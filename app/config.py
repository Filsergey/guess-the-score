import base64
import hashlib
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic_settings import BaseSettings, SettingsConfigDict

_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _derived_vapid_pair(secret: str) -> tuple[str, str]:
    digest = hashlib.sha256(("gts-webpush-v1:" + secret).encode("utf-8")).digest()
    scalar = (int.from_bytes(digest, "big") % (_P256_ORDER - 1)) + 1
    private_key = ec.derive_private_key(scalar, ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    private_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _b64url(public_bytes), _b64url(private_der)


class Settings(BaseSettings):
    app_name: str = "Guess The Score API"
    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/guess_the_score"
    sstats_api_key: str = ""
    # Legacy compatibility only. The active league/logo flows do not use API-Football.
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    admin_sync_token: str = ""
    telegram_bot_token: str = ""
    telegram_login_client_id: str = ""
    telegram_login_client_secret: str = ""
    webpush_vapid_public_key: str = ""
    webpush_vapid_private_key: str = ""
    webpush_subject: str = "mailto:admin@example.com"
    jwt_secret: str = ""
    jwt_access_minutes: int = 60 * 24 * 7
    superadmin_telegram_id: int | None = None
    openai_api_key: str = ""
    openai_oracle_model: str = "gpt-5-mini"
    openai_oracle_enabled: bool = True
    oracle_scheduler_enabled: bool = True
    oracle_scheduler_interval_minutes: int = 60
    oracle_scheduler_batch_size: int = 5
    oracle_scheduler_max_batches: int = 4
    oracle_scheduler_hours_ahead: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context) -> None:
        secret = (self.jwt_secret or "").strip()
        if secret:
            public_key, private_key = _derived_vapid_pair(secret)
            self.webpush_vapid_public_key = public_key
            self.webpush_vapid_private_key = private_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
