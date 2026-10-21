"""Pure tests for shuttle / sanctions / noc / tonnage_supply helpers."""

from pathlib import Path

import pandas as pd

from freight.noc import is_noc_owner, load_noc_aliases, attach_noc_flag
from freight.sanctions import attach_sanction_flags, filter_by_sanction_view
from freight.shuttle import load_shuttle_available, _as_bool
from freight.tonnage_supply import (
    attach_position_age,
    derive_distance_nm,
    derive_eta_days,
    filter_by_ais_dark_view,
    format_position_age,
    position_age_minutes,
    proximity_bucket,
    approx_positions,
)


def test_as_bool() -> None:
    assert _as_bool(True) is True
    assert _as_bool("yes") is True
    assert _as_bool(0) is False
    assert _as_bool(None) is False


def test_load_shuttle(tmp_path: Path) -> None:
    path = tmp_path / "shuttle.xlsx"
    pd.DataFrame(
        {
            "IMO": [111, 222, 111],
            "SHUTTLE_AVAILABLE": [True, False, False],
            "WAS_SHUTTLE": [1, 1, 1],
        }
    ).to_excel(path, index=False)
    out = load_shuttle_available(path)
    assert set(out.columns) == {"imo", "shuttle_available"}
    # duplicate IMO prefers True
    assert bool(out.loc[out["imo"] == 111, "shuttle_available"].iloc[0]) is True
    assert bool(out.loc[out["imo"] == 222, "shuttle_available"].iloc[0]) is False


def test_sanctions_filter(tmp_path: Path) -> None:
    iran = tmp_path / "ofac_iran_vessels_history.csv"
    sdn = tmp_path / "ofac_sdn_vessels_2026-01-01.csv"
    pd.DataFrame({"imo": [100, 200]}).to_csv(iran, index=False)
    pd.DataFrame({"imo": [200, 300]}).to_csv(sdn, index=False)
    df = pd.DataFrame({"imo": [100, 200, 300, 400], "vessel": list("ABCD")})
    flagged = attach_sanction_flags(df, vc_root=tmp_path)
    assert flagged.loc[flagged["imo"] == 100, "sanctioned_iran"].iloc[0]
    assert flagged.loc[flagged["imo"] == 200, "sanctioned_any"].iloc[0]
    assert flagged.loc[flagged["imo"] == 400, "sanctioned_any"].iloc[0] == False
    assert len(filter_by_sanction_view(flagged, "sanctioned")) == 3
    assert len(filter_by_sanction_view(flagged, "clean")) == 1
    assert len(filter_by_sanction_view(flagged, "all")) == 4


def test_noc_aliases_from_repo() -> None:
    repo = Path(__file__).resolve().parents[1]
    aliases = load_noc_aliases(repo_root=repo)
    assert "ADNOC" in aliases
    assert is_noc_owner("ADNOC Shipping", aliases)
    assert not is_noc_owner("Random Tankers", aliases)
    df = attach_noc_flag(pd.DataFrame({"owner": ["KOTC", "Foo"]}), aliases=aliases)
    assert bool(df.iloc[0]["is_noc"]) is True
    assert bool(df.iloc[1]["is_noc"]) is False


def test_proximity_and_distance() -> None:
    eta = pd.Series(pd.to_datetime(["2026-10-14", "2026-10-16", "2026-10-20"]))
    # Freeze as_of so buckets are stable
    days = derive_eta_days(eta, as_of=pd.Timestamp("2026-10-13"))
    assert list(days.astype(int)) == [1, 3, 7]
    assert list(proximity_bucket(days)) == ["0-2 days", "2-4 days", "4-7 days"]
    dist = derive_distance_nm(days, 11)
    assert dist.iloc[0] == 1 * 11 * 24


def test_approx_positions() -> None:
    df = pd.DataFrame(
        {
            "current_sea": ["Persian Gulf", "Unknown Sea"],
            "last_port": [None, "Fujairah"],
        }
    )
    out = approx_positions(df)
    assert out.loc[0, "latitude"] is not None
    assert out.loc[1, "latitude"] is not None


def test_position_age_and_dark_filter() -> None:
    assert format_position_age(45) == "45m"
    assert format_position_age(3 * 60 + 12) == "3h 12m"
    assert format_position_age(2 * 24 * 60 + 5 * 60) == "2d 5h"
    as_of = pd.Timestamp("2026-10-13 12:00:00")
    last = pd.Series(
        [
            "2026-10-13 11:15:00+00:00",  # 45m
            "2026-09-01 12:00:00+00:00",  # >> 10d
            None,
        ]
    )
    mins = position_age_minutes(last, as_of=as_of)
    assert abs(mins.iloc[0] - 45) < 1
    assert mins.iloc[1] > 10 * 24 * 60
    assert pd.isna(mins.iloc[2])
    df = pd.DataFrame({"last_seen": last, "vessel": list("ABC")})
    aged = attach_position_age(df, dark_days=10, as_of=as_of)
    assert bool(aged.iloc[0]["is_ais_dark"]) is False
    assert bool(aged.iloc[1]["is_ais_dark"]) is True
    assert bool(aged.iloc[2]["is_ais_dark"]) is False  # unknown ≠ dark
    assert len(filter_by_ais_dark_view(aged, "non_dark")) == 2
    assert len(filter_by_ais_dark_view(aged, "all")) == 3
