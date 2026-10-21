"""Pure helpers for Clarksons MEG VLCC position lists (no network)."""

from datetime import date
from pathlib import Path

import pandas as pd

from freight.clarksons_meg_list import (
    diff_consecutive_lists,
    is_tbn,
    list_snapshot_sizes,
    normalize_vessel_name,
    parse_as_of_from_filename,
    parse_meg_position_xlsx,
)


def test_parse_as_of_from_filename() -> None:
    p = Path("CLARKSONS MEG VLCC POSITION 25 SEP 2026.xlsx")
    assert parse_as_of_from_filename(p) == date(2026, 9, 25)


def test_normalize_and_tbn() -> None:
    assert normalize_vessel_name("  Front  Prince ") == "FRONT PRINCE"
    # Period spacing: Clarksons vs Kpler
    assert normalize_vessel_name("C. GALAXY") == normalize_vessel_name("C.GALAXY") == "C GALAXY"
    assert normalize_vessel_name("MARIA A. ANGELICOUSSIS") == normalize_vessel_name(
        "MARIA A.ANGELICOUSSIS"
    )
    assert is_tbn("MEG TBN")
    assert not is_tbn("Front Prince")


def test_classify_comment_exit() -> None:
    from freight.clarksons_meg_list import classify_comment_exit

    assert classify_comment_exit("HOLD OVER 18") == "on_hold"
    assert classify_comment_exit("SUBS") == "on_subs"
    assert classify_comment_exit("PUSHED") == "pushed"
    assert classify_comment_exit("CANCELLED") == "cancelled"
    assert classify_comment_exit(None) is None
    assert classify_comment_exit("") is None


def test_annotate_exits_priority() -> None:
    from freight.clarksons_meg_list import annotate_exits, diff_consecutive_lists

    meg = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-10-01", "2026-10-01", "2026-10-02"]),
            "vessel": ["A", "B", "B"],
            "vessel_norm": ["A", "B", "B"],
            "is_tbn": [False, False, False],
            "comments": ["SUBS", "HOLD", "x"],
            "position": ["YOSU", "NINGBO", "NINGBO"],
            "open_date": pd.to_datetime(["2026-10-02"] * 3),
            "eta": pd.to_datetime(["2026-10-05"] * 3),
            "eta_is_ppt": [False, False, False],
            "dwt": [300000, 300000, 300000],
            "owner": ["x", "y", "y"],
        }
    )
    # Force a remove of A between days via diff on two-day frame with only B on day 2
    meg2 = pd.concat(
        [
            meg.iloc[:2],
            meg.iloc[[2]].assign(vessel="B", vessel_norm="B"),
        ],
        ignore_index=True,
    )
    ev = diff_consecutive_lists(meg2)
    exits = annotate_exits(meg2, ev, fixtures=None)
    assert len(exits) == 1
    assert exits.iloc[0]["exit_reason"] == "on_subs"
    assert exits.iloc[0]["exit_confidence"] == "high"


def _tiny_xlsx(tmp_path: Path) -> Path:
    # Minimal workbook matching Clarksons layout (header at row 0, cols 2–11).
    rows = [
        [None, None, "ETA", "VESSEL", "DWT", "BLT", "DRAFT", "COIL", "POSITION", "OPEN", "OWNER", "COMMENTS"],
        [None, None, date(2026, 10, 1), "Alpha Star", 300000, date(2015, 1, 1), 20, None, "MEG", date(2026, 10, 2), "OwnA", "open"],
        [None, None, "PPT", "Beta Moon", 310000, date(2016, 1, 1), 21, None, "FUJ", date(2026, 10, 3), "OwnB", "on subs"],
        [None, None, date(2026, 10, 4), "Gamma TBN", 300000, None, None, None, "MEG", None, None, None],
    ]
    path = tmp_path / "CLARKSONS MEG VLCC POSITION 01 OCT 2026.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False, header=False, engine="openpyxl")
    return path


def test_parse_meg_position_xlsx(tmp_path: Path) -> None:
    df = parse_meg_position_xlsx(_tiny_xlsx(tmp_path))
    assert len(df) == 3
    assert df.loc[df["vessel"] == "Alpha Star", "as_of"].iloc[0].date() == date(2026, 10, 1)
    assert bool(df.loc[df["vessel"] == "Beta Moon", "eta_is_ppt"].iloc[0])
    assert bool(df.loc[df["vessel"] == "Gamma TBN", "is_tbn"].iloc[0])


def test_diff_and_sizes(tmp_path: Path) -> None:
    # Day 1
    p1 = tmp_path / "CLARKSONS MEG VLCC POSITION 01 OCT 2026.xlsx"
    rows1 = [
        [None, None, "ETA", "VESSEL", "DWT", "BLT", "DRAFT", "COIL", "POSITION", "OPEN", "OWNER", "COMMENTS"],
        [None, None, date(2026, 10, 1), "Alpha Star", 300000, None, None, None, "MEG", date(2026, 10, 2), "A", "x"],
        [None, None, date(2026, 10, 1), "Beta Moon", 310000, None, None, None, "FUJ", date(2026, 10, 2), "B", "y"],
    ]
    pd.DataFrame(rows1).to_excel(p1, index=False, header=False, engine="openpyxl")
    # Day 2: Beta removed, Gamma added, Alpha position changed
    p2 = tmp_path / "CLARKSONS MEG VLCC POSITION 02 OCT 2026.xlsx"
    rows2 = [
        [None, None, "ETA", "VESSEL", "DWT", "BLT", "DRAFT", "COIL", "POSITION", "OPEN", "OWNER", "COMMENTS"],
        [None, None, date(2026, 10, 2), "Alpha Star", 300000, None, None, None, "SUEZ", date(2026, 10, 3), "A", "x"],
        [None, None, date(2026, 10, 2), "Gamma Ray", 320000, None, None, None, "MEG", date(2026, 10, 3), "C", "z"],
    ]
    pd.DataFrame(rows2).to_excel(p2, index=False, header=False, engine="openpyxl")
    from freight.clarksons_meg_list import load_all_meg_lists

    all_df = load_all_meg_lists(tmp_path)
    sizes = list_snapshot_sizes(all_df)
    assert list(sizes["n_vessels"]) == [2, 2]
    ev = diff_consecutive_lists(all_df)
    assert set(ev.loc[ev["event"] == "added", "vessel_norm"]) == {"GAMMA RAY"}
    assert set(ev.loc[ev["event"] == "removed", "vessel_norm"]) == {"BETA MOON"}
    alpha = ev.loc[(ev["vessel_norm"] == "ALPHA STAR") & (ev["event"] == "changed")]
    assert len(alpha) == 1
    assert "position" in alpha.iloc[0]["changed_fields"]
