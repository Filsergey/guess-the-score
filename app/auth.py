from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import create_access_token, decode_access_token, verify_telegram_init_data

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
settings = get_settings()


class TelegramLoginRequest(BaseModel):
    init_data: str


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "registered_at": user.registered_at,
        "last_login_at": user.last_login_at,
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/telegram")
async def telegram_login(body: TelegramLoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        telegram_user = verify_telegram_init_data(body.init_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    telegram_id = int(telegram_user["id"])
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    now = datetime.now(timezone.utc)
    display_name = " ".join(
        part for part in [telegram_user.get("first_name"), telegram_user.get("last_name")] if part
    ).strip() or telegram_user.get("username") or f"User {telegram_id}"

    role = "superadmin" if settings.superadmin_telegram_id == telegram_id else "user"
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=telegram_user.get("username"),
            display_name=display_name,
            avatar_url=telegram_user.get("photo_url"),
            role=role,
            registered_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()
    else:
        user.username = telegram_user.get("username")
        user.display_name = display_name
        user.avatar_url = telegram_user.get("photo_url")
        if role == "superadmin":
            user.role = "superadmin"
        user.last_login_at = now

    await db.commit()
    await db.refresh(user)
    try:
        access_token = create_access_token(user.id, user.role)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return serialize_user(user)
