"""Shared pytest fixtures and test doubles.

The doubles here let the API client, service and backfill layers be tested
without any real network or database access — the exam explicitly allows
mocking the CoinGecko response.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def bitcoin_payload() -> dict[str, Any]:
    """A realistic (trimmed) CoinGecko history payload for bitcoin."""
    with (FIXTURES / "bitcoin_2017-12-30.json").open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# HTTP test doubles
# --------------------------------------------------------------------------- #
class FakeResponse:
    """Minimal stand-in for :class:`requests.Response`."""

    def __init__(
        self,
        status_code: int = 200,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> dict[str, Any]:
        if self._json_body is None:
            raise ValueError("No JSON body")
        return self._json_body


class FakeSession:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params=None, timeout=None):  # noqa: ANN001
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# Expose helpers to tests importing from conftest.
__all__ = ["FakeResponse", "FakeSession", "requests"]
