"""Application configuration loaded from environment variables.

Configuration is centralised in immutable dataclasses so the rest of the code
depends on plain values instead of reading ``os.environ`` directly. Secrets
(API keys, DB passwords) come exclusively from the environment / ``.env`` and
never live in source control.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load a local .env if present. Real environment variables always win.
load_dotenv(override=False)


def _get(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class CoinGeckoConfig:
    """Settings for the CoinGecko HTTP client."""

    base_url: str
    api_key: str | None
    api_key_header: str
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL connection settings."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        """SQLAlchemy connection URL (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""

    coingecko: CoinGeckoConfig
    database: DatabaseConfig
    data_dir: str
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build (and cache) the :class:`Settings` from the environment."""
    coingecko = CoinGeckoConfig(
        base_url=_get("COINGECKO_API_BASE_URL", "https://api.coingecko.com/api/v3").rstrip("/"),
        api_key=os.getenv("COINGECKO_API_KEY") or None,
        api_key_header=_get("COINGECKO_API_KEY_HEADER", "x-cg-demo-api-key"),
        timeout_seconds=float(_get("COINGECKO_TIMEOUT_SECONDS", "30")),
        max_retries=int(_get("COINGECKO_MAX_RETRIES", "3")),
        backoff_seconds=float(_get("COINGECKO_BACKOFF_SECONDS", "1.5")),
    )
    database = DatabaseConfig(
        host=_get("POSTGRES_HOST", "localhost"),
        port=int(_get("POSTGRES_PORT", "5432")),
        database=_get("POSTGRES_DB", "crypto"),
        user=_get("POSTGRES_USER", "crypto_user"),
        password=_get("POSTGRES_PASSWORD", ""),
    )
    return Settings(
        coingecko=coingecko,
        database=database,
        data_dir=_get("DATA_DIR", "data"),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
    )
