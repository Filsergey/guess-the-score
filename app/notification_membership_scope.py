"""Keep scheduled notifications scoped to leagues the user still belongs to.

The original notification helper had a broad provider+season fallback. If a league
for a tournament was deleted, a match from that deleted tournament could still be
routed to members of another league in the same provider/season. This module keeps
legacy tournament-less leagues working, but never falls across different explicit
tournaments.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeagueMember, Match, User, UserLeague
from app.profile_models import UserProfile
from app.services import notifications


async def _strict_league_members_for_match(
    db: AsyncSession,
    match: Match,
) -> list[tuple[UserLeague, User]]:
    stmt = (
        select(UserLeague, User)
        .join(LeagueMember, LeagueMember.league_id == UserLeague.id)
        .join(User, User.id == LeagueMember.user_id)
        .where(
            UserLeague.tournament_provider == match.provider,
            UserLeague.tournament_season == match.season,
        )
    )
    if match.tournament_id is not None:
        # Exact tournament leagues are eligible. A legacy league with no tournament
        # id remains provider/season-wide, but a league for another explicit
        # tournament must never receive this match's notifications.
        stmt = stmt.where(
            or_(
                UserLeague.tournament_id == match.tournament_id,
                UserLeague.tournament_id.is_(None),
            )
        )
    else:
        stmt = stmt.where(UserLeague.tournament_id.is_(None))
    return (await db.execute(stmt)).all()


def _match_belongs_to_current_leagues(match: Match, leagues: list[UserLeague]) -> bool:
    for league in leagues:
        if league.tournament_provider != match.provider or league.tournament_season != match.season:
            continue
        if league.tournament_id is None:
            if match.tournament_id is None:
                return True
            # A legacy tournament-less league intentionally represents the whole
            # provider/season, matching the scheduled-notification helper above.
            return True
        if match.tournament_id == league.tournament_id:
            return True
    return False


async def _strict_daily_for_user(db: AsyncSession, user: User, now: datetime) -> None:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    raw = {}
    if profile:
        try:
            raw = json.loads(profile.notification_preferences or "{}")
        except Exception:
            raw = {}

    tzname = raw.get("_timezone") or "Europe/Moscow"
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    local = now.astimezone(tz)
    if not (local.hour == 8 and local.minute < 15):
        return

    day_key = local.date().isoformat()
    prefs = notifications.normalize_preferences(raw)
    if not prefs.get("daily_digest", False):
        return

    leagues = (
        await db.execute(
            select(UserLeague)
            .join(LeagueMember, LeagueMember.league_id == UserLeague.id)
            .where(LeagueMember.user_id == user.id)
        )
    ).scalars().all()

    start = datetime.combine(local.date(), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    matches = (
        await db.execute(
            select(Match)
            .where(Match.kickoff_at >= start, Match.kickoff_at < end)
            .order_by(Match.kickoff_at)
        )
    ).scalars().all()
    matches = [
        match
        for match in matches
        if not notifications._is_qualifying_match(match)
        and _match_belongs_to_current_leagues(match, leagues)
    ]

    if matches:
        lines = []
        for match in matches[:5]:
            home, away = await notifications._match_names(db, match)
            lines.append(f'{match.kickoff_at.astimezone(tz).strftime("%H:%M")} — {home} — {away}')
        body = "Сегодня: " + "; ".join(lines)
        if len(matches) > 5:
            body += f". И ещё {len(matches) - 5} матч(а)."
        title = "Утренняя сводка Оракула"
    else:
        fact = notifications.FACTS[local.toordinal() % len(notifications.FACTS)]
        style = profile.oracle_style if profile else "irony"
        prefix = {
            "merciless": "Оракул без пощады: ",
            "irony": "Оракул напоминает: ",
            "calm": "Факт дня: ",
            "numbers": "Факт: ",
        }.get(style, "Оракул: ")
        title = "Футбольный факт дня"
        body = prefix + fact

    await notifications.deliver_to_user(
        db,
        user,
        f"daily:{day_key}",
        "daily_digest",
        title,
        body,
        "/",
    )


def install_notification_membership_scope() -> None:
    notifications._league_members_for_match = _strict_league_members_for_match
    notifications._daily_for_user = _strict_daily_for_user
