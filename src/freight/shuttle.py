"""Shuttle-trade tanker flags from the desk classification workbook."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def default_shuttle_path(repo_root: Path) -> Path:
    return repo_root / "data" / "shuttle_tankers_class.xlsx"


def load_shuttle_available(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> pd.DataFrame:
    """IMO → shuttle_available (bool). Uses only SHUTTLE_AVAILABLE (latest state)."""
    if path is None:
        if repo_root is None:
            raise ValueError("path or repo_root required")
        path = default_shuttle_path(repo_root)
    if not path.exists():
        return pd.DataFrame(columns=["imo", "shuttle_available"])

    df = pd.read_excel(path)
    cols = {c.lower().strip(): c for c in df.columns}
    imo_col = cols.get("imo")
    flag_col = cols.get("shuttle_available")
    if imo_col is None or flag_col is None:
        return pd.DataFrame(columns=["imo", "shuttle_available"])

    out = pd.DataFrame(
        {
            "imo": pd.to_numeric(df[imo_col], errors="coerce"),
            "shuttle_available": df[flag_col].map(_as_bool),
        }
    )
    out = out.dropna(subset=["imo"])
    out["imo"] = out["imo"].astype("int64")
    # One row per IMO; prefer True if duplicates disagree.
    out = out.groupby("imo", as_index=False)["shuttle_available"].max()
    return out


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "t"}
