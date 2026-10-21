"""Pure helpers for Kpler tape (no network)."""

from pathlib import Path

import pandas as pd

from freight.kpler import (
    _ensure_date_col,
    laden_ballast_ratio,
    parse_dotenv,
    parse_kpler_dates,
    seasonal_tonmiles,
    zscore,
)


def test_parse_dotenv(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("KPLER_EMAIL=a@b.c\n# comment\nAPI_KEY=secret\n", encoding="utf-8")
    cred = parse_dotenv(p)
    assert cred["KPLER_EMAIL"] == "a@b.c"
    assert cred["API_KEY"] == "secret"


def test_zscore_constant_is_nan() -> None:
    s = pd.Series([10.0] * 40)
    z = zscore(s, window=30)
    assert z.dropna().empty


def test_ensure_date_from_index() -> None:
    idx = pd.date_range("2026-01-01", periods=3, name="Date")
    df = pd.DataFrame({"Total": [1, 2, 3]}, index=idx)
    out = _ensure_date_col(df)
    assert "Date" in out.columns
    assert len(out) == 3


def test_parse_iso_week() -> None:
    s = parse_kpler_dates(pd.Series(["2026-W16"]))
    assert s.iloc[0] == pd.Timestamp("2026-04-13")  # ISO week 16 Monday


def test_laden_ballast_ratio() -> None:
    util = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "Loaded": [400.0, 0.0],
            "Ballast": [100.0, 0.0],
            "Unknown": [10.0, 10.0],
        }
    )
    out = laden_ballast_ratio(util)
    assert abs(out.iloc[0]["laden_ballast_ratio"] - 0.8) < 1e-9
    assert pd.isna(out.iloc[1]["laden_ballast_ratio"])


def test_enrich_broker_vs_kpler_eta() -> None:
    from freight.kpler import enrich_broker_vs_kpler_eta

    meg = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-10-01", "2026-10-01"]),
            "vessel_norm": ["ALPHA", "BETA"],
            "open_date": pd.to_datetime(["2026-10-20", "2026-10-05"]),
            "eta": pd.to_datetime(["2026-10-22", "2026-10-06"]),
            "eta_is_ppt": [False, False],
        }
    )
    ladder = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-10-01", "2026-10-01", "2026-10-01"]),
            "vessel_norm": ["ALPHA", "ALPHA", "BETA"],
            "matcher_eta_days": [15, 30, 7],
            "next_eta": pd.to_datetime(["2026-10-12", "2026-10-12", "2026-10-04"]),
        }
    )
    out = enrich_broker_vs_kpler_eta(meg, ladder, etas=(7, 15, 30))
    alpha = out.loc[out["vessel_norm"] == "ALPHA"].iloc[0]
    assert alpha["kpler_min_eta_window"] == 15
    assert bool(alpha["kpler_can_make_broker_open"])  # 15 <= 19 days
    assert alpha["kpler_in_fuj_eta7"] is False or alpha["kpler_in_fuj_eta7"] == False
    beta = out.loc[out["vessel_norm"] == "BETA"].iloc[0]
    assert beta["kpler_min_eta_window"] == 7
    assert bool(beta["kpler_can_make_broker_open"])


def test_enrich_meg_list_marks_live_not_pit() -> None:
    from freight.kpler import enrich_meg_list_kpler

    meg = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-10-01", "2026-10-02"]),
            "vessel": ["Alpha Star", "Alpha Star"],
            "vessel_norm": ["ALPHA STAR", "ALPHA STAR"],
            "is_tbn": [False, False],
        }
    )
    vessels = pd.DataFrame(
        {
            "vessel_norm": ["ALPHA STAR"],
            "vessel_imo": [123],
            "vessel_status": ["Active"],
            "vessel_dead_weight": [300000],
            "vessel_type": ["VLCC"],
            "vessel_build_year": [2015],
            "last_port_call_location_name": ["Fujairah"],
            "last_port_call_end": [pd.Timestamp("2026-09-28")],
            "next_destination_zone_name": ["Mideast Gulf"],
            "next destination eta": [pd.Timestamp("2026-10-05")],
            "vessel_availability_status": ["Open"],
            "vessel_availability_open": [pd.Timestamp("2026-10-02")],
            "Owners_names": ["Own"],
            "is_floating_storage": [False],
            "last_speed_kn": [12.0],
            "kpler_snapshot_at": [pd.Timestamp("2026-10-07")],
            "pit_available": [False],
        }
    )
    fx = pd.DataFrame(
        {
            "vessel_norm": ["ALPHA STAR"],
            "reported_date": [pd.Timestamp("2026-10-01")],
            "origin": ["Ras Tanura"],
            "destination": ["Ningbo"],
            "rate_usd": [10.0],
            "pit_available": [True],
        }
    )
    out = enrich_meg_list_kpler(meg, vessels, fx, None)
    assert not out["kpler_vessel_state_pit_available"].any()
    assert out["kpler_fixture_pit_available"].all()
    assert out["kpler_name_matched"].all()
    assert int(out.loc[out["as_of"] == "2026-10-01", "kpler_n_fixtures_near"].iloc[0]) == 1


def test_seasonal_tonmiles_band() -> None:
    rows = []
    for y in range(2020, 2026):
        for m in range(1, 13):
            rows.append({"Date": pd.Timestamp(y, m, 1), "ton_miles": float(y * 100 + m)})
    out = seasonal_tonmiles(pd.DataFrame(rows), as_of_year=2025, history_years=5)
    assert len(out["band"]) == 12
    assert out["band"]["y5_mean"].notna().all()
    assert 2025 in out["years"].columns
