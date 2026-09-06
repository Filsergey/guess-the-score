import asyncio
import json
from datetime import datetime, timedelta, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.localization import team_name_ru
from app.match_status import FINAL_MATCH_STATUSES
from app.models import LeagueMember, Match, Prediction, Team, UserLeague
from app.push_models import PushDelivery, PushSubscription

settings = get_settings()


def _configured() -> bool:
    return bool(
        (settings.webpush_vapid_public_key or "").strip()
        and (settings.webpush_vapid_private_key or "").strip()
    )


def _subscription_info(subscription: PushSubscription) -> dict:
    return {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }


async def _send(subscription: PushSubscription, payload: dict) -> bool:
    private_key = (settings.webpush_vapid_private_key or "").strip()
    subject = (settings.webpush_subject or "").strip() or "mailto:admin@example.com"
    try:
        await asyncio.to_thread(
            webpush,
            subscription_info=_subscription_info(subscription),
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            ttl=3600,
            timeout=7,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            return False
        raise


async def _already_sent(db: AsyncSession, user_id: int, event_key: str) -> bool:
    return await db.scalar(
        select(PushDelivery.id).where(PushDelivery.user_id == user_id, PushDelivery.event_key == event_key)
    ) is not None


async def _send_user(db: AsyncSession, user_id: int, event_key: str, payload: dict) -> tuple[int, int]:
    if await _already_sent(db, user_id, event_key):
        return 0, 0
    subscriptions = (
        await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    sent = 0
    stale = 0
    for subscription in subscriptions:
        try:
            ok = await _send(subscription, payload)
            if ok:
                sent += 1
            else:
                await db.delete(subscription)
                stale += 1
        except Exception:
            continue
    if sent:
        db.add(PushDelivery(user_id=user_id, event_key=event_key, sent_at=datetime.now(timezone.utc)))
    return sent, stale


async def _league_users_for_match(db: AsyncSession, match: Match) -> set[int]:
    rows = await db.execute(
        select(LeagueMember.user_id)
        .join(UserLeague, UserLeague.id == LeagueMember.league_id)
        .where(
            UserLeague.tournament_provider == match.provider,
            UserLeague.tournament_season == match.season,
            UserLeague.tournament_id == match.tournament_id,
        )
        .distinct()
    )
    return {int(row[0]) for row in rows.all()}


def _score_points(ph: int, pa: int, ah: int, aa: int) -> int:
    if ph == ah and pa == aa:
        return 3
    return 1 if (ph > pa) - (ph < pa) == (ah > aa) - (ah < aa) else 0


async def _team_names(db: AsyncSession, match: Match) -> tuple[str, str]:
    home = await db.get(Team, match.home_team_id)
    away = await db.get(Team, match.away_team_id)
    return team_name_ru(home.name if home else "Хозяева"), team_name_ru(away.name if away else "Гости")


async def _prediction_reminders(db: AsyncSession, now: datetime) -> dict:
    matches = (
        await db.execute(
            select(Match)
            .where(
                Match.kickoff_at >= now + timedelta(minutes=25),
                Match.kickoff_at <= now + timedelta(minutes=35),
                ~Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
            )
            .order_by(Match.kickoff_at)
            .limit(12)
        )
    ).scalars().all()
    sent = stale = candidates = 0
    for match in matches:
        users = await _league_users_for_match(db, match)
        if not users:
            continue
        subscribed = set(
            (
                await db.execute(
                    select(PushSubscription.user_id).where(PushSubscription.user_id.in_(users)).distinct()
                )
            ).scalars().all()
        )
        if not subscribed:
            continue
        predicted = set(
            (
                await db.execute(
                    select(Prediction.user_id).where(
                        Prediction.match_id == match.id,
                        Prediction.user_id.in_(subscribed),
                    )
                )
            ).scalars().all()
        )
        targets = subscribed - predicted
        if not targets:
            continue
        home, away = await _team_names(db, match)
        candidates += len(targets)
        for user_id in targets:
            s, st = await _send_user(
                db,
                int(user_id),
                f"prediction-reminder:{match.id}",
                {
                    "title": "Прогноз не сделан ⚽",
                    "body": f"Через 30 минут {home} — {away}. Успей поставить счёт.",
                    "url": "/",
                    "tag": f"prediction-reminder-{match.id}",
                },
            )
            sent += s
            stale += st
    return {"matches": len(matches), "candidates": candidates, "sent": sent, "stale_removed": stale}


async def _result_notifications(db: AsyncSession, now: datetime) -> dict:
    matches = (
        await db.execute(
            select(Match)
            .where(
                Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
                Match.updated_at >= now - timedelta(minutes=5),
            )
            .order_by(Match.updated_at.desc())
            .limit(12)
        )
    ).scalars().all()
    sent = stale = candidates = 0
    for match in matches:
        users = await _league_users_for_match(db, match)
        if not users:
            continue
        predictions = (
            await db.execute(
                select(Prediction).where(Prediction.match_id == match.id, Prediction.user_id.in_(users))
            )
        ).scalars().all()
        if not predictions:
            continue
        subscribed = set(
            (
                await db.execute(
                    select(PushSubscription.user_id).where(
                        PushSubscription.user_id.in_([p.user_id for p in predictions])
                    ).distinct()
                )
            ).scalars().all()
        )
        if not subscribed:
            continue
        home, away = await _team_names(db, match)
        by_user = {p.user_id: p for p in predictions}
        candidates += len(subscribed)
        for user_id in subscribed:
            prediction = by_user.get(user_id)
            if prediction is None:
                continue
            points = _score_points(
                int(prediction.home_score),
                int(prediction.away_score),
                int(match.home_goals),
                int(match.away_goals),
            )
            if points == 3:
                lead = "Точный счёт! +3 очка 🎯"
            elif points == 1:
                lead = "Исход угадан. +1 очко"
            else:
                lead = "В этот раз 0 очков"
            s, st = await _send_user(
                db,
                int(user_id),
                f"match-result:{match.id}",
                {
                    "title": lead,
                    "body": f"{home} {match.home_goals}:{match.away_goals} {away}",
                    "url": "/",
                    "tag": f"match-result-{match.id}",
                },
            )
            sent += s
            stale += st
    return {"matches": len(matches), "candidates": candidates, "sent": sent, "stale_removed": stale}


async def process_push_notifications(db: AsyncSession) -> dict:
    if not _configured():
        return {"configured": False, "sent": 0}
    now = datetime.now(timezone.utc)
    reminders = await _prediction_reminders(db, now)
    results = await _result_notifications(db, now)
    await db.commit()
    return {
        "configured": True,
        "sent": int(reminders["sent"]) + int(results["sent"]),
        "prediction_reminders": reminders,
        "results": results,
    }
