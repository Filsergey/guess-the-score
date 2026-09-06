from datetime import datetime, timezone

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.security import create_access_token, decode_access_token, verify_telegram_init_data

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
settings = get_settings()
_bot_username_cache: str | None = None


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


async def _telegram_bot_username() -> str:
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN не настроен")
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            response.raise_for_status()
            payload = response.json()
        username = str((payload.get("result") or {}).get("username") or "").strip().lstrip("@")
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Не удалось получить username Telegram-бота") from exc
    if not username:
        raise HTTPException(status_code=502, detail="Telegram-бот не вернул username")
    _bot_username_cache = username
    return username


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


@router.get("/league-invite/{invite_code}")
async def league_invite_preview(
    invite_code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    code = invite_code.strip().upper()
    if len(code) < 4 or len(code) > 12:
        raise HTTPException(status_code=404, detail="Лига не найдена")
    league = await db.scalar(select(UserLeague).where(UserLeague.invite_code == code))
    if league is None:
        raise HTTPException(status_code=404, detail="Лига не найдена или приглашение устарело")
    member = await db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
        )
    )
    count = await db.scalar(
        select(func.count(LeagueMember.id)).where(LeagueMember.league_id == league.id)
    )
    tournament = await db.get(Tournament, league.tournament_id) if league.tournament_id else None
    return {
        "already_member": member is not None,
        "league": {
            "id": league.id,
            "name": league.name,
            "member_count": int(count or 0),
            "tournament_name": tournament.name if tournament else "SStats",
            "tournament_season": league.tournament_season,
        },
    }


@router.get("/league-invite-link/{league_id}")
async def league_invite_link(
    league_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(status_code=404, detail="Лига не найдена")
    if league.owner_user_id != user.id and user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Ссылкой приглашения управляет владелец лиги")
    username = await _telegram_bot_username()
    start_param = f"league_{league.invite_code}"
    return {
        "league_id": league.id,
        "league_name": league.name,
        "invite_code": league.invite_code,
        "bot_username": username,
        "start_param": start_param,
        "url": f"https://t.me/{username}?startapp={start_param}",
    }
