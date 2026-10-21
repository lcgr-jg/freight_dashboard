"""ICE monthly strip parsing — no Snowflake."""

from datetime import date

from freight.ice import ice_contract_code, last_trading_day, parse_monthly_strip


def test_parse_oct26():
    assert parse_monthly_strip("Oct26") == date(2026, 10, 1)


def test_parse_dated_strip_rejected():
    assert parse_monthly_strip("Oct-05-26") is None


def test_ice_code_v6():
    assert ice_contract_code(date(2026, 10, 1)) == "V6"


def test_december_ltd():
    assert last_trading_day(date(2026, 12, 1)) == date(2026, 12, 24)


def test_parse_dated():
    from freight.ice import parse_dated_strip

    assert parse_dated_strip("Oct-05-26") == date(2026, 10, 5)
