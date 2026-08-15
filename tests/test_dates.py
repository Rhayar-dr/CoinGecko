"""Tests for date parsing, validation and conversion."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.errors import InvalidDateError
from app.utils.dates import (
    date_range,
    parse_iso_date,
    to_coingecko_format,
    to_iso,
    today,
    yesterday,
)


def test_parse_iso_date_valid():
    assert parse_iso_date("2017-12-30") == date(2017, 12, 30)


def test_parse_iso_date_aliases():
    assert parse_iso_date("today") == today()
    assert parse_iso_date("yesterday") == yesterday()
    assert parse_iso_date("YESTERDAY") == yesterday()


@pytest.mark.parametrize("bad", ["30-12-2017", "2017/12/30", "not-a-date", "2017-13-01", ""])
def test_parse_iso_date_invalid(bad):
    with pytest.raises(InvalidDateError):
        parse_iso_date(bad)


def test_iso_to_coingecko_conversion():
    # 2017-12-30 -> 30-12-2017 (this is the core exam conversion).
    assert to_coingecko_format(date(2017, 12, 30)) == "30-12-2017"


def test_to_iso():
    assert to_iso(date(2018, 1, 1)) == "2018-01-01"


def test_date_range_inclusive():
    start = date(2025, 1, 1)
    end = date(2025, 1, 3)
    assert list(date_range(start, end)) == [
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
    ]


def test_date_range_single_day():
    d = date(2025, 6, 15)
    assert list(date_range(d, d)) == [d]


def test_date_range_start_after_end_raises():
    with pytest.raises(InvalidDateError):
        list(date_range(date(2025, 1, 2), date(2025, 1, 1)))


def test_yesterday_is_one_day_before_today():
    assert today() - yesterday() == timedelta(days=1)
