import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Match, OraclePrediction, UserLeague
from app.oracle import _is_ai_payload, _payload_from_row, generate_or_refresh_matches

logger = logging.getLogger(__name__)
_EVENT_LOCK = asyncio.Lock()
_TASKS: set[asyncio.Task] = set()
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


def schedule_oracle_initialization(
    *,
    provider: str,
    season: int,
    tournament_id: int | None,
    match_ids: list[int] | None = None,
) -> None:
    """Queue one-time INITIAL forecasts after a league/match creation event.

    This is deliberately event-driven: it is not a polling scheduler and it never
    refreshes an existing AI forecast. Updates happen only when a user opens
    "Прогноз ИИ" and the match context has changed.
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
    """Create missing AI predictions once for matches used by an Oracle league."""
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

            ids = [m.id for m in matches]
            rows = (
                await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))
            ).scalars().all()
            by_match = {row.match_id: row for row in rows}
            missing = [
                match
                for match in matches
                if not _is_ai_payload(_payload_from_row(by_match.get(match.id)))
            ]

            totals = {"eligible": len(matches), "missing": len(missing), "generated": 0, "failed": 0}
            for start in range(0, len(missing), BATCH_SIZE):
                batch = missing[start : start + BATCH_SIZE]
                try:
                    result = await generate_or_refresh_matches(db, batch, force=False)
                    generated = int(result.get("generated") or 0)
                    failed = int(result.get("failed") or 0)
                    totals["generated"] += generated
                    totals["failed"] += failed
                    # A provider/quota failure normally affects the whole batch.
                    # Stop immediately instead of spending/retrying every remaining
                    # match in the same event. A later user action or new event can retry.
                    if failed and not generated:
                        totals["stopped_after_failure"] = True
                        break
                except Exception:
                    totals["failed"] += len(batch)
                    totals["stopped_after_failure"] = True
                    logger.exception("Event-driven Oracle initialization failed")
                    break
            if totals["missing"]:
                logger.info("Event-driven Oracle initialization: %s", totals)
            return totals


async def initialize_all_active_oracle_leagues() -> None:
    """One bootstrap pass for leagues that existed before event hooks were installed."""
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
        for (provider, season, tournament_id), match_ids in new_matches.items():
            pending.append(("matches", provider, season, tournament_id, match_ids))

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
