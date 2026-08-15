"""Core orchestration service.

:meth:`CryptoService.process_date` is the single unit of work shared by every
command (``download``, ``daily`` and ``backfill``). It:

1. fetches the day's history from CoinGecko,
2. saves the raw JSON locally,
3. optionally persists the daily row to PostgreSQL and refreshes the month's
   MIN/MAX aggregate.

Collaborators (API client, file storage, database) are injected, so the
service can be tested with fakes and reused across commands without
duplicating logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.api.coingecko_client import CoinGeckoClient
from app.database.connection import Database
from app.models.crypto import CryptoHistory
from app.repositories.crypto_repository import CryptoRepository
from app.storage.file_storage import FileStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of processing a single coin/date."""

    coin_id: str
    date: date
    price_usd: float | None
    file_path: str
    persisted: bool


class CryptoService:
    """Coordinates API, file storage and database for one coin/date at a time."""

    def __init__(
        self,
        client: CoinGeckoClient,
        storage: FileStorage,
        database: Database | None = None,
    ) -> None:
        self._client = client
        self._storage = storage
        self._database = database

    def process_date(self, coin_id: str, on_date: date, persist: bool = False) -> ProcessResult:
        """Fetch, store and (optionally) persist one coin/date snapshot.

        Args:
            coin_id: CoinGecko coin identifier.
            on_date: the day to process.
            persist: when ``True``, UPSERT into PostgreSQL and refresh the
                monthly aggregate. Requires a configured database.
        """
        logger.info("Starting %s extraction for %s", coin_id, on_date.isoformat())

        payload = self._client.get_history(coin_id, on_date)
        record = CryptoHistory.from_api_response(coin_id, on_date, payload)

        if record.price_usd is None:
            logger.warning(
                "Missing expected fields: no USD price for %s on %s (raw payload still saved).",
                coin_id,
                on_date.isoformat(),
            )

        file_path = self._storage.save(coin_id, on_date, payload)

        persisted = False
        if persist:
            self._persist(record)
            persisted = True

        logger.info("Process finished successfully for %s on %s", coin_id, on_date.isoformat())
        return ProcessResult(
            coin_id=coin_id,
            date=on_date,
            price_usd=record.price_usd,
            file_path=str(file_path),
            persisted=persisted,
        )

    def _persist(self, record: CryptoHistory) -> None:
        if self._database is None:
            raise RuntimeError(
                "Persistence requested but no database is configured. "
                "Check your POSTGRES_* environment variables."
            )
        with self._database.session() as session:
            repo = CryptoRepository(session)
            repo.upsert_history(record)
            repo.recalculate_monthly_stats(record.coin_id, record.date)
