"""Application configuration loaded from environment variables.

Connection secrets (Dataverse service-principal secret, Foundry key) are NOT
stored here — they live encrypted in the ``app_config`` table and are entered
via the admin UI. Only infrastructure/bootstrap values come from the environment.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://agentquality:agentquality@db:5432/agentquality",
        alias="DATABASE_URL",
    )

    # --- Security ---------------------------------------------------------
    secret_key: str = Field(default="dev-insecure-change-me", alias="SECRET_KEY")
    fernet_key: str = Field(default="", alias="FERNET_KEY")
    access_token_expire_minutes: int = Field(
        default=60 * 12, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    admin_username: str | None = Field(default=None, alias="ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")

    # --- App --------------------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    frontend_dist: str = Field(default="frontend/dist", alias="FRONTEND_DIST")

    # --- Scan tuning ------------------------------------------------------
    scan_concurrency: int = Field(default=8, alias="SCAN_CONCURRENCY")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
