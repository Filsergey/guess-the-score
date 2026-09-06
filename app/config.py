from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

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

@lru_cache
def get_settings() -> Settings:
    return Settings()
