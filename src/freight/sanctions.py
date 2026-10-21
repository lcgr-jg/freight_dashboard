"""OFAC vessel sanctions flags — same files as vessel_crossing/polygon_tracker."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def resolve_vessel_crossing_root(repo_root: Path) -> Path:
    """freight_dashboard sits next to vessel_crossing under Coding/."""
    sibling = repo_root.parent / "vessel_crossing"
    if sibling.is_dir():
        return sibling
    return repo_root / "vessel_crossing"


def ofac_iran_path(vc_root: Path) -> Path:
    return vc_root / "ofac_iran_vessels_history.csv"


def ofac_sdn_path(vc_root: Path) -> Path:
    files = sorted(vc_root.glob("ofac_sdn_vessels_*.csv"))
    if files:
        return files[-1]
    return vc_root / "ofac_sdn_vessels_2026-07-13.csv"


def _normalize_imo(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _imo_set_from_csv(path: Path) -> set[int]:
    if not path.exists():
        return set()
    df = pd.read_csv(path)
    col = "imo" if "imo" in df.columns else df.columns[0]
    imos = _normalize_imo(df[col]).dropna().astype(int)
    return set(imos.tolist())


def ofac_imo_sets(vc_root: Path) -> tuple[set[int], set[int]]:
    """Return (iran_imos, sdn_imos)."""
    return _imo_set_from_csv(ofac_iran_path(vc_root)), _imo_set_from_csv(ofac_sdn_path(vc_root))


def attach_sanction_flags(df: pd.DataFrame, *, imo_col: str = "imo", vc_root: Path) -> pd.DataFrame:
    """Add sanctioned_iran / sanctioned_sdn / sanctioned_any / sanctioned_label."""
    out = df.copy()
    iran, sdn = ofac_imo_sets(vc_root)
    imos = pd.to_numeric(out[imo_col], errors="coerce")
    out["sanctioned_iran"] = imos.isin(iran)
    out["sanctioned_sdn"] = imos.isin(sdn)
    out["sanctioned_any"] = out["sanctioned_iran"] | out["sanctioned_sdn"]
    out["sanctioned_label"] = out.apply(_sanction_label, axis=1)
    return out


def _sanction_label(row: pd.Series) -> str:
    parts: list[str] = []
    if bool(row.get("sanctioned_iran")):
        parts.append("Iran")
    if bool(row.get("sanctioned_sdn")):
        parts.append("SDN")
    return ", ".join(parts) if parts else ""


def filter_by_sanction_view(df: pd.DataFrame, view: str) -> pd.DataFrame:
    """view: all | sanctioned | clean (default all)."""
    key = (view or "all").strip().lower()
    if key == "all" or "sanctioned_any" not in df.columns:
        return df
    mask = df["sanctioned_any"].fillna(False).astype(bool)
    if key == "sanctioned":
        return df.loc[mask].copy()
    if key == "clean":
        return df.loc[~mask].copy()
    raise ValueError(f"sanction view must be all|sanctioned|clean, got {view!r}")
