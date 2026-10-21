"""Parse Clarksons MEG VLCC position Excel dumps and day-over-day diffs.

Source files: ``broker_research/clarksons/CLARKSONS MEG VLCC POSITION *.xlsx``.
Vessel-level detail is for local analysis only — do not commit extracts.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

FILENAME_RE = re.compile(
    r"CLARKSONS\s+MEG\s+VLCC\s+POSITION\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})",
    re.I,
)

HEADER_COLS = [
    "eta_raw",
    "vessel",
    "dwt",
    "blt",
    "draft",
    "coil",
    "position",
    "open_raw",
    "owner",
    "comments",
]


def parse_as_of_from_filename(path: Path | str) -> date:
    m = FILENAME_RE.search(Path(path).name)
    if not m:
        raise ValueError(f"cannot parse as_of from filename: {path}")
    day, mon, year = int(m.group(1)), m.group(2).upper()[:3], int(m.group(3))
    return date(year, MONTHS[mon], day)


def normalize_vessel_name(name: str | None) -> str:
    """Normalize broker/Kpler names for joins.

    Punctuation becomes a space so ``C.GALAXY`` and ``C. GALAXY`` both → ``C GALAXY``.
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).upper().strip()
    # Why space (not delete): initials without space would glue (C.GALAXY → CGALAXY).
    s = re.sub(r"[^\w\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_tbn(name: str) -> bool:
    n = normalize_vessel_name(name)
    return n.endswith(" TBN") or n == "TBN" or " TBN " in f" {n} "


def _cell_date(v) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, pd.Timestamp):
        return v.date()
    s = str(v).strip().upper()
    if not s or s in ("PPT", "NAN", "NAT"):
        return None
    try:
        return pd.to_datetime(v).date()
    except Exception:  # noqa: BLE001
        return None


def parse_meg_position_xlsx(path: Path | str, *, as_of: date | None = None) -> pd.DataFrame:
    """Parse one Clarksons MEG VLCC position workbook into tidy rows."""
    path = Path(path)
    as_of = as_of or parse_as_of_from_filename(path)
    raw = pd.read_excel(path, sheet_name=0, header=None, engine="openpyxl")
    # Header row: ETA / VESSEL in columns 2 and 3
    header_ix = []
    for i, row in raw.iterrows():
        a = str(row.iloc[2]).strip().upper() if pd.notna(row.iloc[2]) else ""
        b = str(row.iloc[3]).strip().upper() if pd.notna(row.iloc[3]) else ""
        if a == "ETA" and b == "VESSEL":
            header_ix.append(int(i))

    rows: list[dict] = []
    for h_i, start in enumerate(header_ix):
        end = header_ix[h_i + 1] if h_i + 1 < len(header_ix) else len(raw)
        block = f"block_{h_i}"
        for i in range(start + 1, end):
            r = raw.iloc[i]
            vessel = r.iloc[3]
            if pd.isna(vessel) or str(vessel).strip() == "":
                continue
            if str(vessel).strip().upper() == "VESSEL":
                continue
            eta_raw = r.iloc[2]
            open_raw = r.iloc[9]
            eta_d = _cell_date(eta_raw)
            open_d = _cell_date(open_raw)
            eta_is_ppt = str(eta_raw).strip().upper() == "PPT" if pd.notna(eta_raw) else False
            rows.append(
                {
                    "as_of": as_of,
                    "source_file": path.name,
                    "block": block,
                    "vessel": str(vessel).strip(),
                    "vessel_norm": normalize_vessel_name(vessel),
                    "is_tbn": is_tbn(str(vessel)),
                    "eta": eta_d,
                    # Stringify raw cells so parquet/Arrow do not see mixed date/str objects.
                    "eta_raw": (
                        eta_d.isoformat()
                        if eta_d is not None
                        else (str(eta_raw).strip() if pd.notna(eta_raw) else None)
                    ),
                    "eta_is_ppt": eta_is_ppt,
                    "dwt": pd.to_numeric(r.iloc[4], errors="coerce"),
                    "blt": _cell_date(r.iloc[5]),
                    "draft": pd.to_numeric(r.iloc[6], errors="coerce"),
                    "coil": str(r.iloc[7]).strip() if pd.notna(r.iloc[7]) else None,
                    "position": str(r.iloc[8]).strip() if pd.notna(r.iloc[8]) else None,
                    "open_date": open_d,
                    "open_raw": (
                        open_d.isoformat()
                        if open_d is not None
                        else (str(open_raw).strip() if pd.notna(open_raw) else None)
                    ),
                    "owner": str(r.iloc[10]).strip() if pd.notna(r.iloc[10]) else None,
                    "comments": str(r.iloc[11]).strip() if pd.notna(r.iloc[11]) else None,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["as_of"] = pd.to_datetime(out["as_of"])
    for col in ("eta", "open_date", "blt"):
        out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def load_all_meg_lists(
    folder: Path | str,
    *,
    pattern: str = "CLARKSONS MEG VLCC POSITION*.xlsx",
) -> pd.DataFrame:
    """Parse every readable dump in ``folder``. Skips locked/unreadable files."""
    folder = Path(folder)
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for path in sorted(folder.glob(pattern), key=lambda p: parse_as_of_from_filename(p)):
        try:
            frames.append(parse_meg_position_xlsx(path))
        except Exception as exc:  # noqa: BLE001 — keep going on OneDrive locks
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
    if not frames:
        raise RuntimeError("no MEG position files parsed; " + "; ".join(errors[:5]))
    out = pd.concat(frames, ignore_index=True)
    out.attrs["load_errors"] = errors
    return out


def list_snapshot_sizes(df: pd.DataFrame, *, exclude_tbn: bool = True) -> pd.DataFrame:
    d = df.loc[~df["is_tbn"]] if exclude_tbn and "is_tbn" in df.columns else df.copy()
    d = d.copy()
    d["Date"] = pd.to_datetime(d["as_of"]).dt.normalize()
    return (
        d.groupby("Date", as_index=False)
        .agg(n_vessels=("vessel_norm", "nunique"), n_rows=("vessel", "count"))
        .sort_values("Date")
    )


TRACKED_FIELDS = ("eta", "open_date", "position", "owner", "comments", "eta_is_ppt", "dwt")


def diff_consecutive_lists(df: pd.DataFrame, *, exclude_tbn: bool = True) -> pd.DataFrame:
    """Vessel-level changes between consecutive as_of dates.

    Events: added, removed, stayed (+ field-level change flags).
    """
    d = df.copy()
    if exclude_tbn:
        d = d.loc[~d["is_tbn"]]
    d = d.sort_values(["as_of", "vessel_norm"])
    # One row per vessel per day (last block wins if dup names)
    d = d.drop_duplicates(["as_of", "vessel_norm"], keep="last")
    dates = sorted(d["as_of"].dt.normalize().unique())
    events: list[dict] = []
    for i in range(1, len(dates)):
        prev_d, curr_d = dates[i - 1], dates[i]
        prev = d.loc[d["as_of"].dt.normalize() == prev_d].set_index("vessel_norm")
        curr = d.loc[d["as_of"].dt.normalize() == curr_d].set_index("vessel_norm")
        prev_set, curr_set = set(prev.index), set(curr.index)
        for v in sorted(curr_set - prev_set):
            events.append(
                {
                    "from_as_of": prev_d,
                    "to_as_of": curr_d,
                    "vessel_norm": v,
                    "vessel": curr.loc[v, "vessel"],
                    "event": "added",
                    "changed_fields": "",
                }
            )
        for v in sorted(prev_set - curr_set):
            events.append(
                {
                    "from_as_of": prev_d,
                    "to_as_of": curr_d,
                    "vessel_norm": v,
                    "vessel": prev.loc[v, "vessel"],
                    "event": "removed",
                    "changed_fields": "",
                }
            )
        for v in sorted(prev_set & curr_set):
            changed = []
            for f in TRACKED_FIELDS:
                a, b = prev.loc[v, f], curr.loc[v, f]
                if pd.isna(a) and pd.isna(b):
                    continue
                if pd.isna(a) or pd.isna(b) or a != b:
                    # dates compare as timestamps
                    if pd.notna(a) and pd.notna(b) and str(a) == str(b):
                        continue
                    changed.append(f)
            events.append(
                {
                    "from_as_of": prev_d,
                    "to_as_of": curr_d,
                    "vessel_norm": v,
                    "vessel": curr.loc[v, "vessel"],
                    "event": "changed" if changed else "unchanged",
                    "changed_fields": ",".join(changed),
                }
            )
    return pd.DataFrame(events)


def diff_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events is None or events.empty:
        return pd.DataFrame()
    return (
        events.groupby(["to_as_of", "event"], as_index=False)
        .size()
        .rename(columns={"size": "n", "to_as_of": "Date"})
        .sort_values(["Date", "event"])
    )


def list_dynamics(events: pd.DataFrame, sizes: pd.DataFrame) -> pd.DataFrame:
    """Wide day-over-day tracker: size, added, removed, net, changed, unchanged."""
    if events is None or events.empty:
        return pd.DataFrame()
    wide = (
        events.groupby(["to_as_of", "event"], as_index=False)
        .size()
        .rename(columns={"size": "n", "to_as_of": "Date"})
        .pivot(index="Date", columns="event", values="n")
        .fillna(0)
        .astype(int)
        .reset_index()
    )
    for col in ("added", "removed", "changed", "unchanged"):
        if col not in wide.columns:
            wide[col] = 0
    wide["net"] = wide["added"] - wide["removed"]
    if sizes is not None and not sizes.empty:
        wide = wide.merge(sizes[["Date", "n_vessels"]], on="Date", how="left")
    return wide.sort_values("Date")


# --- Exit reasons when a vessel drops off the available list -----------------
# Priority matters: commercial status on the last list row beats inferred fixture.
EXIT_REASON_PRIORITY = (
    "cancelled",
    "pushed",
    "on_subs",
    "on_hold",
    "fixed_loaded",
    "unexplained",
)


def classify_comment_exit(comments: str | None) -> str | None:
    """Map Clarksons COMMENTS tokens → exit reason. None if no commercial cue."""
    if comments is None or (isinstance(comments, float) and pd.isna(comments)):
        return None
    c = str(comments).upper()
    if not c.strip():
        return None
    # Cancelled is rare in this pack; keep explicit.
    if re.search(r"\bCANCEL", c):
        return "cancelled"
    if re.search(r"\bPUSHED\b", c):
        return "pushed"
    if re.search(r"\bSUBS?\b", c):
        return "on_subs"
    if re.search(r"\bHOLD\b", c):
        return "on_hold"
    return None


def _fixture_suggests_fixed(fixtures: pd.DataFrame, vessel_norm: str, around: pd.Timestamp, days: int = 3) -> bool:
    if fixtures is None or fixtures.empty or "vessel_norm" not in fixtures.columns:
        return False
    lo = around - pd.Timedelta(days=days)
    hi = around + pd.Timedelta(days=days + 1)
    sub = fixtures.loc[
        (fixtures["vessel_norm"] == vessel_norm)
        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") >= lo)
        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") < hi)
    ]
    if sub.empty:
        return False
    if "fixture_status" in sub.columns:
        st = sub["fixture_status"].astype("string").str.upper()
        if st.str.contains("FULLY FIXED|FIXED|FAILED|CANCEL", na=False).any():
            # Failed/cancel handled by caller via status; here True means any decisive status hit
            return bool(st.str.contains("FULLY FIXED|^FIXED|FIXED", na=False).any())
    # Any nearby VLCC fixture is a weak "likely fixed/loaded" signal
    return True


def _fixture_suggests_cancelled(fixtures: pd.DataFrame, vessel_norm: str, around: pd.Timestamp, days: int = 3) -> bool:
    if fixtures is None or fixtures.empty or "fixture_status" not in fixtures.columns:
        return False
    lo = around - pd.Timedelta(days=days)
    hi = around + pd.Timedelta(days=days + 1)
    sub = fixtures.loc[
        (fixtures["vessel_norm"] == vessel_norm)
        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") >= lo)
        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") < hi)
    ]
    if sub.empty:
        return False
    st = sub["fixture_status"].astype("string").str.upper()
    return bool(st.str.contains("CANCEL|FAILED|ON SUBS FAIL", na=False).any())


def annotate_exits(
    meg: pd.DataFrame,
    events: pd.DataFrame,
    fixtures: pd.DataFrame | None = None,
    *,
    fixture_window_days: int = 3,
) -> pd.DataFrame:
    """Enrich ``removed`` events with exit_reason + confidence + last list fields.

    Confidence: ``high`` = comment token; ``medium`` = fixture Fully Fixed/cancel;
    ``low`` = any nearby fixture inferred as fixed; ``none`` = unexplained.
    """
    if events is None or events.empty:
        return pd.DataFrame()
    rem = events.loc[events["event"] == "removed"].copy()
    if rem.empty:
        return rem.assign(
            exit_reason=pd.Series(dtype="string"),
            exit_confidence=pd.Series(dtype="string"),
            exit_source=pd.Series(dtype="string"),
        )

    d = meg.copy()
    d = d.loc[~d["is_tbn"]] if "is_tbn" in d.columns else d
    d = d.drop_duplicates(["as_of", "vessel_norm"], keep="last")
    d["_d"] = pd.to_datetime(d["as_of"]).dt.normalize()

    rows: list[dict] = []
    for _, ev in rem.iterrows():
        from_d = pd.Timestamp(ev["from_as_of"]).normalize()
        prev = d.loc[(d["vessel_norm"] == ev["vessel_norm"]) & (d["_d"] == from_d)]
        comments = prev["comments"].iloc[0] if len(prev) else None
        position = prev["position"].iloc[0] if len(prev) else None
        open_date = prev["open_date"].iloc[0] if len(prev) else pd.NaT
        eta = prev["eta"].iloc[0] if len(prev) else pd.NaT
        reason = classify_comment_exit(comments)
        source = "comments" if reason else None
        confidence = "high" if reason else "none"

        around = pd.Timestamp(ev["to_as_of"]).normalize()
        if reason is None and _fixture_suggests_cancelled(fixtures, ev["vessel_norm"], around, fixture_window_days):
            reason, source, confidence = "cancelled", "fixture_status", "medium"
        if reason is None and fixtures is not None:
            fx_hit = _fixture_suggests_fixed(fixtures, ev["vessel_norm"], around, fixture_window_days)
            if fx_hit:
                # Prefer Fully Fixed label when status present
                reason, source, confidence = "fixed_loaded", "fixture_near", "low"
                if fixtures is not None and not fixtures.empty and "fixture_status" in fixtures.columns:
                    lo = around - pd.Timedelta(days=fixture_window_days)
                    hi = around + pd.Timedelta(days=fixture_window_days + 1)
                    sub = fixtures.loc[
                        (fixtures["vessel_norm"] == ev["vessel_norm"])
                        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") >= lo)
                        & (pd.to_datetime(fixtures["reported_date"], errors="coerce") < hi)
                    ]
                    st = sub["fixture_status"].astype("string").str.upper() if len(sub) else pd.Series(dtype="string")
                    if st.str.contains("FULLY FIXED", na=False).any():
                        confidence = "medium"
                        source = "fixture_fully_fixed"

        if reason is None:
            reason, source, confidence = "unexplained", "none", "none"

        rows.append(
            {
                **ev.to_dict(),
                "exit_reason": reason,
                "exit_confidence": confidence,
                "exit_source": source,
                "last_comments": comments,
                "last_position": position,
                "last_open_date": open_date,
                "last_eta": eta,
            }
        )
    return pd.DataFrame(rows)


def exit_reason_summary(exits: pd.DataFrame) -> pd.DataFrame:
    if exits is None or exits.empty:
        return pd.DataFrame()
    return (
        exits.groupby(["to_as_of", "exit_reason"], as_index=False)
        .size()
        .rename(columns={"size": "n", "to_as_of": "Date"})
        .sort_values(["Date", "exit_reason"])
    )
