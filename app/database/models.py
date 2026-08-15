"""SQLAlchemy ORM models — the PostgreSQL schema in code.

Two tables:

* ``crypto_history`` — one row per coin/day, with a unique ``(coin_id, date)``
  constraint that prevents duplicates and enables UPSERT.
* ``crypto_monthly_stats`` — aggregated MIN/MAX USD price per coin/year/month,
  unique on ``(coin_id, year, month)``.

The SQL in ``sql/001_create_tables.sql`` mirrors these definitions for
environments that prefer running migrations by hand.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class CryptoHistoryRow(Base):
    """Daily price snapshot for a coin."""

    __tablename__ = "crypto_history"
    __table_args__ = (UniqueConstraint("coin_id", "date", name="uq_crypto_history_coin_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    price_usd: Mapped[Optional[float]] = mapped_column(Numeric(30, 10), nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CryptoMonthlyStatsRow(Base):
    """Aggregated MIN/MAX USD price per coin/year/month."""

    __tablename__ = "crypto_monthly_stats"
    __table_args__ = (
        UniqueConstraint("coin_id", "year", "month", name="uq_crypto_monthly_coin_year_month"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    min_price_usd: Mapped[Optional[float]] = mapped_column(Numeric(30, 10), nullable=True)
    max_price_usd: Mapped[Optional[float]] = mapped_column(Numeric(30, 10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
