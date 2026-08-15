"""Tests for the core service and backfill orchestration using fakes."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.errors import CoinGeckoAPIError
from app.services.backfill_service import BackfillService
from app.services.crypto_service import CryptoService
from app.storage.file_storage import FileStorage


class FakeClient:
    """Returns a canned payload, or raises for specific dates."""

    def __init__(self, payload: dict[str, Any], fail_dates: list[date] | None = None) -> None:
        self._payload = payload
        self._fail_dates = set(fail_dates or [])
        self.requested: list[date] = []

    def get_history(self, coin_id: str, on_date: date) -> dict[str, Any]:
        self.requested.append(on_date)
        if on_date in self._fail_dates:
            raise CoinGeckoAPIError(f"boom for {on_date}")
        return self._payload


def test_process_date_saves_file_and_extracts_price(tmp_path, bitcoin_payload):
    client = FakeClient(bitcoin_payload)
    storage = FileStorage(str(tmp_path))
    service = CryptoService(client=client, storage=storage)

    result = service.process_date("bitcoin", date(2017, 12, 30), persist=False)

    assert result.price_usd == pytest.approx(14156.6)
    assert result.persisted is False
    saved = tmp_path / "bitcoin" / "bitcoin_2017-12-30.json"
    assert saved.exists()


def test_process_date_persist_without_db_raises(tmp_path, bitcoin_payload):
    service = CryptoService(FakeClient(bitcoin_payload), FileStorage(str(tmp_path)), database=None)
    with pytest.raises(RuntimeError):
        service.process_date("bitcoin", date(2017, 12, 30), persist=True)


def test_backfill_processes_all_dates(tmp_path, bitcoin_payload):
    client = FakeClient(bitcoin_payload)
    service = CryptoService(client=client, storage=FileStorage(str(tmp_path)))
    backfill = BackfillService(service)

    summary = backfill.run("bitcoin", date(2025, 1, 1), date(2025, 1, 5), persist=False)

    assert summary.total == 5
    assert summary.succeeded == 5
    assert summary.failure_count == 0
    assert len(client.requested) == 5


def test_backfill_records_failures_without_aborting(tmp_path, bitcoin_payload):
    client = FakeClient(bitcoin_payload, fail_dates=[date(2025, 1, 3)])
    service = CryptoService(client=client, storage=FileStorage(str(tmp_path)))
    backfill = BackfillService(service)

    summary = backfill.run("bitcoin", date(2025, 1, 1), date(2025, 1, 5), persist=False)

    assert summary.succeeded == 4
    assert summary.failure_count == 1
    assert "2025-01-03" in summary.failed


def test_backfill_concurrent_processes_all_dates(tmp_path, bitcoin_payload):
    client = FakeClient(bitcoin_payload)
    service = CryptoService(client=client, storage=FileStorage(str(tmp_path)))
    backfill = BackfillService(service)

    summary = backfill.run("bitcoin", date(2025, 1, 1), date(2025, 1, 10), persist=False, workers=4)

    assert summary.succeeded == 10
    assert summary.total == 10
