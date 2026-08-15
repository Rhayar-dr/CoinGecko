"""Tests for the CoinGecko HTTP client (retries, error mapping, date format)."""

from __future__ import annotations

from datetime import date

import pytest
import requests

from app.api.coingecko_client import CoinGeckoClient
from app.config import CoinGeckoConfig
from app.errors import CoinGeckoAPIError, InvalidCoinError
from tests.conftest import FakeResponse, FakeSession


def _config(max_retries: int = 3) -> CoinGeckoConfig:
    return CoinGeckoConfig(
        base_url="https://api.coingecko.com/api/v3",
        api_key=None,
        api_key_header="x-cg-demo-api-key",
        timeout_seconds=1.0,
        max_retries=max_retries,
        backoff_seconds=0.0,  # no real sleeping in tests
    )


def test_get_history_success_and_date_conversion(bitcoin_payload):
    session = FakeSession([FakeResponse(200, json_body=bitcoin_payload)])
    client = CoinGeckoClient(_config(), session=session)

    result = client.get_history("bitcoin", date(2017, 12, 30))

    assert result["id"] == "bitcoin"
    # The request must send the CoinGecko dd-mm-yyyy date.
    assert session.calls[0]["params"]["date"] == "30-12-2017"
    assert session.calls[0]["url"].endswith("/coins/bitcoin/history")


def test_get_history_invalid_coin_raises():
    session = FakeSession([FakeResponse(404, text="coin not found")])
    client = CoinGeckoClient(_config(), session=session)

    with pytest.raises(InvalidCoinError):
        client.get_history("not-a-coin", date(2020, 1, 1))


def test_get_history_retries_on_429_then_succeeds(bitcoin_payload):
    session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(200, json_body=bitcoin_payload),
        ]
    )
    client = CoinGeckoClient(_config(), session=session)

    result = client.get_history("bitcoin", date(2017, 12, 30))
    assert result["id"] == "bitcoin"
    assert len(session.calls) == 2


def test_get_history_retries_on_timeout_then_succeeds(bitcoin_payload):
    session = FakeSession(
        [requests.Timeout("timed out"), FakeResponse(200, json_body=bitcoin_payload)]
    )
    client = CoinGeckoClient(_config(), session=session)

    result = client.get_history("bitcoin", date(2017, 12, 30))
    assert result["id"] == "bitcoin"


def test_get_history_gives_up_after_max_retries():
    session = FakeSession([FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    client = CoinGeckoClient(_config(max_retries=3), session=session)

    with pytest.raises(CoinGeckoAPIError):
        client.get_history("bitcoin", date(2020, 1, 1))
    assert len(session.calls) == 3
