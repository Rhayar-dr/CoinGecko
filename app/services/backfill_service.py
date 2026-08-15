"""Backfill service — process a range of dates, optionally concurrently.

Reuses :meth:`CryptoService.process_date` for every day in the range, so daily
and historical processing share exactly the same logic. Concurrency is bounded
by ``workers``: with ``workers == 1`` dates run sequentially; with more, a
:class:`ThreadPoolExecutor` runs up to ``workers`` requests at a time (I/O-bound
HTTP work, so threads are a good fit while respecting a configurable limit).

Per-date progress and failures are logged; one failing date does not abort the
whole run — the summary reports how many succeeded and which failed.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date

from app.errors import AppError
from app.services.crypto_service import CryptoService
from app.utils.dates import date_range

logger = logging.getLogger(__name__)


@dataclass
class BackfillSummary:
    """Aggregate outcome of a backfill run."""

    coin_id: str
    total: int
    succeeded: int = 0
    failed: dict[str, str] = field(default_factory=dict)  # ISO date -> error message

    @property
    def failure_count(self) -> int:
        return len(self.failed)


class BackfillService:
    """Runs :meth:`CryptoService.process_date` over an inclusive date range."""

    def __init__(self, service: CryptoService) -> None:
        self._service = service

    def run(
        self,
        coin_id: str,
        start: date,
        end: date,
        persist: bool = False,
        workers: int = 1,
    ) -> BackfillSummary:
        dates: list[date] = list(date_range(start, end))
        summary = BackfillSummary(coin_id=coin_id, total=len(dates))
        logger.info(
            "Starting backfill for %s: %s -> %s (%d days, workers=%d)",
            coin_id,
            start.isoformat(),
            end.isoformat(),
            len(dates),
            max(1, workers),
        )

        if workers <= 1:
            for current in dates:
                self._run_one(coin_id, current, persist, summary)
        else:
            self._run_concurrent(coin_id, dates, persist, workers, summary)

        logger.info(
            "Backfill finished for %s: %d/%d succeeded, %d failed",
            coin_id,
            summary.succeeded,
            summary.total,
            summary.failure_count,
        )
        return summary

    # ------------------------------------------------------------------ #
    def _run_one(
        self, coin_id: str, current: date, persist: bool, summary: BackfillSummary
    ) -> None:
        try:
            self._service.process_date(coin_id, current, persist=persist)
            summary.succeeded += 1
        except AppError as exc:
            logger.error("Backfill failed for %s on %s: %s", coin_id, current.isoformat(), exc)
            summary.failed[current.isoformat()] = str(exc)

    def _run_concurrent(
        self,
        coin_id: str,
        dates: list[date],
        persist: bool,
        workers: int,
        summary: BackfillSummary,
    ) -> None:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._service.process_date, coin_id, current, persist): current
                for current in dates
            }
            for future in as_completed(futures):
                current = futures[future]
                try:
                    future.result()
                    summary.succeeded += 1
                except AppError as exc:
                    logger.error(
                        "Backfill failed for %s on %s: %s", coin_id, current.isoformat(), exc
                    )
                    summary.failed[current.isoformat()] = str(exc)
