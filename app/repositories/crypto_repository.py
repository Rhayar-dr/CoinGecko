"""Persistence logic for crypto history and monthly aggregates.

The repository is the only place that knows SQL. It exposes two operations:

* :meth:`upsert_history` — insert-or-update a daily row keyed on
  ``(coin_id, date)`` so re-running a date never creates duplicates;
* :meth:`recalculate_monthly_stats` — recompute MIN/MAX for the affected
  month from the committed daily rows and UPSERT it into
  ``crypto_monthly_stats``.

Both use PostgreSQL's ``INSERT ... ON CONFLICT DO UPDATE``.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import extract, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models import CryptoHistoryRow, CryptoMonthlyStatsRow
from app.models.crypto import CryptoHistory

logger = logging.getLogger(__name__)


class CryptoRepository:
    """Data-access object for the crypto tables. One instance per session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_history(self, record: CryptoHistory) -> None:
        """Insert or update the daily snapshot for ``record``.

        On conflict of ``(coin_id, date)`` the price, raw payload and
        ``updated_at`` are refreshed — so correcting a previously stored price
        is supported without duplicating rows.
        """
        stmt = pg_insert(CryptoHistoryRow).values(
            coin_id=record.coin_id,
            date=record.date,
            price_usd=record.price_usd,
            raw_json=record.raw_json,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_crypto_history_coin_date",
            set_={
                "price_usd": stmt.excluded.price_usd,
                "raw_json": stmt.excluded.raw_json,
                "updated_at": func.now(),
            },
        )
        self._session.execute(stmt)
        logger.info(
            "Database updated: crypto_history %s %s (price_usd=%s)",
            record.coin_id,
            record.date.isoformat(),
            record.price_usd,
        )

    def recalculate_monthly_stats(self, coin_id: str, on_date: date) -> None:
        """Recompute and UPSERT MIN/MAX USD price for ``on_date``'s month.

        MIN/MAX are computed from the committed ``crypto_history`` rows, which
        keeps the aggregate correct even when a stored price is later revised
        (an incremental LEAST/GREATEST merge could not lower a corrected max).
        NULL prices are ignored by the SQL aggregates.
        """
        year = on_date.year
        month = on_date.month

        min_price, max_price = self._session.execute(
            select(
                func.min(CryptoHistoryRow.price_usd),
                func.max(CryptoHistoryRow.price_usd),
            ).where(
                CryptoHistoryRow.coin_id == coin_id,
                extract("year", CryptoHistoryRow.date) == year,
                extract("month", CryptoHistoryRow.date) == month,
            )
        ).one()

        stmt = pg_insert(CryptoMonthlyStatsRow).values(
            coin_id=coin_id,
            year=year,
            month=month,
            min_price_usd=min_price,
            max_price_usd=max_price,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_crypto_monthly_coin_year_month",
            set_={
                "min_price_usd": stmt.excluded.min_price_usd,
                "max_price_usd": stmt.excluded.max_price_usd,
                "updated_at": func.now(),
            },
        )
        self._session.execute(stmt)
        logger.info(
            "Monthly stats updated: %s %04d-%02d min=%s max=%s",
            coin_id,
            year,
            month,
            min_price,
            max_price,
        )
