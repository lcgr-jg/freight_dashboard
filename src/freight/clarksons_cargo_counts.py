"""Parse Clarksons VLCC cargo-counts workbook (decade × load region).

Source: ``broker_research/clarksons/CARGO COUNTS DATA.xlsx``.
Sheets are calendar years; layout drifts (region order, MEG→MEG+RSEA in 2026).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

DECADE_LABELS = ("1st", "2nd", "3rd", "TTL")

# Canonical region codes used in tidy output.
REGION_ALIASES = {
    "MEG": "MEG",
    "MEG/STS WCI": "MEG",
    "MEG/STS": "MEG",
    "RSEA": "RSEA",
    "WAF": "WAF",
    "USG": "USG",
    "CARIBS/ECMEX": "CARIBS_ECMEX",
    "EC SOUTH AMERICA": "ECSA",
    "WC SOUTH AMERICA": "WCSA",
    "UKC": "UKC",
    "MED": "MED",
    "ATL TOTAL": "ATL_TOTAL",
    "TOTAL": "WORLD_TOTAL",
}


def _norm_region(raw: str) -> str | None:
    s = str(raw).strip().upper().replace("  ", " ")
    # strip trailing spaces already; UKC often has trailing space in file
    s = s.strip()
    if s in REGION_ALIASES:
        return REGION_ALIASES[s]
    # fuzzy: MEG prefix
    if s.startswith("MEG"):
        return "MEG"
    if s.startswith("ATL"):
        return "ATL_TOTAL"
    if s in ("TOTAL", "TTL WORLD", "WORLD"):
        return "WORLD_TOTAL"
    return None


def _decade_token(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().lower()
    if s.startswith("1"):
        return "1st"
    if s.startswith("2"):
        return "2nd"
    if s.startswith("3"):
        return "3rd"
    if s.startswith("ttl") or s == "total":
        return "TTL"
    return None


def parse_cargo_counts_sheet(
    df: pd.DataFrame,
    *,
    sheet_year: int | None = None,
) -> pd.DataFrame:
    """Tidy one year sheet into long rows (month × region × decade).

    Clarksons sometimes labels the ``2025`` tab months as 2024-01…12 while the
    cargoes are the 2025 book. If every month on the sheet is ``sheet_year - 1``,
    we relabel to ``sheet_year``.
    """
    if df is None or df.empty or len(df) < 3:
        return pd.DataFrame()

    # Region headers live on row 0; decade labels on row 1.
    region_starts: list[tuple[int, str, str]] = []
    for i, v in enumerate(df.iloc[0].tolist()):
        if pd.isna(v):
            continue
        canon = _norm_region(str(v))
        if canon is None:
            continue
        # Skip stray blocks like "ATL TBA"
        if "TBA" in str(v).upper():
            continue
        region_starts.append((i, canon, str(v).strip()))

    if not region_starts:
        return pd.DataFrame()

    # Detect stale year labels before building rows.
    month_years: list[int] = []
    for rix in range(2, len(df)):
        month_cell = df.iloc[rix, 1]
        if isinstance(month_cell, (datetime, pd.Timestamp, date)):
            month_years.append(pd.Timestamp(month_cell).year)
    relabel_to = None
    if sheet_year is not None and month_years and set(month_years) == {sheet_year - 1}:
        relabel_to = sheet_year

    rows: list[dict] = []
    for rix in range(2, len(df)):
        month_cell = df.iloc[rix, 1]
        if pd.isna(month_cell):
            continue
        # Average rows leave MONTH blank; require a real timestamp/date.
        if not isinstance(month_cell, (datetime, pd.Timestamp, date)):
            continue
        month = pd.Timestamp(month_cell).to_period("M").to_timestamp()
        if relabel_to is not None:
            month = month.replace(year=relabel_to)

        days = pd.to_numeric(df.iloc[rix, 0], errors="coerce")
        for start, region, region_raw in region_starts:
            for offset, decade in enumerate(DECADE_LABELS):
                c = start + offset
                if c >= df.shape[1]:
                    break
                # Prefer row-1 label when present (layout check)
                hdr = _decade_token(df.iloc[1, c]) if c < df.shape[1] else decade
                dec = hdr or decade
                val = pd.to_numeric(df.iloc[rix, c], errors="coerce")
                if pd.isna(val):
                    continue
                rows.append(
                    {
                        "month": month,
                        "year": int(month.year),
                        "sheet_year": sheet_year,
                        "region": region,
                        "region_raw": region_raw,
                        "decade": dec,
                        "cargoes": float(val),
                        "days_in_month": float(days) if pd.notna(days) else pd.NA,
                        "year_relabeled": relabel_to is not None,
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Drop WORLD/ATL totals from "load region" analytics helpers via flag
    out["is_aggregate"] = out["region"].isin(("ATL_TOTAL", "WORLD_TOTAL"))
    return out.sort_values(["month", "region", "decade"]).reset_index(drop=True)


def load_cargo_counts(
    path: Path | str,
    *,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Load all year sheets from the Clarksons cargo-counts workbook."""
    path = Path(path)
    xl = pd.ExcelFile(path, engine="openpyxl")
    frames: list[pd.DataFrame] = []
    for sheet in xl.sheet_names:
        if not re.fullmatch(r"\d{4}", str(sheet).strip()):
            continue
        y = int(sheet)
        if years is not None and y not in years:
            continue
        raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
        part = parse_cargo_counts_sheet(raw, sheet_year=y)
        if not part.empty:
            frames.append(part)
    if not frames:
        raise RuntimeError(f"no cargo-count year sheets parsed from {path}")
    out = pd.concat(frames, ignore_index=True)
    # Prefer later sheet when the same month/region/decade appears twice.
    out = out.sort_values(["month", "region", "decade", "sheet_year"])
    out = out.drop_duplicates(["month", "region", "decade"], keep="last")
    return out.reset_index(drop=True)


def meg_cargoes_comparable(df: pd.DataFrame) -> pd.DataFrame:
    """MEG series comparable across years: MEG alone + MEG+RSEA when RSEA exists.

    2026 splits Red Sea (RSEA) out of the old MEG bucket — use ``meg_plus_rsea``
    for y/y continuity with 2022–25 ``MEG``.
    """
    d = df.loc[~df["is_aggregate"]].copy()
    meg = d.loc[d["region"] == "MEG", ["month", "decade", "cargoes"]].rename(
        columns={"cargoes": "meg"}
    )
    rsea = d.loc[d["region"] == "RSEA", ["month", "decade", "cargoes"]].rename(
        columns={"cargoes": "rsea"}
    )
    out = meg.merge(rsea, on=["month", "decade"], how="outer")
    out["meg"] = out["meg"].fillna(0.0)
    out["rsea"] = out["rsea"].fillna(0.0)
    out["meg_plus_rsea"] = out["meg"] + out["rsea"]
    # Before RSEA split, meg_plus_rsea == meg
    out["year"] = pd.to_datetime(out["month"]).dt.year
    return out.sort_values(["month", "decade"])


def cargoes_wide_by_region(
    df: pd.DataFrame,
    *,
    decade: str = "TTL",
    regions: list[str] | None = None,
) -> pd.DataFrame:
    """Month × region pivot for a single decade column (default monthly TTL)."""
    d = df.loc[(~df["is_aggregate"]) & (df["decade"] == decade)].copy()
    if regions:
        d = d.loc[d["region"].isin(regions)]
    return (
        d.pivot_table(index="month", columns="region", values="cargoes", aggfunc="sum")
        .sort_index()
        .reset_index()
    )


def decade_from_date(d) -> str:
    """Map a calendar day to Clarksons decade bucket."""
    ts = pd.Timestamp(d)
    if ts.day <= 10:
        return "1st"
    if ts.day <= 20:
        return "2nd"
    return "3rd"


MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def seasonal_cargoes(
    df: pd.DataFrame,
    *,
    region: str = "MEG+RSEA",
    decade: str = "TTL",
    mask_trailing_zeros: bool = True,
) -> pd.DataFrame:
    """Month-of-year cargoes for seasonality charts (one row per year × calendar month).

    ``region`` can be a tidy region code (``MEG``, ``WAF``, …) or the synthetic
    ``MEG+RSEA`` (MEG alone pre-2026, MEG+RSEA after the Red Sea split).

    Trailing zeros in the latest year are set to NA when ``mask_trailing_zeros``
    so incomplete forward months (e.g. Nov/Dec still blank in the book) do not
    plot as real zero demand.
    """
    decade = str(decade).strip()
    region = str(region).strip()

    if region.upper().replace(" ", "") in ("MEG+RSEA", "MEG_PLUS_RSEA"):
        base = meg_cargoes_comparable(df)
        base = base.loc[base["decade"] == decade, ["month", "year", "meg_plus_rsea"]].copy()
        base = base.rename(columns={"meg_plus_rsea": "cargoes"})
        region_label = "MEG+RSEA"
    else:
        d = df.loc[~df["is_aggregate"]].copy() if "is_aggregate" in df.columns else df.copy()
        d = d.loc[(d["region"] == region) & (d["decade"] == decade)].copy()
        if d.empty:
            return pd.DataFrame(
                columns=["year", "cal_month", "month_label", "cargoes", "yoy_delta", "region", "decade"]
            )
        base = d[["month", "year", "cargoes"]].copy()
        region_label = region

    if base.empty:
        return pd.DataFrame(
            columns=["year", "cal_month", "month_label", "cargoes", "yoy_delta", "region", "decade"]
        )

    base["month"] = pd.to_datetime(base["month"])
    base["year"] = base["month"].dt.year.astype(int)
    base["cal_month"] = base["month"].dt.month.astype(int)
    base["month_label"] = base["cal_month"].map(lambda m: MONTH_ABBR[m - 1])
    base["region"] = region_label
    base["decade"] = decade
    out = (
        base.groupby(["year", "cal_month", "month_label", "region", "decade"], as_index=False)["cargoes"]
        .sum()
        .sort_values(["year", "cal_month"])
    )

    if mask_trailing_zeros and not out.empty:
        latest = int(out["year"].max())
        cur = out.loc[out["year"] == latest].sort_values("cal_month")
        # Walk backward: zeros after the last positive month are incomplete book.
        vals = cur["cargoes"].tolist()
        months = cur["cal_month"].tolist()
        last_pos = None
        for m, v in zip(months, vals):
            if pd.notna(v) and float(v) > 0:
                last_pos = m
        if last_pos is not None:
            mask_idx = out.index[
                (out["year"] == latest) & (out["cal_month"] > last_pos) & (out["cargoes"].fillna(0) == 0)
            ]
            out.loc[mask_idx, "cargoes"] = pd.NA

    # YoY delta vs same calendar month prior year
    prev = out[["year", "cal_month", "cargoes"]].rename(
        columns={"year": "year_prev", "cargoes": "cargoes_prev"}
    )
    prev["year"] = prev["year_prev"] + 1
    out = out.merge(prev[["year", "cal_month", "cargoes_prev"]], on=["year", "cal_month"], how="left")
    out["yoy_delta"] = out["cargoes"] - out["cargoes_prev"]
    return out.drop(columns=["cargoes_prev"]).reset_index(drop=True)


def plot_seasonal_cargoes(
    seasonal: pd.DataFrame,
    *,
    title: str | None = None,
) -> "go.Figure":
    """Jan–Dec overlay: prior years muted, latest year thick + end marker."""
    import plotly.graph_objects as go

    fig = go.Figure()
    if seasonal is None or seasonal.empty:
        fig.update_layout(title=title or "No data", height=420)
        return fig

    years = sorted(int(y) for y in seasonal["year"].unique())
    latest = years[-1]
    # Muted palette for history (beige / grey / pale purple — not loud)
    hist_colors = ["#c4b8a8", "#b0b0b0", "#9a8fb8", "#a8b5c4", "#c9b29b"]
    region = seasonal["region"].iloc[0]
    decade = seasonal["decade"].iloc[0]

    for i, year in enumerate(years):
        sub = seasonal.loc[seasonal["year"] == year].sort_values("cal_month")
        is_latest = year == latest
        color = "#1a1a1a" if is_latest else hist_colors[i % len(hist_colors)]
        fig.add_trace(
            go.Scatter(
                x=sub["cal_month"],
                y=sub["cargoes"],
                mode="lines+markers" if is_latest else "lines",
                name=str(year),
                line=dict(color=color, width=3.2 if is_latest else 1.4),
                marker=dict(size=8 if is_latest else 0, color=color),
                hovertemplate=(
                    "%{customdata[0]} %{customdata[1]}<br>"
                    "cargoes=%{y:.0f}"
                    "<extra></extra>"
                ),
                customdata=[
                    [
                        lab,
                        str(yr),
                        (None if pd.isna(dy) else float(dy)),
                    ]
                    for lab, yr, dy in zip(sub["month_label"], sub["year"], sub["yoy_delta"])
                ],
            )
        )
        # Richer hover for latest: include YoY delta when present
        if is_latest:
            fig.data[-1].hovertemplate = (
                "%{customdata[0]} %{customdata[1]}<br>"
                "cargoes=%{y:.0f}<br>"
                "YoY=%{customdata[2]}"
                "<extra></extra>"
            )

    fig.update_layout(
        title=title or f"{region} cargoes — {decade} decade (seasonal)",
        height=440,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(1, 13)),
            ticktext=list(MONTH_ABBR),
            title=None,
            showgrid=True,
            gridcolor="#e8e8e8",
        ),
        yaxis=dict(title="cargoes", showgrid=True, gridcolor="#e8e8e8", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
        margin=dict(l=50, r=20, t=60, b=40),
        hovermode="x unified",
    )
    return fig


def ships_per_cargo(
    cargoes: pd.DataFrame,
    ships: pd.DataFrame,
    *,
    cargo_col: str = "meg_plus_rsea",
    ships_col: str = "ships",
) -> pd.DataFrame:
    """Join decade cargoes to ships-ex-subs (or proxy) → ships_per_cargo.

    ``ships`` needs columns: month, decade, ``ships_col``.
    ``cargoes`` from ``meg_cargoes_comparable`` (or equivalent with cargo_col).
    """
    c = cargoes.copy()
    s = ships.copy()
    c["month"] = pd.to_datetime(c["month"]).dt.to_period("M").dt.to_timestamp()
    s["month"] = pd.to_datetime(s["month"]).dt.to_period("M").dt.to_timestamp()
    # decade cargoes only (not TTL) for ratio vs ships by decade
    c = c.loc[c["decade"] != "TTL"]
    s = s.loc[s["decade"] != "TTL"] if "decade" in s.columns else s
    out = c.merge(s[["month", "decade", ships_col]], on=["month", "decade"], how="inner")
    out["ships_per_cargo"] = out[ships_col] / out[cargo_col].replace(0, pd.NA)
    return out.sort_values(["month", "decade"])


def ships_proxy_from_meg_list(meg_list: pd.DataFrame) -> pd.DataFrame:
    """Rough ships-by-decade proxy: mean non-TBN list size on dump dates in each decade.

    Not the same as Clarksons ``MEG_SHIPS_EX_SUBS`` — label as proxy.
    """
    d = meg_list.loc[~meg_list["is_tbn"]].copy() if "is_tbn" in meg_list.columns else meg_list.copy()
    d["Date"] = pd.to_datetime(d["as_of"]).dt.normalize()
    daily = d.groupby("Date", as_index=False).agg(ships=("vessel_norm", "nunique"))
    daily["month"] = daily["Date"].dt.to_period("M").dt.to_timestamp()
    daily["decade"] = daily["Date"].map(decade_from_date)
    return (
        daily.groupby(["month", "decade"], as_index=False)
        .agg(ships=("ships", "mean"), n_snapshots=("ships", "count"))
        .assign(ships_source="meg_list_proxy")
    )


def ships_from_evening_pdf(pdf_path: Path | str, report_date: date | None = None) -> pd.DataFrame:
    """Parse MEG_SHIPS_EX_SUBS decade counts from a VLCC evening PDF panel."""
    from clarksons_ingest.parsers import parse_vlcc_pdf_panel

    pdf_path = Path(pdf_path)
    if report_date is None:
        m = re.search(r"(\d{1,2})\s+(\d{1,2})\s+(\d{4})", pdf_path.stem.replace("_", " "))
        # filenames like "VLCC Evening Report 05 10 2026.pdf"
        m = re.search(r"(\d{1,2})\s+(\d{1,2})\s+(\d{4})", pdf_path.name)
        if not m:
            raise ValueError(f"cannot infer report_date from {pdf_path.name}")
        report_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    res = parse_vlcc_pdf_panel(str(pdf_path), report_date)
    rows = [r for r in res.decade_counts if r.get("metric") == "MEG_SHIPS_EX_SUBS"]
    if not rows:
        return pd.DataFrame(columns=["month", "decade", "ships", "ships_source"])
    out = pd.DataFrame(rows)
    out["month"] = pd.to_datetime(out["month"])
    out["decade"] = out["decade"].astype(str).str.lower()
    out = out.rename(columns={"value": "ships"})
    out["ships"] = pd.to_numeric(out["ships"], errors="coerce")
    out = out.loc[out["ships"].notna()].copy()
    out["ships_source"] = "evening_pdf"
    return out[["month", "decade", "ships", "ships_source", "raw_line"]]
