import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Match, OraclePrediction, UserLeague
from app.oracle import _is_ai_payload, _payload_from_row, generate_or_refresh_matches

logger = logging.getLogger(__name__)
settings = get_settings()
_EVENT_LOCK = asyncio.Lock()
_TASKS: set[asyncio.Task] = set()
_DELAYED_KEYS: set[tuple[str, int, int | None, int]] = set()
BATCH_SIZE = 5
_HOOKS_INSTALLED = False
_BOOTSTRAP_SCHEDULED = False
_PENDING_KEY = "gts_oracle_initial_events"


def _track(task: asyncio.Task) -> None:
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def _spawn(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        close = getattr(coro, "close", None)
        if close:
            close()
        return
    _track(loop.create_task(coro))


def _window_hours() -> int:
    return max(1, int(settings.oracle_initial_window_hours or 72))


def _schedule_match_for_window(match: Match) -> bool:
    """Schedule a one-shot INITIAL at T-window without polling OpenAI.

    The task is only a local asyncio timer. On a process restart the bootstrap pass
    recreates timers from the database, so no persistent scheduler is required.
    """
    if match.kickoff_at is None:
        return False

    key = (
        str(match.provider),
        int(match.season),
        int(match.tournament_id) if match.tournament_id is not None else None,
        int(match.id),
    )
    if key in _DELAYED_KEYS:
        return False

    now = datetime.now(timezone.utc)
    run_at = match.kickoff_at - timedelta(hours=_window_hours())
    delay = max(0.0, (run_at - now).total_seconds())

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    _DELAYED_KEYS.add(key)

    async def _run_later() -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await initialize_missing_oracle_predictions(
                provider=key[0],
                season=key[1],
                tournament_id=key[2],
                match_ids=[key[3]],
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Deferred Oracle initialization failed for match %s", key[3])
        finally:
            _DELAYED_KEYS.discard(key)

    _track(loop.create_task(_run_later()))
    return True


def schedule_oracle_initialization(
    *,
    provider: str,
    season: int,
    tournament_id: int | None,
    match_ids: list[int] | None = None,
) -> None:
    """Queue INITIAL forecasts after league/match creation events.

    Matches inside the configured pre-kickoff window can be generated immediately.
    Matches farther away only receive a local one-shot timer for T-72h. Existing AI
    forecasts are never refreshed here; delta refreshes remain user-driven.
    """
    _spawn(
        initialize_missing_oracle_predictions(
            provider=provider,
            season=season,
            tournament_id=tournament_id,
            match_ids=match_ids,
        )
    )


async def initialize_missing_oracle_predictions(
    *,
    provider: str,
    season: int,
    tournament_id: int | None,
    match_ids: list[int] | None = None,
) -> dict:
    """Create missing AI predictions only inside the configured kickoff window."""
    async with _EVENT_LOCK:
        async with SessionLocal() as db:
            league_query = select(UserLeague.id).where(
                UserLeague.include_oracle.is_(True),
                UserLeague.tournament_provider == provider,
                UserLeague.tournament_season == season,
            )
            if tournament_id is not None:
                league_query = league_query.where(UserLeague.tournament_id == tournament_id)
            if await db.scalar(league_query.limit(1)) is None:
                return {"eligible": 0, "generated": 0, "reason": "no-oracle-league"}

            now = datetime.now(timezone.utc)
            window_end = now + timedelta(hours=_window_hours())
            query = select(Match).where(
                Match.provider == provider,
                Match.season == season,
                Match.kickoff_at > now,
            )
            if tournament_id is not None:
                query = query.where(Match.tournament_id == tournament_id)
            if match_ids:
                query = query.where(Match.id.in_(match_ids))

            matches = (await db.execute(query.order_by(Match.kickoff_at))).scalars().all()
            if not matches:
                return {"eligible": 0, "generated": 0, "reason": "no-upcoming-matches"}

            due = [match for match in matches if match.kickoff_at <= window_end]
            deferred = [match for match in matches if match.kickoff_at > window_end]
            scheduled = sum(1 for match in deferred if _schedule_match_for_window(match))

            if not due:
                return {
                    "eligible": len(matches),
                    "window_eligible": 0,
                    "deferred": len(deferred),
                    "scheduled": scheduled,
                    "generated": 0,
                    "reason": "outside-initial-window",
                }

            ids = [match.id for match in due]
            rows = (
                await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))
            ).scalars().all()
            by_match = {row.match_id: row for row in rows}
            missing = [
                match
                for match in due
                if not _is_ai_payload(_payload_from_row(by_match.get(match.id)))
            ]

            totals = {
                "eligible": len(matches),
                "window_eligible": len(due),
                "deferred": len(deferred),
                "scheduled": scheduled,
                "missing": len(missing),
                "generated": 0,
                "failed": 0,
            }
            for start in range(0, len(missing), BATCH_SIZE):
                batch = missing[start : start + BATCH_SIZE]
                try:
                    result = await generate_or_refresh_matches(db, batch, force=False)
                    generated = int(result.get("generated") or 0)
                    failed = int(result.get("failed") or 0)
                    totals["generated"] += generated
                    totals["failed"] += failed
                    # A provider/quota failure normally affects the whole batch.
                    # Stop immediately instead of retrying every remaining match.
                    if failed and not generated:
                        totals["stopped_after_failure"] = True
                        break
                except Exception:
                    totals["failed"] += len(batch)
                    totals["stopped_after_failure"] = True
                    logger.exception("Event-driven Oracle initialization failed")
                    break

            if totals["missing"] or totals["deferred"]:
                logger.info("Event-driven Oracle initialization: %s", totals)
            return totals


async def initialize_all_active_oracle_leagues() -> None:
    """Bootstrap due forecasts and recreate future T-72h timers after a restart."""
    await asyncio.sleep(2)
    try:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(
                        UserLeague.tournament_provider,
                        UserLeague.tournament_season,
                        UserLeague.tournament_id,
                    )
                    .where(UserLeague.include_oracle.is_(True))
                    .distinct()
                )
            ).all()
        for provider, season, tournament_id in rows:
            result = await initialize_missing_oracle_predictions(
                provider=str(provider),
                season=int(season),
                tournament_id=int(tournament_id) if tournament_id is not None else None,
            )
            if result.get("stopped_after_failure"):
                break
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Bootstrap Oracle initialization failed")


def install_oracle_event_hooks() -> None:
    """Listen for newly created leagues/matches and initialize Oracle exactly once."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True

    @event.listens_for(Session, "after_flush")
    def _capture_new_objects(session, flush_context):
        pending = session.info.setdefault(_PENDING_KEY, [])
        new_matches = defaultdict(list)
        for obj in session.new:
            if isinstance(obj, UserLeague) and obj.include_oracle:
                pending.append(
                    (
                        "league",
                        str(obj.tournament_provider),
                        int(obj.tournament_season),
                        int(obj.tournament_id) if obj.tournament_id is not None else None,
                        None,
                    )
                )
            elif isinstance(obj, Match) and obj.id is not None:
                key = (
                    str(obj.provider),
                    int(obj.season),
                    int(obj.tournament_id) if obj.tournament_id is not None else None,
                )
                new_matches[key].append(int(obj.id))
        for (provider, season, tournament_id), created_match_ids in new_matches.items():
            pending.append(("matches", provider, season, tournament_id, created_match_ids))

    @event.listens_for(Session, "after_commit")
    def _after_commit(session):
        global _BOOTSTRAP_SCHEDULED
        pending = list(session.info.pop(_PENDING_KEY, []) or [])
        if not _BOOTSTRAP_SCHEDULED:
            _BOOTSTRAP_SCHEDULED = True
            _spawn(initialize_all_active_oracle_leagues())
        for _, provider, season, tournament_id, match_ids in pending:
            schedule_oracle_initialization(
                provider=provider,
                season=season,
                tournament_id=tournament_id,
                match_ids=match_ids,
            )

    @event.listens_for(Session, "after_rollback")
    def _after_rollback(session):
        session.info.pop(_PENDING_KEY, None)
