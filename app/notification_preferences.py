import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.profile_models import UserProfile

router = APIRouter(prefix="/api/notifications/preferences", tags=["notifications"])

DEFAULT_NOTIFICATION_PREFERENCES = {
    "prediction_reminders": True,
    "participant_activity": True,
    "match_start": True,
    "match_results": True,
    "daily_digest": True,
    "match_videos": True,
}


class NotificationPreferencesUpdate(BaseModel):
    prediction_reminders: bool = True
    participant_activity: bool = True
    match_start: bool = True
    match_results: bool = True
    daily_digest: bool = True
    match_videos: bool = True


def _decode(value: str | None) -> dict[str, bool]:
    prefs = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if not value:
        return prefs
    try:
        raw = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return prefs
    if isinstance(raw, dict):
        for key in prefs:
            if isinstance(raw.get(key), bool):
                prefs[key] = raw[key]
    return prefs


@router.get("")
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    return {"preferences": _decode(profile.notification_preferences if profile else None)}


@router.patch("")
async def update_notification_preferences(
    body: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    prefs = body.model_dump()
    profile.notification_preferences = json.dumps(prefs, ensure_ascii=False, separators=(",", ":"))
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"preferences": prefs}
