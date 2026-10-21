"""Vessel list table helpers."""

from __future__ import annotations

import pandas as pd

DISPLAY_COLUMNS = [
    ("vessel", "Name"),
    ("vessel_dwt_tons", "Deadweight (t)"),
    ("build_year", "Build year"),
    ("distance_nm", "Distance (nm)"),
    ("vessel_state", "State"),
    ("last_port", "Previous port call"),
    ("next_port", "Next port call"),
    ("next_port_call_source", "Source"),
    ("last_product_on_board", "Products"),
    ("next_destination", "Next destination"),
    ("next_eta", "ETA"),
    ("position", "Position"),
    ("position_age_label", "Last position"),
    ("loading_region", "Loading region"),
    ("owner", "Owner"),
    ("sanctioned_label", "Sanctioned"),
    ("shuttle_available", "Shuttle available"),
    ("is_noc", "NOC"),
]


def vessels_for_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[label for _, label in DISPLAY_COLUMNS])

    out = df.copy()
    # Ensure expected cols exist
    for src, _ in DISPLAY_COLUMNS:
        if src not in out.columns:
            out[src] = pd.NA

    table = out[[src for src, _ in DISPLAY_COLUMNS]].rename(columns={s: l for s, l in DISPLAY_COLUMNS})
    # Format
    if "Deadweight (t)" in table.columns:
        dwt = pd.to_numeric(table["Deadweight (t)"], errors="coerce")
        table["Deadweight (t)"] = dwt.map(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    if "Distance (nm)" in table.columns:
        dist = pd.to_numeric(table["Distance (nm)"], errors="coerce")
        table["Distance (nm)"] = dist.map(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    if "ETA" in table.columns:
        table["ETA"] = pd.to_datetime(table["ETA"], errors="coerce").dt.strftime("%Y-%m-%d")
        table["ETA"] = table["ETA"].fillna("—")
    for bool_col in ("Shuttle available", "NOC"):
        if bool_col in table.columns:
            table[bool_col] = table[bool_col].fillna(False).map({True: "Yes", False: ""})
    if "Sanctioned" in table.columns:
        table["Sanctioned"] = table["Sanctioned"].fillna("").replace("", "—")
    table = table.fillna("—")
    return table
