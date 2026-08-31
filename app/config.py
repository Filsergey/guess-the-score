from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Guess The Score API"
    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/guess_the_score"
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    admin_sync_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
