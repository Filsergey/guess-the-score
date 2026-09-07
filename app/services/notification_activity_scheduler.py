import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Prediction, TournamentPrediction
from app.services.activity_notifications import notify_prediction_activity, notify_tournament_activity

STARTED_AT=datetime.now(timezone.utc)
seen_predictions:set[tuple[int,int,str]]=set()
seen_tournaments:set[tuple[int,int,int|None,str]]=set()

async def _cycle()->None:
    cutoff=max(STARTED_AT-timedelta(seconds=5),datetime.now(timezone.utc)-timedelta(minutes=3))
    async with SessionLocal() as db:
        preds=(await db.execute(select(Prediction).where(Prediction.updated_at>=cutoff))).scalars().all()
        tours=(await db.execute(select(TournamentPrediction).where(TournamentPrediction.updated_at>=cutoff))).scalars().all()
    for p in preds:
        key=(p.user_id,p.match_id,p.updated_at.isoformat())
        if key in seen_predictions:continue
        seen_predictions.add(key);await notify_prediction_activity(p.user_id,p.match_id)
    for p in tours:
        key=(p.user_id,p.season,p.tournament_id,p.updated_at.isoformat())
        if key in seen_tournaments:continue
        seen_tournaments.add(key);await notify_tournament_activity(p.user_id,p.tournament_id,p.season)
    if len(seen_predictions)>5000:seen_predictions.clear()
    if len(seen_tournaments)>2000:seen_tournaments.clear()

async def notification_activity_loop()->None:
    await asyncio.sleep(15)
    while True:
        try:await _cycle()
        except Exception:pass
        await asyncio.sleep(30)
