import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Match, OraclePrediction
from app.oracle import _match_context, _needs_refresh, _save_cache, _web_oracle_batch

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_due_oracle_predictions() -> dict:
    """Generate/refresh cached Oracle predictions for matches approaching kickoff."""
    if not settings.openai_oracle_enabled or not settings.openai_api_key:
        return {"generated": 0, "reason": "openai-disabled"}

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=settings.oracle_scheduler_hours_ahead)
    total_generated = 0
    total_requested = 0

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

            total_requested += len(selected)
            items = [await _match_context(match, db) for match in selected]
            generated = await _web_oracle_batch(items)

            for ctx in items:
                match_id = ctx["match"].id
                data = generated.get(match_id)
                if not data:
                    continue
                data["details_errors"] = ctx["errors"]
                await _save_cache(db, match_id, data)
                total_generated += 1

            await db.commit()

            # Do not spin repeatedly if OpenAI returned nothing for this batch.
            if not generated:
                break

    return {"requested": total_requested, "generated": total_generated}


async def oracle_scheduler_loop() -> None:
    """Run once shortly after startup and then periodically while the API is alive."""
    await asyncio.sleep(20)
    while True:
        try:
            result = await generate_due_oracle_predictions()
            if result.get("generated"):
                logger.info("Oracle scheduler: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oracle scheduler iteration failed")

        await asyncio.sleep(max(15, settings.oracle_scheduler_interval_minutes) * 60)
