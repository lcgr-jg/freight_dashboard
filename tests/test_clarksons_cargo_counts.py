"""Pure helpers for Clarksons cargo-counts workbook (no network)."""

from datetime import date
from pathlib import Path

import pandas as pd

from freight.clarksons_cargo_counts import (
    decade_from_date,
    load_cargo_counts,
    meg_cargoes_comparable,
    parse_cargo_counts_sheet,
    ships_per_cargo,
)


def _mini_sheet() -> pd.DataFrame:
    # Row0 regions, row1 decades, then two months + average row
    rows = [
        [None, None, "MEG", None, None, None, None, "WAF", None, None, None],
        ["DAYS", "MONTH", "1st", "2nd", "3rd", "TTL", None, "1st", "2nd", "3rd", "TTL"],
        [31, date(2026, 1, 1), 40, 41, 42, 123, None, 9, 8, 7, 24],
        [28, date(2026, 2, 1), 30, 31, 32, 93, None, 5, 6, 7, 18],
        [None, None, 35.0, 36.0, 37.0, 108.0, None, 7.0, 7.0, 7.0, 21.0],
    ]
    return pd.DataFrame(rows)


def test_parse_cargo_counts_sheet() -> None:
    out = parse_cargo_counts_sheet(_mini_sheet(), sheet_year=2026)
    assert set(out["region"]) == {"MEG", "WAF"}
    meg_jan_ttl = out.loc[
        (out["month"] == "2026-01-01") & (out["region"] == "MEG") & (out["decade"] == "TTL"),
        "cargoes",
    ].iloc[0]
    assert meg_jan_ttl == 123
    # average row skipped (no month)
    assert out["month"].nunique() == 2


def test_relabel_stale_year_on_sheet() -> None:
    # Sheet tab 2025 but months printed as 2024 (Clarksons quirk).
    rows = [
        [None, None, "MEG", None, None, None],
        ["DAYS", "MONTH", "1st", "2nd", "3rd", "TTL"],
        [31, date(2024, 1, 1), 10, 11, 12, 33],
        [28, date(2024, 2, 1), 13, 14, 15, 42],
    ]
    out = parse_cargo_counts_sheet(pd.DataFrame(rows), sheet_year=2025)
    assert set(out["year"]) == {2025}
    assert bool(out["year_relabeled"].all())


def test_meg_comparable_adds_rsea() -> None:
    rows = [
        [None, None, "MEG/STS WCI", None, None, None, None, "RSEA", None, None, None],
        ["DAYS", "MONTH", "1st", "2nd", "3rd", "TTL", None, "1st", "2nd", "3rd", "TTL"],
        [31, date(2026, 3, 1), 22, 14, 13, 49, None, 1, 27, 13, 41],
    ]
    tidy = parse_cargo_counts_sheet(pd.DataFrame(rows))
    cmp_ = meg_cargoes_comparable(tidy)
    mar_ttl = cmp_.loc[(cmp_["month"] == "2026-03-01") & (cmp_["decade"] == "TTL")].iloc[0]
    assert mar_ttl["meg"] == 49
    assert mar_ttl["rsea"] == 41
    assert mar_ttl["meg_plus_rsea"] == 90


def test_ships_per_cargo_and_decade() -> None:
    assert decade_from_date(date(2026, 10, 5)) == "1st"
    assert decade_from_date(date(2026, 10, 15)) == "2nd"
    assert decade_from_date(date(2026, 10, 25)) == "3rd"
    cargoes = pd.DataFrame(
        {
            "month": pd.to_datetime(["2026-10-01", "2026-10-01"]),
            "decade": ["1st", "2nd"],
            "meg_plus_rsea": [40.0, 20.0],
        }
    )
    ships = pd.DataFrame(
        {
            "month": pd.to_datetime(["2026-10-01", "2026-10-01"]),
            "decade": ["1st", "2nd"],
            "ships": [80.0, 60.0],
        }
    )
    out = ships_per_cargo(cargoes, ships)
    assert abs(out.loc[out["decade"] == "1st", "ships_per_cargo"].iloc[0] - 2.0) < 1e-9


def test_seasonal_cargoes_masks_trailing_zeros() -> None:
    from freight.clarksons_cargo_counts import seasonal_cargoes

    rows = []
    # 2025 full year MEG TTL
    for m in range(1, 13):
        rows.append(
            {
                "month": pd.Timestamp(2025, m, 1),
                "year": 2025,
                "region": "MEG",
                "decade": "TTL",
                "cargoes": 100.0 + m,
                "is_aggregate": False,
            }
        )
    # 2026 through Oct, then zero placeholders
    for m, v in [(1, 130), (2, 134), (3, 90), (10, 82), (11, 0), (12, 0)]:
        rows.append(
            {
                "month": pd.Timestamp(2026, m, 1),
                "year": 2026,
                "region": "MEG",
                "decade": "TTL",
                "cargoes": float(v),
                "is_aggregate": False,
            }
        )
    df = pd.DataFrame(rows)
    # Need RSEA zeros for MEG+RSEA path — use MEG region directly
    out = seasonal_cargoes(df, region="MEG", decade="TTL")
    nov = out.loc[(out["year"] == 2026) & (out["cal_month"] == 11), "cargoes"]
    assert nov.isna().all()
    oct_ = out.loc[(out["year"] == 2026) & (out["cal_month"] == 10), "cargoes"].iloc[0]
    assert oct_ == 82


def test_load_real_workbook_if_present() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "broker_research"
        / "clarksons"
        / "CARGO COUNTS DATA.xlsx"
    )
    if not path.exists():
        return
    df = load_cargo_counts(path)
    assert df["year"].min() <= 2022
    assert "MEG" in set(df["region"])
    # 2026 should expose RSEA split
    y26 = df.loc[df["year"] == 2026]
    assert "RSEA" in set(y26["region"])
