from datetime import date

import pytest

from scripts.reconcile_enrollment_p0_confirmed_date_2026 import (
    CONFIRM_TOKEN,
    SOURCE,
    YEAR,
    parse_confirmed_date,
)


def test_constants_are_scoped_and_explicit():
    assert YEAR == 2026
    assert CONFIRM_TOKEN == "RECONCILE-P0-CONFIRMED-DATE-2026"
    assert SOURCE == "repair:p0-enrollment-confirmed-date-2026"


def test_parse_confirmed_date_accepts_iso_2026():
    assert parse_confirmed_date("2026-01-15") == "2026-01-15"


@pytest.mark.parametrize("value", ["15/01/2026", "2025-01-15", "2027-01-15", ""])
def test_parse_confirmed_date_rejects_invalid_or_other_year(value):
    with pytest.raises(ValueError):
        parse_confirmed_date(value)


def test_confirmed_date_is_not_after_known_first_attendance_example():
    confirmed = date.fromisoformat(parse_confirmed_date("2026-01-15"))
    first_attendance = date.fromisoformat("2026-02-09")
    assert confirmed <= first_attendance
