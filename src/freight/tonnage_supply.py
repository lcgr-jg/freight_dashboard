"""Assemble tonnage-supply vessel table: matcher + live fleet + desk overlays + positions."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from freight.kpler import (
    FUJAIRAH_ZONE,
    ETA_DAYS,
    SPEED_KN,
    liquids_config,
    tonnage_supply_series,
    tonnage_supply_vessels,
    vessels_live_snapshot,
)
from freight.noc import attach_noc_flag, load_noc_aliases
from freight.sanctions import attach_sanction_flags, filter_by_sanction_view, resolve_vessel_crossing_root
from freight.shuttle import load_shuttle_available

# AIS "dark" = no fresh last_seen for this many days (desk toggle threshold).
DARK_AIS_DAYS = 10

# Rough centroids for map fallback B (sea / common load regions). Not AIS accuracy.
_GEO_CENTROIDS: dict[str, tuple[float, float]] = {
    "persian gulf": (26.5, 52.0),
    "mideast gulf": (26.5, 52.0),
    "arabian gulf": (26.5, 52.0),
    "gulf of oman": (24.5, 58.5),
    "arabian sea": (18.0, 65.0),
    "red sea": (20.0, 38.5),
    "mediterranean": (35.0, 18.0),
    "south china sea": (12.0, 114.0),
    "east china sea": (30.0, 125.0),
    "malacca strait": (2.5, 101.0),
    "bay of bengal": (15.0, 88.0),
    "west africa": (0.0, 5.0),
    "brazil": (-20.0, -38.0),
    "us gulf": (28.0, -90.0),
    "north sea": (56.0, 3.0),
    "fujairah": (25.12, 56.35),
    "singapore": (1.26, 103.85),
    "ras tanura": (26.64, 50.16),
    "hormuz": (26.57, 56.25),
    "strait of hormuz": (26.57, 56.25),
}


def derive_eta_days(next_eta: pd.Series, *, as_of: pd.Timestamp | None = None) -> pd.Series:
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None).normalize()
    eta = pd.to_datetime(next_eta, errors="coerce")
    return (eta.dt.normalize() - as_of.normalize()).dt.days.astype("Float64")


def derive_distance_nm(eta_days: pd.Series, speed_kn: float) -> pd.Series:
    """Rough NM ≈ kn × 24 × days. Matcher has no distance column."""
    days = pd.to_numeric(eta_days, errors="coerce").clip(lower=0)
    return (days * float(speed_kn) * 24.0).round(0)


def proximity_bucket(eta_days: pd.Series) -> pd.Series:
    d = pd.to_numeric(eta_days, errors="coerce")
    out = pd.Series(pd.NA, index=d.index, dtype="string")
    out = out.mask(d.notna() & (d <= 2), "0-2 days")
    out = out.mask(d.notna() & (d > 2) & (d <= 4), "2-4 days")
    out = out.mask(d.notna() & (d > 4) & (d <= 7), "4-7 days")
    out = out.mask(d.notna() & (d > 7), ">7 days")
    return out


def position_age_minutes(
    last_seen: pd.Series,
    *,
    as_of: pd.Timestamp | None = None,
) -> pd.Series:
    """Minutes since AIS last_seen (UTC)."""
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None)
    ts = pd.to_datetime(last_seen, errors="coerce", utc=True)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    if as_of.tzinfo is not None:
        as_of = as_of.tz_convert("UTC").tz_localize(None)
    delta = as_of - ts
    return (delta.dt.total_seconds() / 60.0).astype("Float64")


def format_position_age(minutes: object) -> str:
    """Human age: ``45m``, ``3h 12m``, ``2d 5h``."""
    if minutes is None or (isinstance(minutes, float) and pd.isna(minutes)):
        return "—"
    try:
        m = float(minutes)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(m) or m < 0:
        return "—"
    total = int(round(m))
    days, rem = divmod(total, 60 * 24)
    hours, mins = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def attach_position_age(
    df: pd.DataFrame,
    *,
    dark_days: float = DARK_AIS_DAYS,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Add position_age_minutes, position_age_label, is_ais_dark (> dark_days)."""
    out = df.copy()
    if "last_seen" not in out.columns:
        out["last_seen"] = pd.NaT
    out["position_age_minutes"] = position_age_minutes(out["last_seen"], as_of=as_of)
    out["position_age_label"] = out["position_age_minutes"].map(format_position_age)
    # Dark only when we have a dated last_seen older than the threshold.
    thresh_min = float(dark_days) * 24.0 * 60.0
    age = out["position_age_minutes"]
    out["is_ais_dark"] = age.notna() & (age > thresh_min)
    return out


def filter_by_ais_dark_view(df: pd.DataFrame, view: str) -> pd.DataFrame:
    """view: all | non_dark (default all). non_dark drops AIS-dark (>10d) ships."""
    key = (view or "all").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"all", ""} or "is_ais_dark" not in df.columns:
        return df
    if key in {"non_dark", "nondark", "non_dark_fleet"}:
        return df.loc[~df["is_ais_dark"].fillna(False)].copy()
    raise ValueError(f"AIS dark view must be all|non_dark, got {view!r}")


def approx_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback B: map last_port / current_sea / current_country to centroids."""
    out = df.copy()
    lats: list[float | None] = []
    lons: list[float | None] = []
    sources: list[str] = []
    for _, row in out.iterrows():
        lat = lon = None
        src = "none"
        for col in ("current_sea", "last_port", "current_country", "current_sub_continent"):
            if col not in out.columns:
                continue
            key = str(row.get(col) or "").strip().lower()
            if not key or key == "nan":
                continue
            if key in _GEO_CENTROIDS:
                lat, lon = _GEO_CENTROIDS[key]
                src = f"approx:{col}"
                break
            # substring match
            hit = next((k for k in _GEO_CENTROIDS if k in key or key in k), None)
            if hit:
                lat, lon = _GEO_CENTROIDS[hit]
                src = f"approx:{col}"
                break
        lats.append(lat)
        lons.append(lon)
        sources.append(src)
    out["latitude"] = lats
    out["longitude"] = lons
    out["position_source"] = sources
    return out


def load_bbg_positions(
    *,
    repo_root: Path,
    imos: set[int] | None = None,
) -> pd.DataFrame:
    """Try live Bloomberg, then latest polygon_tracker enriched CSV."""
    # 1) Live BBG via desk_core / polygon_tracker
    try:
        import sys

        vc = resolve_vessel_crossing_root(repo_root)
        if str(vc) not in sys.path:
            sys.path.insert(0, str(vc))
        from polygon_tracker.fetch_bbg import fetch_tanker_snapshot

        snap = fetch_tanker_snapshot()
        if snap is not None and not snap.empty:
            pos = _normalize_positions(snap)
            if imos:
                pos = pos.loc[pos["imo"].isin(imos)]
            pos["position_source"] = "bloomberg"
            return pos
    except Exception:
        pass

    # 2) Latest enriched snapshot from polygon_tracker
    vc = resolve_vessel_crossing_root(repo_root)
    out_dir = vc / "polygon_tracker" / "output"
    if out_dir.is_dir():
        files = sorted(out_dir.glob("enriched_*.csv"), reverse=True)
        if files:
            try:
                pos = _normalize_positions(pd.read_csv(files[0]))
                if imos:
                    pos = pos.loc[pos["imo"].isin(imos)]
                pos["position_source"] = f"enriched:{files[0].name}"
                return pos
            except Exception:
                pass
    return pd.DataFrame(columns=["imo", "latitude", "longitude", "position_source"])


def _normalize_positions(df: pd.DataFrame) -> pd.DataFrame:
    rename = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    out = df.rename(columns=rename)
    imo_col = "imo" if "imo" in out.columns else ("vessel_imo" if "vessel_imo" in out.columns else None)
    if imo_col is None:
        return pd.DataFrame(columns=["imo", "latitude", "longitude", "last_seen"])
    lat_col = next((c for c in out.columns if c in ("latitude", "lat")), None)
    lon_col = next((c for c in out.columns if c in ("longitude", "lon", "lng")), None)
    if lat_col is None or lon_col is None:
        return pd.DataFrame(columns=["imo", "latitude", "longitude", "last_seen"])
    seen_col = next((c for c in out.columns if c in ("last_seen", "lastseen")), None)
    pos = pd.DataFrame(
        {
            "imo": pd.to_numeric(out[imo_col], errors="coerce"),
            "latitude": pd.to_numeric(out[lat_col], errors="coerce"),
            "longitude": pd.to_numeric(out[lon_col], errors="coerce"),
            "last_seen": pd.to_datetime(out[seen_col], errors="coerce", utc=True)
            if seen_col
            else pd.NaT,
        }
    )
    return pos.dropna(subset=["imo", "latitude", "longitude"]).drop_duplicates("imo")


def attach_positions(df: pd.DataFrame, *, repo_root: Path) -> pd.DataFrame:
    out = df.copy()
    if "imo" not in out.columns:
        out["latitude"] = pd.NA
        out["longitude"] = pd.NA
        out["position_source"] = "none"
        out["last_seen"] = pd.NaT
        return out
    imos = set(pd.to_numeric(out["imo"], errors="coerce").dropna().astype(int))
    bbg = load_bbg_positions(repo_root=repo_root, imos=imos)
    if not bbg.empty:
        out = out.drop(columns=["latitude", "longitude", "position_source", "last_seen"], errors="ignore")
        out = out.merge(bbg, on="imo", how="left")
    else:
        out = approx_positions(out)
        if "last_seen" not in out.columns:
            out["last_seen"] = pd.NaT
    # Fill remaining gaps with approx (keep any last_seen already joined)
    missing = out["latitude"].isna() if "latitude" in out.columns else pd.Series(True, index=out.index)
    if missing.any():
        approx = approx_positions(out.loc[missing])
        for col in ("latitude", "longitude", "position_source"):
            out.loc[missing, col] = approx[col].to_numpy()
    if "last_seen" not in out.columns:
        out["last_seen"] = pd.NaT
    return out


def fetch_matcher_frame(
    config,
    *,
    destination: str = FUJAIRAH_ZONE,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
    vessel_types: list[str] | None = None,
    vessel_states: list[str] | None = None,
    products: list[str] | None = None,
    build_year_min: int = 2010,
    build_year_max: int = 2026,
    match_next_port_call: bool | None = False,
) -> pd.DataFrame:
    today = date.today()
    return tonnage_supply_vessels(
        config,
        today,
        today,
        destination=destination,
        eta=eta,
        speed=speed,
        vessel_types=vessel_types or ["VLCC"],
        vessel_states=vessel_states,
        products=products,
        build_year_min=build_year_min,
        build_year_max=build_year_max,
        match_next_port_call=match_next_port_call,
        columns="all",
    )


def enrich_matcher(
    matcher: pd.DataFrame,
    *,
    repo_root: Path,
    config=None,
    speed_kn: float = SPEED_KN,
    vessels_cache: Path | None = None,
    refresh_vessels: bool = False,
) -> pd.DataFrame:
    """Join live fleet attrs + shuttle + OFAC + NOC + positions; add derived cols."""
    if matcher is None or matcher.empty:
        return pd.DataFrame()

    out = matcher.copy()
    if "vessel_imo" in out.columns:
        out["imo"] = pd.to_numeric(out["vessel_imo"], errors="coerce")
    elif "imo" not in out.columns:
        out["imo"] = pd.NA

    # Live vessels for build year / owner / next destination
    if config is not None:
        live = vessels_live_snapshot(config, cache_path=vessels_cache, refresh=refresh_vessels)
        if not live.empty and "vessel_imo" in live.columns:
            keep = [
                c
                for c in (
                    "vessel_imo",
                    "vessel_build_year",
                    "Owners_names",
                    "next_destination_zone_name",
                    "next destination eta",
                    "next_destination_source",
                    "last_port_call_location_name",
                )
                if c in live.columns
            ]
            live = live[keep].drop_duplicates("vessel_imo")
            live = live.rename(
                columns={
                    "vessel_imo": "imo",
                    "vessel_build_year": "build_year",
                    "Owners_names": "owner",
                    "next_destination_zone_name": "next_destination",
                    "next destination eta": "live_next_eta",
                    "next_destination_source": "live_next_source",
                    "last_port_call_location_name": "live_last_port",
                }
            )
            live["imo"] = pd.to_numeric(live["imo"], errors="coerce")
            out = out.merge(live, on="imo", how="left")

    # Prefer matcher next_eta; fall back to live
    if "next_eta" not in out.columns and "live_next_eta" in out.columns:
        out["next_eta"] = out["live_next_eta"]
    elif "live_next_eta" in out.columns:
        out["next_eta"] = pd.to_datetime(out["next_eta"], errors="coerce").fillna(
            pd.to_datetime(out["live_next_eta"], errors="coerce")
        )

    if "next_destination" not in out.columns:
        out["next_destination"] = out.get("next_port")
    else:
        out["next_destination"] = out["next_destination"].fillna(out.get("next_port"))

    out["eta_days"] = derive_eta_days(out.get("next_eta", pd.Series(index=out.index)))
    out["distance_nm"] = derive_distance_nm(out["eta_days"], speed_kn)
    out["proximity"] = proximity_bucket(out["eta_days"])

    # Loading region from matcher geo
    for src, dest in (
        ("current_sea", "loading_region"),
        ("current_country", "loading_region"),
        ("current_sub_continent", "loading_region"),
    ):
        if src in out.columns and "loading_region" not in out.columns:
            out["loading_region"] = out[src]
        elif src in out.columns:
            out["loading_region"] = out["loading_region"].fillna(out[src])
    if "loading_region" not in out.columns:
        out["loading_region"] = pd.NA

    if "build_year" not in out.columns:
        out["build_year"] = pd.NA
    if "owner" not in out.columns:
        out["owner"] = pd.NA

    # Desk overlays
    shuttle = load_shuttle_available(repo_root=repo_root)
    out = out.merge(shuttle, on="imo", how="left")
    # Explicit bool dtype avoids pandas downcasting FutureWarning on fillna.
    out["shuttle_available"] = out["shuttle_available"].fillna(False).astype("boolean").astype(bool)

    vc = resolve_vessel_crossing_root(repo_root)
    out = attach_sanction_flags(out, imo_col="imo", vc_root=vc)

    aliases = load_noc_aliases(repo_root=repo_root)
    out = attach_noc_flag(out, owner_col="owner", aliases=aliases)

    out = attach_positions(out, repo_root=repo_root)
    out = attach_position_age(out, dark_days=DARK_AIS_DAYS)

    # Position display string
    def _pos_str(r: pd.Series) -> str:
        if pd.notna(r.get("latitude")) and pd.notna(r.get("longitude")):
            return f"{float(r['latitude']):.2f}, {float(r['longitude']):.2f}"
        return "—"

    out["position"] = out.apply(_pos_str, axis=1)
    return out


def apply_client_filters(
    df: pd.DataFrame,
    *,
    sanction_view: str = "all",
    ais_dark_view: str = "all",
) -> pd.DataFrame:
    out = filter_by_sanction_view(df, sanction_view)
    return filter_by_ais_dark_view(out, ais_dark_view)


def fetch_history_series(
    config,
    *,
    destination: str = FUJAIRAH_ZONE,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
    metric: str = "count",
    vessel_types: list[str] | None = None,
    vessel_states: list[str] | None = None,
    products: list[str] | None = None,
    build_year_min: int = 2010,
    build_year_max: int = 2026,
    match_next_port_call: bool | None = False,
    lookback_days: int = 90,
) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return tonnage_supply_series(
        config,
        destination,
        start,
        end,
        eta=eta,
        speed=speed,
        metric=metric,
        vessel_types=vessel_types or ["VLCC"],
        vessel_states=vessel_states,
        products=products,
        build_year_min=build_year_min,
        build_year_max=build_year_max,
        match_next_port_call=match_next_port_call,
        split="total",
    )


def load_tonnage_bundle(
    repo_root: Path,
    *,
    destination: str = FUJAIRAH_ZONE,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
    metric: str = "count",
    vessel_types: list[str] | None = None,
    vessel_states: list[str] | None = None,
    products: list[str] | None = None,
    build_year_min: int = 2010,
    build_year_max: int = 2026,
    match_next_port_call: bool = False,
    sanction_view: str = "all",
    ais_dark_view: str = "all",
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """One-shot fetch for the Dash app. Returns vessels (filtered), series, meta."""
    config = liquids_config(repo_root)
    cache_dir = cache_dir or (repo_root / "apps" / "tonnage_supply" / ".cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    vessels_cache = cache_dir / "vessels_live.parquet"
    matcher = fetch_matcher_frame(
        config,
        destination=destination,
        eta=eta,
        speed=speed,
        vessel_types=vessel_types,
        vessel_states=vessel_states,
        products=products,
        build_year_min=build_year_min,
        build_year_max=build_year_max,
        match_next_port_call=match_next_port_call,
    )
    enriched = enrich_matcher(
        matcher,
        repo_root=repo_root,
        config=config,
        speed_kn=speed,
        vessels_cache=vessels_cache,
        refresh_vessels=refresh,
    )
    filtered = apply_client_filters(
        enriched, sanction_view=sanction_view, ais_dark_view=ais_dark_view
    )

    series = fetch_history_series(
        config,
        destination=destination,
        eta=eta,
        speed=speed,
        metric=metric,
        vessel_types=vessel_types,
        vessel_states=vessel_states,
        products=products,
        build_year_min=build_year_min,
        build_year_max=build_year_max,
        match_next_port_call=match_next_port_call,
    )

    return {
        "vessels": filtered,
        "vessels_all": enriched,
        "series": series,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "destination": destination,
        "n_matcher": len(enriched),
        "n_visible": len(filtered),
    }
