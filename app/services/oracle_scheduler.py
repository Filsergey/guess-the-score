import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Match, OraclePrediction
from app.oracle import _needs_refresh, generate_or_refresh_matches

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_due_oracle_predictions() -> dict:
    """Check upcoming context; local forecasts work even when OpenAI is unavailable."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=settings.oracle_scheduler_hours_ahead)
    totals = {"requested": 0, "generated": 0, "unchanged": 0, "local_only": 0, "ai_requested": 0}

    for _ in range(settings.oracle_scheduler_max_batches):
        async with SessionLocal() as db:
            matches = (
                await db.execute(
                    select(Match)
                    .where(Match.kickoff_at > now, Match.kickoff_at <= end)
                    .order_by(Match.kickoff_at)
                )
            ).scalars().all()

            selected = []
            for match in matches:
                cache = (
                    await db.execute(
                        select(OraclePrediction).where(OraclePrediction.match_id == match.id)
                    )
                ).scalar_one_or_none()
                if _needs_refresh(match, cache, now):
                    selected.append(match)
                if len(selected) >= settings.oracle_scheduler_batch_size:
                    break

            if not selected:
                break

            result = await generate_or_refresh_matches(db, selected, force=False, refresh_news=True)
            for key in totals:
                totals[key] += int(result.get(key) or 0)

            # Avoid repeatedly retrying the same failed AI batch in one scheduler tick.
            if result.get("ai_requested") and not result.get("generated") and not result.get("unchanged"):
                break

    return totals


async def oracle_scheduler_loop() -> None:
    """Run once shortly after startup and then periodically while the API is alive."""
    await asyncio.sleep(20)
    while True:
        try:
            result = await generate_due_oracle_predictions()
            if result.get("requested"):
                logger.info("Oracle scheduler: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oracle scheduler iteration failed")

        await asyncio.sleep(max(15, settings.oracle_scheduler_interval_minutes) * 60)
