"""Domain-specific exception hierarchy.

Using explicit exception types (instead of bare ``ValueError`` / ``Exception``)
lets callers and the CLI distinguish, log and exit on the different failure
modes the exam calls out: invalid coin, invalid date, API/HTTP errors and
database errors.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application errors."""


class InvalidDateError(AppError):
    """The supplied date is malformed or outside the accepted range."""


class InvalidCoinError(AppError):
    """The requested coin id does not exist on CoinGecko."""


class CoinGeckoAPIError(AppError):
    """A transport/HTTP-level failure while talking to CoinGecko."""


class MissingFieldsError(AppError):
    """The API response did not contain the expected fields."""


class DatabaseError(AppError):
    """A failure while persisting to PostgreSQL."""
