"""
Application settings loaded from environment variables / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Geospatial File Measurement API"
    environment: str = "development"
    log_level: str = "INFO"

    # Database — SQLite by default for easy local startup; swap to PostgreSQL in production.
    database_url: str = "sqlite:///./geospatial_api.db"

    # Upload storage root directory
    storage_root: Path = Path("./storage")

    # Upload limits
    max_upload_size_mb: int = Field(default=50, ge=1, le=1024)
    max_zip_entries: int = Field(default=1000, ge=1, le=100_000)
    max_zip_uncompressed_mb: int = Field(default=250, ge=1, le=4096)

    # CORS — comma-separated list of allowed origins, or "*" for all
    cors_allowed_origins: str = "*"

    # When True the app will call Base.metadata.create_all() on startup (useful for SQLite / tests).
    # Set to False in production and rely on Alembic migrations.
    auto_create_db: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_zip_uncompressed_bytes(self) -> int:
        return self.max_zip_uncompressed_mb * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    # ------------------------------------------------------------------
    # Post-init side effects — create storage directories
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _create_storage_dirs(self) -> "Settings":
        self.storage_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "uploads").mkdir(parents=True, exist_ok=True)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
