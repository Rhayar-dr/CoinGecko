"""HTTP client for the CoinGecko API.

Responsibilities (single responsibility principle):

* build the ``/coins/{id}/history`` request, converting the ISO date to the
  ``dd-mm-yyyy`` format the API expects;
* attach the optional API key header;
* handle transient failures — timeouts, HTTP 429 and 5xx — with bounded
  retries and exponential backoff, honouring ``Retry-After``;
* translate transport/HTTP outcomes into the application's exception types.

The underlying :class:`requests.Session` is injected, which keeps the client
easy to unit-test without real network access.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import requests

from app.config import CoinGeckoConfig
from app.errors import CoinGeckoAPIError, InvalidCoinError
from app.utils.dates import to_coingecko_format

logger = logging.getLogger(__name__)

# HTTP statuses that are worth retrying (transient server / rate-limit issues).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class CoinGeckoClient:
    """Thin, retrying wrapper around the CoinGecko REST API."""

    def __init__(self, config: CoinGeckoConfig, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()

        headers = {"Accept": "application/json"}
        if config.api_key:
            headers[config.api_key_header] = config.api_key
        self._session.headers.update(headers)

    def get_history(self, coin_id: str, on_date: date) -> dict[str, Any]:
        """Fetch the historical snapshot for ``coin_id`` on ``on_date``.

        Args:
            coin_id: CoinGecko coin identifier, e.g. ``"bitcoin"``.
            on_date: the day to fetch (converted internally to ``dd-mm-yyyy``).

        Returns:
            The parsed JSON body as a dict.

        Raises:
            InvalidCoinError: the coin id was rejected (HTTP 404).
            CoinGeckoAPIError: any other transport or HTTP failure.
        """
        cg_date = to_coingecko_format(on_date)
        url = f"{self._config.base_url}/coins/{coin_id}/history"
        params = {"date": cg_date, "localization": "false"}

        logger.info("Calling CoinGecko for %s on %s", coin_id, on_date.isoformat())
        response = self._request_with_retries(url, params, coin_id)

        try:
            payload = response.json()
        except ValueError as exc:  # malformed JSON
            raise CoinGeckoAPIError(
                f"CoinGecko returned a non-JSON response for {coin_id} {on_date}."
            ) from exc

        logger.info("Response received successfully for %s on %s", coin_id, on_date.isoformat())
        return payload

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _request_with_retries(
        self, url: str, params: dict[str, str], coin_id: str
    ) -> requests.Response:
        last_exc: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                response = self._session.get(
                    url, params=params, timeout=self._config.timeout_seconds
                )
            except requests.Timeout as exc:
                last_exc = exc
                logger.warning(
                    "API timeout for %s (attempt %d/%d)", coin_id, attempt, self._config.max_retries
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "HTTP error for %s (attempt %d/%d): %s",
                    coin_id,
                    attempt,
                    self._config.max_retries,
                    exc,
                )
            else:
                if response.status_code == 404:
                    raise InvalidCoinError(f"Invalid coin id: {coin_id!r} (HTTP 404).")
                if response.status_code in _RETRYABLE_STATUS:
                    last_exc = CoinGeckoAPIError(
                        f"CoinGecko returned HTTP {response.status_code} for {coin_id}."
                    )
                    self._sleep_before_retry(attempt, response)
                    continue
                if not response.ok:
                    raise CoinGeckoAPIError(
                        f"CoinGecko returned HTTP {response.status_code} for {coin_id}: "
                        f"{response.text[:200]}"
                    )
                return response

            # We only reach here after a caught exception -> back off and retry.
            if attempt < self._config.max_retries:
                self._sleep_before_retry(attempt, None)

        raise CoinGeckoAPIError(
            f"CoinGecko request for {coin_id} failed after " f"{self._config.max_retries} attempts."
        ) from last_exc

    def _sleep_before_retry(self, attempt: int, response: requests.Response | None) -> None:
        """Sleep with exponential backoff, honouring ``Retry-After`` when present."""
        delay = self._config.backoff_seconds * (2 ** (attempt - 1))
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass  # non-numeric Retry-After (HTTP-date) -> keep backoff
            if response.status_code == 429:
                logger.warning("Rate limited (HTTP 429); backing off %.1fs", delay)
        time.sleep(delay)
