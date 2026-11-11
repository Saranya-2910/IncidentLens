"""Application configuration loaded from environment variables using Pydantic Settings."""

from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(v: object) -> list[str]:
    if isinstance(v, str):
        import json
        try:
            return json.loads(v)
        except Exception:
            return [origin.strip() for origin in v.split(",") if origin.strip()]
    elif isinstance(v, list):
        return [str(item) for item in v]
    return ["http://localhost:3000", "http://localhost:5173"]


class Settings(BaseSettings):
    """IncidentLens application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Core Application
    PROJECT_NAME: str = "IncidentLens"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Security & Auth
    SECRET_KEY: str = "dev-secret-key-change-in-production-only"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: Annotated[list[str], BeforeValidator(_parse_cors_origins)] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/incidentlens"
    DATABASE_SYNC_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/incidentlens"

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # AI & LLM (Never expose to frontend)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "text-embedding-004"


settings = Settings()
