"""Date parsing, validation and conversion helpers.

The application speaks ISO-8601 (``YYYY-MM-DD``) at its boundaries, while
CoinGecko's ``/coins/{id}/history`` endpoint expects ``dd-mm-yyyy``. All the
conversion and validation logic lives here so it can be unit-tested in
isolation and reused by every command.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from app.errors import InvalidDateError

ISO_FORMAT = "%Y-%m-%d"
COINGECKO_FORMAT = "%d-%m-%Y"


def parse_iso_date(value: str) -> date:
    """Parse an ISO-8601 date string, supporting the ``today``/``yesterday`` aliases.

    Raises:
        InvalidDateError: if the string is not a valid ``YYYY-MM-DD`` date.
    """
    if value is None:
        raise InvalidDateError("A date is required.")

    token = value.strip().lower()
    if token == "today":
        return today()
    if token == "yesterday":
        return yesterday()

    try:
        return datetime.strptime(value.strip(), ISO_FORMAT).date()
    except ValueError as exc:
        raise InvalidDateError(
            f"Invalid date {value!r}. Expected ISO-8601 format YYYY-MM-DD."
        ) from exc


def to_coingecko_format(value: date) -> str:
    """Convert a :class:`datetime.date` to CoinGecko's ``dd-mm-yyyy`` format."""
    return value.strftime(COINGECKO_FORMAT)


def to_iso(value: date) -> str:
    """Convert a :class:`datetime.date` to an ISO-8601 string."""
    return value.strftime(ISO_FORMAT)


def today() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def yesterday() -> date:
    """Return yesterday's date in UTC (used by the daily job / CRON)."""
    return today() - timedelta(days=1)


def date_range(start: date, end: date) -> Iterator[date]:
    """Yield every date from ``start`` to ``end`` inclusive.

    Raises:
        InvalidDateError: if ``start`` is after ``end``.
    """
    if start > end:
        raise InvalidDateError(f"start-date ({start}) must not be after end-date ({end}).")

    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
