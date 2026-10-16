import datetime as dt

import pytest

from app.services.analytics import _parse_date_cell


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-03-15", dt.date(2026, 3, 15)),
        ("15/03/2026", dt.date(2026, 3, 15)),  # DD/MM tried before MM/DD
        ("03/25/2026", dt.date(2026, 3, 25)),  # unambiguous — day 25 forces MM/DD
        ("15-03-2026", dt.date(2026, 3, 15)),
        ("2026/03/15", dt.date(2026, 3, 15)),
        ("15 March 2026", dt.date(2026, 3, 15)),
        ("15 march 2026", dt.date(2026, 3, 15)),  # case-insensitive
        ("15 MARCH 2026", dt.date(2026, 3, 15)),
        ("15 Mar 2026", dt.date(2026, 3, 15)),
        ("March 15, 2026", dt.date(2026, 3, 15)),
        ("Mar 15, 2026", dt.date(2026, 3, 15)),
        ("March 15 2026", dt.date(2026, 3, 15)),
        ("Mar 15 2026", dt.date(2026, 3, 15)),
    ],
)
def test_parses_every_supported_format(raw: str, expected: dt.date) -> None:
    assert _parse_date_cell(raw) == expected


def test_strips_surrounding_whitespace() -> None:
    assert _parse_date_cell("  15 March 2026  ") == dt.date(2026, 3, 15)


@pytest.mark.parametrize(
    "raw",
    [
        "not a date",
        "",
        "32/13/2026",  # no valid day/month in any order
        "15th of March 2026",  # ordinal suffix not supported
        "2026-13-01",  # invalid month
    ],
)
def test_unparseable_values_return_none_rather_than_raising(raw: str) -> None:
    assert _parse_date_cell(raw) is None


def test_abbreviated_month_format_does_not_accept_a_full_month_name() -> None:
    # %b (abbreviated) and %B (full) are tried as distinct formats — a
    # full name should still parse overall (via the %B entry), but this
    # pins down that %b itself isn't silently lenient in a way that could
    # mask a format-list ordering bug.
    assert _parse_date_cell("15 March 2026") == dt.date(2026, 3, 15)
