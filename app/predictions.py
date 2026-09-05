from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Match, Prediction, User

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionInput(BaseModel):
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)


def _outcome(home: int, away: int) -> int:
    return 1 if home > away else -1 if home < away else 0


def prediction_points(prediction: Prediction, match: Match) -> int | None:
    if match.home_goals is None or match.away_goals is None:
        return None
    if prediction.home_score == match.home_goals and prediction.away_score == match.away_goals:
        return 3
    if _outcome(prediction.home_score, prediction.away_score) == _outcome(match.home_goals, match.away_goals):
        return 1
    return 0


def serialize_prediction(prediction: Prediction, match: Match) -> dict:
    return {
        "id": prediction.id,
        "match_id": prediction.match_id,
        "home_score": prediction.home_score,
        "away_score": prediction.away_score,
        "created_at": prediction.created_at,
        "updated_at": prediction.updated_at,
        "locked": datetime.now(timezone.utc) >= match.kickoff_at,
        "points": prediction_points(prediction, match),
    }


@router.put("/matches/{match_id}")
async def save_prediction(match_id: int, body: PredictionInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    match = await db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    now = datetime.now(timezone.utc)
    if now >= match.kickoff_at:
        raise HTTPException(status_code=409, detail="Prediction is locked because the match has started")
    if match.kickoff_at < user.registered_at:
        raise HTTPException(status_code=409, detail="Match is not eligible for this user")
    prediction = await db.scalar(select(Prediction).where(Prediction.user_id == user.id, Prediction.match_id == match_id))
    if prediction is None:
        prediction = Prediction(user_id=user.id, match_id=match_id, home_score=body.home_score, away_score=body.away_score, created_at=now, updated_at=now)
        db.add(prediction)
    else:
        prediction.home_score = body.home_score
        prediction.away_score = body.away_score
        prediction.updated_at = now
    await db.commit(); await db.refresh(prediction)
    return serialize_prediction(prediction, match)


@router.get("/matches/{match_id}/mine")
async def my_prediction(match_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    match = await db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    prediction = await db.scalar(select(Prediction).where(Prediction.user_id == user.id, Prediction.match_id == match_id))
    return {"match_id": match_id, "has_prediction": prediction is not None, "prediction": serialize_prediction(prediction, match) if prediction else None}


@router.get("/matches/{match_id}/participants")
async def match_prediction_participants(match_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    match = await db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    started = datetime.now(timezone.utc) >= match.kickoff_at
    rows = (await db.execute(select(Prediction, User).join(User, Prediction.user_id == User.id).where(Prediction.match_id == match_id).order_by(User.display_name))).all()
    response = []
    for prediction, participant in rows:
        item = {"user_id": participant.id, "display_name": participant.display_name, "avatar_url": participant.avatar_url, "has_prediction": True}
        if started or participant.id == user.id:
            item["prediction"] = {"home_score": prediction.home_score, "away_score": prediction.away_score, "points": prediction_points(prediction, match)}
        response.append(item)
    return {"match_id": match_id, "started": started, "predictions_visible": started, "count": len(response), "response": response}


@router.get("/mine")
async def my_predictions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(Prediction, Match).join(Match, Prediction.match_id == Match.id).where(Prediction.user_id == user.id).order_by(Match.kickoff_at))).all()
    items = [serialize_prediction(prediction, match) for prediction, match in rows]
    return {"count": len(items), "response": items}
