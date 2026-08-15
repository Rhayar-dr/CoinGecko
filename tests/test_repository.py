"""Integration tests for the repository (UPSERT + monthly MIN/MAX).

These require a real PostgreSQL (the code relies on the postgresql dialect:
JSONB and ``INSERT ... ON CONFLICT``). They are skipped automatically when no
database is reachable, so the rest of the suite runs anywhere.

To run them, point ``TEST_DATABASE_URL`` at a throwaway database, e.g.::

    docker compose up -d postgres
    export TEST_DATABASE_URL=postgresql+psycopg2://crypto_user:change_me@localhost:5432/crypto
    pytest tests/test_repository.py
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from app.models.crypto import CryptoHistory
from app.repositories.crypto_repository import CryptoRepository

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database.models import Base  # noqa: E402

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("Set TEST_DATABASE_URL to run repository integration tests.")
    try:
        eng = create_engine(TEST_DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crypto_history, crypto_monthly_stats RESTART IDENTITY"))
    sess = Session()
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()


def _record(price, day=10):
    return CryptoHistory(
        coin_id="bitcoin",
        date=date(2026, 8, day),
        price_usd=price,
        raw_json={"id": "bitcoin", "market_data": {"current_price": {"usd": price}}},
    )


def test_upsert_is_idempotent(session):
    repo = CryptoRepository(session)
    repo.upsert_history(_record(100.0))
    repo.upsert_history(_record(100.0))
    session.flush()

    count = session.execute(text("SELECT count(*) FROM crypto_history")).scalar_one()
    assert count == 1


def test_upsert_updates_existing_price(session):
    repo = CryptoRepository(session)
    repo.upsert_history(_record(100.0))
    repo.upsert_history(_record(150.0))
    session.flush()

    price = session.execute(text("SELECT price_usd FROM crypto_history")).scalar_one()
    assert float(price) == 150.0


def test_monthly_min_max_recomputed(session):
    repo = CryptoRepository(session)
    for day, price in [(10, 100.0), (11, 250.0), (12, 175.0)]:
        rec = _record(price, day=day)
        repo.upsert_history(rec)
        repo.recalculate_monthly_stats(rec.coin_id, rec.date)
    session.flush()

    row = session.execute(
        text(
            "SELECT min_price_usd, max_price_usd FROM crypto_monthly_stats "
            "WHERE coin_id='bitcoin' AND year=2026 AND month=8"
        )
    ).one()
    assert float(row[0]) == 100.0
    assert float(row[1]) == 250.0


def test_monthly_max_lowered_after_correction(session):
    """Correcting the highest price down must lower the monthly max (full recompute)."""
    repo = CryptoRepository(session)
    for day, price in [(10, 100.0), (11, 250.0)]:
        rec = _record(price, day=day)
        repo.upsert_history(rec)
        repo.recalculate_monthly_stats(rec.coin_id, rec.date)

    # Correct day 11 down to 120.
    corrected = _record(120.0, day=11)
    repo.upsert_history(corrected)
    repo.recalculate_monthly_stats(corrected.coin_id, corrected.date)
    session.flush()

    row = session.execute(
        text("SELECT max_price_usd FROM crypto_monthly_stats WHERE coin_id='bitcoin'")
    ).scalar_one()
    assert float(row) == 120.0
