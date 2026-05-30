"""Application settings, loaded from environment / .env (see .env.example)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # An empty env var (e.g. a blank ANTHROPIC_API_KEY in the shell) must not shadow .env.
        env_ignore_empty=True,
    )

    app_name: str = "Trip Planner"
    app_env: str = "development"
    debug: bool = True

    # Async SQLAlchemy URL. Default matches docker-compose.yml.
    database_url: str = "postgresql+asyncpg://trip:trip@localhost:5432/trip_planner"
    sql_echo: bool = False

    # Secrets — optional so the app boots without them (needed from Phase 2).
    anthropic_api_key: str | None = None
    google_maps_api_key: str | None = None

    # Comma-separated list of allowed CORS origins; "*" allows all.
    cors_origins: str = "*"


settings = Settings()
