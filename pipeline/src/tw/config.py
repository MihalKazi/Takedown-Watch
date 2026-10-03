"""Runtime configuration. Every value can be overridden by a TW_* env var or the repo-root .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tw import __version__

# src/tw/config.py -> src/tw -> src -> pipeline -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = REPO_ROOT / "pipeline"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TW_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(REPO_ROOT / 'var' / 'tw.db').as_posix()}"
    blob_dir: Path = REPO_ROOT / "var" / "blobs"
    report_dir: Path = REPO_ROOT / "var" / "reports"
    outlets_path: Path = REPO_ROOT / "outlets.yaml"
    data_dir: Path = REPO_ROOT / "data"

    contact_url: str = "https://activaterights.org"
    user_agent: str | None = None
    vantage: str = "local"

    default_rate_limit_seconds: float = 2.0
    http_timeout_seconds: float = 30.0
    http_max_attempts: int = 3
    http_backoff_base_seconds: float = 2.0
    http_max_redirects: int = 10
    http_max_bytes: int = 25_000_000
    http_max_retry_after_seconds: float = 300.0

    respect_retroactive_robots: bool = False

    # Listing entries dated older than this are stored in listing_entry but not enqueued for fetch.
    # Undated RSS / news-sitemap entries are always enqueued.
    capture_window_hours: float = 48.0
    max_index_children: int = 10
    fetch_job_backoff_minutes: float = 10.0

    archive_interval_auth_seconds: float = 5.0
    archive_interval_anon_seconds: float = 20.0
    archive_poll_seconds: float = 10.0
    archive_poll_timeout_seconds: float = 180.0
    archive_job_backoff_minutes: float = 30.0
    archive_max_attempts: int = 5

    ia_access_key: SecretStr | None = None
    ia_secret_key: SecretStr | None = None

    log_format: Literal["console", "json"] = "console"
    log_level: str = "INFO"

    @field_validator("blob_dir", "report_dir", "outlets_path", "data_dir")
    @classmethod
    def _relative_to_repo(cls, v: Path) -> Path:
        return v if v.is_absolute() else REPO_ROOT / v

    @field_validator("database_url")
    @classmethod
    def _sqlite_relative_to_repo(cls, v: str) -> str:
        prefix = "sqlite:///"
        if v.startswith(prefix) and v != "sqlite:///:memory:":
            p = Path(v[len(prefix):])
            if not p.is_absolute():
                return prefix + (REPO_ROOT / p).as_posix()
        return v

    @property
    def effective_user_agent(self) -> str:
        return self.user_agent or (
            f"TakedownWatch/{__version__} (+{self.contact_url}; news-archive integrity monitor)"
        )

    @property
    def robots_agent_token(self) -> str:
        return "TakedownWatch"


@lru_cache
def get_settings() -> Settings:
    return Settings()
