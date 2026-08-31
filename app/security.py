import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt

from app.config import get_settings

settings = get_settings()


def verify_telegram_init_data(init_data: str, max_age_seconds: int = 86400) -> dict:
    """Verify Telegram Mini App initData and return the Telegram user payload."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise ValueError("Telegram initData has no hash")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram initData signature")

    auth_date_raw = values.get("auth_date")
    if not auth_date_raw:
        raise ValueError("Telegram initData has no auth_date")
    auth_date = datetime.fromtimestamp(int(auth_date_raw), tz=timezone.utc)
    now = datetime.now(timezone.utc)
    if auth_date > now + timedelta(minutes=5) or now - auth_date > timedelta(seconds=max_age_seconds):
        raise ValueError("Telegram initData is expired")

    user_raw = values.get("user")
    if not user_raw:
        raise ValueError("Telegram initData has no user")
    user = json.loads(user_raw)
    if not user.get("id"):
        raise ValueError("Telegram user has no id")
    return user


def create_access_token(user_id: int, role: str) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    return payload
