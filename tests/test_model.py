"""Tests for the domain model and price extraction."""

from __future__ import annotations

from datetime import date

import pytest

from app.errors import MissingFieldsError
from app.models.crypto import CryptoHistory


def test_from_api_response_extracts_price(bitcoin_payload):
    record = CryptoHistory.from_api_response("bitcoin", date(2017, 12, 30), bitcoin_payload)
    assert record.coin_id == "bitcoin"
    assert record.date == date(2017, 12, 30)
    assert record.price_usd == pytest.approx(14156.6)
    assert record.raw_json == bitcoin_payload


def test_from_api_response_missing_market_data_yields_none_price():
    payload = {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}
    record = CryptoHistory.from_api_response("bitcoin", date(2013, 1, 1), payload)
    assert record.price_usd is None


def test_from_api_response_malformed_payload_raises():
    with pytest.raises(MissingFieldsError):
        CryptoHistory.from_api_response("bitcoin", date(2020, 1, 1), {})
