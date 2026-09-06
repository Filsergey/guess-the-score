import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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


async def _upsert_telegram_user(
    db: AsyncSession,
    telegram_id: int,
    username: str | None,
    display_name: str,
    avatar_url: str | None,
) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    now = datetime.now(timezone.utc)
    role = "superadmin" if settings.superadmin_telegram_id == telegram_id else "user"
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            role=role,
            registered_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()
    else:
        user.username = username
        user.display_name = display_name
        user.avatar_url = avatar_url
        if role == "superadmin":
            user.role = "superadmin"
        user.last_login_at = now
    await db.commit()
    await db.refresh(user)
    return user


def _web_login_config() -> tuple[str, str]:
    client_id = (settings.telegram_login_client_id or "").strip()
    client_secret = (settings.telegram_login_client_secret or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Вход через Telegram в браузере ещё не настроен")
    if not (settings.jwt_secret or "").strip():
        raise HTTPException(status_code=503, detail="JWT_SECRET не настроен")
    return client_id, client_secret


def _callback_url(request: Request) -> str:
    url = str(request.url_for("telegram_web_callback"))
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto in {"http", "https"} and "://" in url:
        url = forwarded_proto + "://" + url.split("://", 1)[1]
    return url


def _oauth_state_token(state: str, verifier: str) -> str:
    return jwt.encode(
        {
            "state": state,
            "verifier": verifier,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def _decode_oauth_state(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Сессия входа истекла. Попробуй войти ещё раз.") from exc


async def _verify_telegram_id_token(id_token: str, client_id: str) -> dict:
    try:
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        alg = header.get("alg")
        if alg not in {"RS256", "ES256"} or not kid:
            raise ValueError("Unsupported Telegram signing key")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("https://oauth.telegram.org/.well-known/jwks.json")
            response.raise_for_status()
            jwks = response.json()
        key_data = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
        if key_data is None:
            raise ValueError("Telegram signing key not found")
        signing_key = jwt.PyJWK.from_dict(key_data, algorithm=alg).key
        return jwt.decode(
            id_token,
            signing_key,
            algorithms=[alg],
            audience=str(client_id),
            issuer="https://oauth.telegram.org",
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Не удалось подтвердить вход через Telegram") from exc


@router.post("/telegram")
async def telegram_login(body: TelegramLoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        telegram_user = verify_telegram_init_data(body.init_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    telegram_id = int(telegram_user["id"])
    display_name = " ".join(
        part for part in [telegram_user.get("first_name"), telegram_user.get("last_name")] if part
    ).strip() or telegram_user.get("username") or f"User {telegram_id}"
    user = await _upsert_telegram_user(
        db,
        telegram_id=telegram_id,
        username=telegram_user.get("username"),
        display_name=display_name,
        avatar_url=telegram_user.get("photo_url"),
    )

    try:
        access_token = create_access_token(user.id, user.role)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@router.get("/web/status")
async def telegram_web_status() -> dict:
    configured = bool(
        (settings.telegram_login_client_id or "").strip()
        and (settings.telegram_login_client_secret or "").strip()
        and (settings.jwt_secret or "").strip()
    )
    return {"configured": configured, "login_url": "/api/auth/web/start"}


@router.get("/web/start")
async def telegram_web_start(request: Request):
    client_id, _ = _web_login_config()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).rstrip(b"=").decode("ascii")
    redirect_uri = _callback_url(request)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    response = RedirectResponse(f"https://oauth.telegram.org/auth?{urlencode(params)}", status_code=302)
    secure = request.url.scheme == "https" or (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip() == "https"
    response.set_cookie(
        "gts_tg_oauth",
        _oauth_state_token(state, verifier),
        max_age=600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth/web",
    )
    return response


@router.get("/web/callback", name="telegram_web_callback")
async def telegram_web_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if error:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>Вход отменён</title>"
            "<body style='font-family:system-ui;background:#07111f;color:white;padding:32px'>"
            "<h2>Вход через Telegram отменён</h2><p><a style='color:#5fc6ff' href='/'>Вернуться в приложение</a></p></body>",
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    cookie = request.cookies.get("gts_tg_oauth")
    if not cookie or not code or not state:
        raise HTTPException(status_code=400, detail="Не удалось продолжить вход через Telegram")
    saved = _decode_oauth_state(cookie)
    if not secrets.compare_digest(str(saved.get("state") or ""), str(state)):
        raise HTTPException(status_code=400, detail="Некорректное состояние входа")

    client_id, client_secret = _web_login_config()
    redirect_uri = _callback_url(request)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            token_response = await client.post(
                "https://oauth.telegram.org/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": str(saved.get("verifier") or ""),
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Telegram не завершил вход. Попробуй ещё раз.") from exc

    id_token = str(token_payload.get("id_token") or "")
    if not id_token:
        raise HTTPException(status_code=502, detail="Telegram не вернул данные пользователя")
    claims = await _verify_telegram_id_token(id_token, client_id)
    try:
        telegram_id = int(claims.get("id"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Telegram не вернул ID пользователя") from exc
    username = str(claims.get("preferred_username") or "").strip() or None
    display_name = str(claims.get("name") or username or f"User {telegram_id}").strip()
    avatar_url = str(claims.get("picture") or "").strip() or None
    user = await _upsert_telegram_user(db, telegram_id, username, display_name, avatar_url)
    access_token = create_access_token(user.id, user.role)
    token_json = json.dumps(access_token)
    html = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Угадай счёт</title></head><body style='margin:0;background:#07111f;color:white;font-family:system-ui;display:grid;place-items:center;min-height:100vh'><div>Вход выполнен…</div><script>localStorage.setItem('access_token',{token_json});location.replace('/?source=pwa');</script></body></html>"""
    response = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    response.delete_cookie("gts_tg_oauth", path="/api/auth/web")
    return response


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
    member = await db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
        )
    )
    if member is None and user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Приглашение доступно только участникам лиги")
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
