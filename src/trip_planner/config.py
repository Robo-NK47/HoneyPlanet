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
    # Anthropic is still used by the hotel/transport/budget specialist experts.
    anthropic_api_key: str | None = None
    google_maps_api_key: str | None = None

    # Chat agent — a Qwen model over any OpenAI-compatible endpoint.
    # Default: local Ollama (free, offline). `ollama pull qwen3.5:9b` first.
    # Point these at DashScope / OpenRouter / vLLM to use a hosted model instead.
    qwen_api_key: str | None = None  # Ollama ignores this; hosted providers require it.
    qwen_base_url: str = "http://localhost:11434/v1"
    qwen_model: str = "qwen3.5:9b"

    # Comma-separated list of allowed CORS origins; "*" allows all (credentials disabled then).
    cors_origins: str = "*"

    # Optional shared-password auth (opt-in). When set, /plan, /chat and task writes require
    # signing in at /login. Leave empty for open local dev.
    app_secret: str | None = None


settings = Settings()
