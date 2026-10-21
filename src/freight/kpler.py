"""Kpler Liquids helpers for TD3C physical tape.

Aggregates only in callers that get committed. Prices are Kpler's own
fixture $ (not Baltic WS, not ICE $/t). Auth: Liquids email/password for v1;
raw API_KEY with Authorization Basic for v2 fleet-development.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Kpler referential: "Persian Gulf" / "Arabian Gulf" resolve to this gulf name.
MEG_ZONE = "Mideast Gulf"
# Clarksons MEG open basis is Fujairah (not Ras Tanura) for reachability compares.
FUJAIRAH_ZONE = "Fujairah"
CHINA_ZONE = "China"
ETA_DAYS = 7
SPEED_KN = 11
# Clarksons-style availability windows (days-out). Kpler caps eta at 21 days.
MEG_AVAIL_ETAS = (7, 15, 20, 21)
# Atlantic load zones that return VLCC fixture rows on Liquids (probe-backed).
ATLANTIC_LOAD_ZONES = ("West Africa", "Brazil", "United States")


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def repo_env(repo_root: Path) -> dict[str, str]:
    return parse_dotenv(repo_root / ".env")


def liquids_config(repo_root: Path):
    cred = repo_env(repo_root)
    email = cred.get("KPLER_EMAIL") or cred.get("EMAIL")
    password = cred.get("KPLER_PASSWORD") or cred.get("PASSWORD")
    if not email or not password:
        raise RuntimeError("KPLER_EMAIL / KPLER_PASSWORD missing in .env")
    from kpler.sdk import Platform
    from kpler.sdk.configuration import Configuration

    return Configuration(Platform.Liquids, email, password, timeout=90)


def v2_headers(repo_root: Path) -> dict[str, str]:
    key = repo_env(repo_root).get("API_KEY") or repo_env(repo_root).get("KPLER_V2_API_KEY")
    if not key:
        raise RuntimeError("API_KEY missing in .env")
    # Portal snippet is Basic + raw key, not Base64.
    return {"Authorization": f"Basic {key}", "Accept": "application/json"}


def _series_cache(cache_dir: Path, name: str, refresh: bool, fetch) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{name}.parquet"
    if path.exists() and not refresh:
        df = pd.read_parquet(path)
        if "Date" in df.columns:
            df["Date"] = parse_kpler_dates(df["Date"])
        return df
    df = fetch()
    if df is None:
        df = pd.DataFrame()
    else:
        df = df.copy()
        if "Date" in df.columns:
            df["Date"] = parse_kpler_dates(df["Date"])
    df.to_parquet(path, index=False)
    return df


def parse_kpler_dates(s: pd.Series) -> pd.Series:
    """Daily timestamps, monthly ``YYYY-MM``, and ISO weeks like ``2026-W16``."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s)
    as_str = s.astype("string")
    out = pd.to_datetime(s, errors="coerce")
    # Monthly freight-metrics labels: 2026-05
    ym = as_str.str.match(r"^\d{4}-\d{2}$", na=False) & out.isna()
    if ym.any():
        out = out.copy()
        out.loc[ym] = pd.to_datetime(as_str[ym] + "-01", errors="coerce")
    iso = as_str.str.match(r"^\d{4}-W\d{2}$", na=False)
    if iso.any():
        # %G/%V/%u = ISO year / week / Monday=1
        parsed = as_str[iso].map(lambda x: pd.Timestamp(datetime.strptime(f"{x}-1", "%G-W%V-%u")))
        out = out.copy()
        out.loc[iso] = parsed
    return out


def _ensure_date_col(df: pd.DataFrame) -> pd.DataFrame:
    """SDK series often put the timestamp on the index, not a column."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Date" not in out.columns:
        idx_name = out.index.name
        if idx_name in ("Date", "date") or pd.api.types.is_datetime64_any_dtype(out.index):
            out = out.reset_index()
        if "date" in out.columns and "Date" not in out.columns:
            out = out.rename(columns={"date": "Date"})
        if "Date" not in out.columns and "index" in out.columns:
            out = out.rename(columns={"index": "Date"})
    if "Date" in out.columns:
        out["Date"] = parse_kpler_dates(out["Date"])
    return out


def zscore(s: pd.Series, window: int = 90) -> pd.Series:
    mu = s.rolling(window, min_periods=max(20, window // 3)).mean()
    sd = s.rolling(window, min_periods=max(20, window // 3)).std()
    # Zero variance is a flat tape, not infinite tightness.
    return (s - mu) / sd.replace(0, pd.NA)


def tonnage_count_series(
    config,
    destination: str,
    start: date,
    end: date | None = None,
    *,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
) -> pd.DataFrame:
    from kpler.sdk import TonnageSupplySeriesMetric, TonnageSupplySeriesSplit, TonnageSupplyVesselTypes
    from kpler.sdk.resources.tonnage_supply_series import TonnageSupplySeries

    end = end or date.today()
    client = TonnageSupplySeries(config)
    df = client.get(
        destination=destination,
        eta=eta,
        speed=speed,
        start_date=start,
        end_date=end,
        metric=TonnageSupplySeriesMetric.Count,
        split=TonnageSupplySeriesSplit.Total,
        vessel_types=[TonnageSupplyVesselTypes.VLCC],
    )
    out = _ensure_date_col(df if df is not None else pd.DataFrame())
    if out.empty:
        return pd.DataFrame(columns=["Date", "vlcc_count"])
    if "vlcc_count" not in out.columns:
        if "Total" in out.columns:
            out = out.rename(columns={"Total": "vlcc_count"})
        else:
            num = [c for c in out.select_dtypes("number").columns if c != "Date"]
            if num:
                out = out.rename(columns={num[0]: "vlcc_count"})
    return out


def tonnage_ladder(
    config,
    destination: str,
    start: date,
    end: date | None = None,
    *,
    etas: tuple[int, ...] | list[int] = MEG_AVAIL_ETAS,
    speed: int = SPEED_KN,
) -> pd.DataFrame:
    """VLCC reachable counts for several ETA horizons (wide: Date, eta_7, …)."""
    end = end or date.today()
    out: pd.DataFrame | None = None
    for eta in etas:
        part = tonnage_count_series(
            config, destination, start, end, eta=int(eta), speed=speed
        )
        if part.empty or "vlcc_count" not in part.columns:
            continue
        col = f"eta_{int(eta)}"
        part = part[["Date", "vlcc_count"]].rename(columns={"vlcc_count": col})
        out = part if out is None else out.merge(part, on="Date", how="outer")
    if out is None:
        return pd.DataFrame(columns=["Date", *[f"eta_{e}" for e in etas]])
    return out.sort_values("Date")


def laden_ballast_ratio(util: pd.DataFrame) -> pd.DataFrame:
    """Loaded / (Loaded + Ballast) from FleetUtilization state split.

    All VLCC on the Liquids view — *not* Clarksons non-restricted / dark-fleet filter.
    """
    if util is None or util.empty:
        return pd.DataFrame(columns=["Date", "Loaded", "Ballast", "laden_ballast_ratio"])
    need = {"Date", "Loaded", "Ballast"}
    if not need.issubset(util.columns):
        return pd.DataFrame(columns=["Date", "Loaded", "Ballast", "laden_ballast_ratio"])
    out = util[["Date", "Loaded", "Ballast"]].copy()
    denom = out["Loaded"] + out["Ballast"]
    out["laden_ballast_ratio"] = out["Loaded"] / denom.replace(0, pd.NA)
    return out


def fleet_util_vlcc(config, start: date, end: date | None = None) -> pd.DataFrame:
    from kpler.sdk import (
        FleetUtilizationSeriesMetric,
        FleetUtilizationSeriesPeriod,
        FleetUtilizationSeriesSplit,
        VesselTypesOil,
    )
    from kpler.sdk.resources.fleet_utilization_series import FleetUtilizationSeries

    end = end or date.today()
    client = FleetUtilizationSeries(config)
    return _ensure_date_col(
        client.get(
            start_date=start,
            end_date=end,
            metric=FleetUtilizationSeriesMetric.Count,
            period=FleetUtilizationSeriesPeriod.Daily,
            split=FleetUtilizationSeriesSplit.State,
            vessel_types_oil=[VesselTypesOil.VLCC],
        )
    )


def ballast_capacity_vlcc(config, start: date, end: date | None = None) -> pd.DataFrame:
    """Ballast *capacity* (kt) from port-call aggregates — not fleet-util ship count.

    SDK docs: aggregated from Ballast Capacity Port Calls; example metric is Capacity.
    Count for VLCC is sparse on this account; use FleetUtilizationSeries Ballast for
    'how many VLCCs are empty'.
    """
    from kpler.sdk import (
        BallastCapacitySeriesMetric,
        BallastCapacitySeriesPeriod,
        BallastCapacitySeriesSplit,
        VesselTypesOil,
    )
    from kpler.sdk.resources.ballast_capacity_series import BallastCapacitySeries

    end = end or date.today()
    client = BallastCapacitySeries(config)
    df = client.get(
        start_date=start,
        end_date=end,
        metric=BallastCapacitySeriesMetric.Capacity,
        period=BallastCapacitySeriesPeriod.Daily,
        split=BallastCapacitySeriesSplit.VesselTypeOil,
        vessel_types_oil=[VesselTypesOil.VLCC],
        with_freight_view=True,
    )
    out = _ensure_date_col(df)
    if out.empty:
        return pd.DataFrame(columns=["Date", "vlcc_ballast_capacity"])
    if "VLCC" in out.columns:
        out = out.rename(columns={"VLCC": "vlcc_ballast_capacity"})
    if "vlcc_ballast_capacity" not in out.columns:
        num = [c for c in out.columns if c != "Date"]
        if num:
            out = out.rename(columns={num[0]: "vlcc_ballast_capacity"})
    # Capacity unit in SDK example is cargo tonnes; store as numeric for charts.
    if "vlcc_ballast_capacity" in out.columns:
        out["vlcc_ballast_capacity"] = pd.to_numeric(out["vlcc_ballast_capacity"], errors="coerce")
    return out


# Back-compat name used briefly in notebook 02; prefer ballast_capacity_vlcc.
def ballast_vlcc(config, start: date, end: date | None = None) -> pd.DataFrame:
    return ballast_capacity_vlcc(config, start, end)


def congestion_china_vlcc(config, start: date, end: date | None = None) -> pd.DataFrame:
    from kpler.sdk import (
        CongestionSeriesMetric,
        CongestionSeriesPeriod,
        CongestionSeriesSplit,
        VesselTypesOil,
    )
    from kpler.sdk.resources.congestion_series import CongestionSeries

    end = end or date.today()
    client = CongestionSeries(config)
    df = client.get(
        start_date=start,
        end_date=end,
        zones=["China"],
        metric=CongestionSeriesMetric.Count,
        period=CongestionSeriesPeriod.Weekly,
        split=CongestionSeriesSplit.VesselTypeOil,
        vessel_types_oil=[VesselTypesOil.VLCC],
        with_freight_view=True,
    )
    out = _ensure_date_col(df)
    if out.empty:
        return pd.DataFrame(columns=["Date", "vlcc_waiting"])
    if "VLCC" in out.columns:
        out = out.rename(columns={"VLCC": "vlcc_waiting"})
    if "vlcc_waiting" not in out.columns:
        num = [c for c in out.columns if c != "Date"]
        if num:
            out = out.rename(columns={num[0]: "vlcc_waiting"})
    return out


# Chart scale: Kpler returns large numeric ton-mile units; /1e9 ≈ Bn for desk slides.
TONMILES_BN = 1e9

# Named load regions for VLCC → China origin split (zones that return data on Liquids).
CHINA_VLCC_ORIGINS = (
    "Mideast Gulf",
    "West Africa",
    "Brazil",
    "United States",
    "Russia",
)


def _freight_metrics_client(config):
    from kpler.sdk.resources.freight_metrics_series import FreightMetricsSeries

    return FreightMetricsSeries(config)


def _vlcc_tonmiles_frame(
    config,
    start: date,
    end: date,
    *,
    to_locations: list[str] | None = None,
    from_locations: list[str] | None = None,
) -> pd.DataFrame:
    """Monthly VLCC ton-miles via vesselTypeOil split (Total+VLCC filter is empty here)."""
    from kpler.sdk import (
        FreightMetricsSeriesMetric,
        FreightMetricsSeriesPeriod,
        FreightMetricsSeriesSplit,
        FreightMetricsSeriesUnit,
    )

    client = _freight_metrics_client(config)
    kw: dict[str, Any] = {
        "metric": FreightMetricsSeriesMetric.TonMiles,
        "split": FreightMetricsSeriesSplit.VesselTypeOil,
        "unit": FreightMetricsSeriesUnit.KTNMI,
        "period": FreightMetricsSeriesPeriod.Monthly,
        "start_date": start,
        "end_date": end,
        "with_freight_view": True,
    }
    if to_locations:
        kw["to_locations"] = to_locations
    if from_locations:
        kw["from_locations"] = from_locations
    out = _ensure_date_col(client.get(**kw))
    if out.empty or "VLCC" not in out.columns:
        return pd.DataFrame(columns=["Date", "ton_miles"])
    out = out[["Date", "VLCC"]].rename(columns={"VLCC": "ton_miles"})
    out["ton_miles"] = pd.to_numeric(out["ton_miles"], errors="coerce")
    return out


def tonmiles_vlcc(config, start: date, end: date | None = None) -> pd.DataFrame:
    """Monthly global VLCC ton-miles."""
    end = end or date.today()
    return _vlcc_tonmiles_frame(config, start, end)


def tonmiles_vlcc_to(
    config,
    to_location: str,
    start: date,
    end: date | None = None,
) -> pd.DataFrame:
    """Monthly VLCC ton-miles into a destination (e.g. China)."""
    end = end or date.today()
    return _vlcc_tonmiles_frame(config, start, end, to_locations=[to_location])


def tonmiles_vlcc_to_by_origin(
    config,
    to_location: str,
    start: date,
    end: date | None = None,
    *,
    origins: tuple[str, ...] | list[str] = CHINA_VLCC_ORIGINS,
) -> pd.DataFrame:
    """VLCC ton-miles into ``to_location``, columns = named origins + Other.

    OriginCountry + vessel_types_oil=[VLCC] returns empty on this account, so we
    pull each from_location with a VesselTypeOil split and residual Other =
    destination total − sum(named). Overlaps between zones can bias Other.
    """
    end = end or date.today()
    total = tonmiles_vlcc_to(config, to_location, start, end)
    if total.empty:
        return pd.DataFrame(columns=["Date", *origins, "Other"])
    out = total.rename(columns={"ton_miles": "_total"}).copy()
    for origin in origins:
        part = _vlcc_tonmiles_frame(
            config, start, end, to_locations=[to_location], from_locations=[origin]
        )
        out = out.merge(
            part.rename(columns={"ton_miles": origin}),
            on="Date",
            how="left",
        )
    named = list(origins)
    out[named] = out[named].apply(pd.to_numeric, errors="coerce")
    out["Other"] = out["_total"] - out[named].sum(axis=1, min_count=1)
    return out.drop(columns=["_total"]).sort_values("Date")


def seasonal_tonmiles(
    df: pd.DataFrame,
    value_col: str = "ton_miles",
    *,
    history_years: int = 5,
    as_of_year: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Build month-of-year seasonality: range/mean over prior years + recent year lines.

    Returns dict with keys ``band`` (month, y5_lo, y5_hi, y5_mean) and ``years``
    (month × year columns for years in the window ending at as_of_year).
    """
    if df is None or df.empty or value_col not in df.columns:
        return {"band": pd.DataFrame(), "years": pd.DataFrame()}
    s = df[["Date", value_col]].dropna().copy()
    s["Date"] = pd.to_datetime(s["Date"])
    s["year"] = s["Date"].dt.year
    s["month"] = s["Date"].dt.month
    as_of_year = as_of_year or int(s["year"].max())
    # History band: the history_years calendar years before as_of_year
    hist_lo = as_of_year - history_years
    hist = s.loc[(s["year"] >= hist_lo) & (s["year"] < as_of_year)]
    band = (
        hist.groupby("month", as_index=False)[value_col]
        .agg(y5_lo="min", y5_hi="max", y5_mean="mean")
        if not hist.empty
        else pd.DataFrame(columns=["month", "y5_lo", "y5_hi", "y5_mean"])
    )
    # Overlay: last few years including as_of
    year_min = as_of_year - 2
    recent = s.loc[s["year"] >= year_min]
    years = recent.pivot_table(index="month", columns="year", values=value_col, aggfunc="sum")
    years = years.reset_index()
    return {"band": band, "years": years}


def fixtures_vlcc_summary(
    config,
    start: date,
    end: date | None = None,
    *,
    from_zones: list[str] | None = None,
    to_zones: list[str] | None = None,
    size: int = 1000,
) -> pd.DataFrame:
    """Daily fixture *counts* (and median Kpler $ if present). No vessel names."""
    from kpler.sdk import VesselTypesOil
    from kpler.sdk.resources.fixtures import Fixtures

    end = end or date.today()
    client = Fixtures(config)
    raw = client.get(
        size=size,
        reported_date_after=start,
        reported_date_before=end,
        from_zones=from_zones or [MEG_ZONE],
        to_zones=to_zones or [CHINA_ZONE],
        vessel_types_oil=[VesselTypesOil.VLCC],
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Date", "n_fixtures", "median_rate"])
    df = raw.copy()
    date_col = "Reported date" if "Reported date" in df.columns else "reportedDate"
    rate_col = "Rates ($ price)" if "Rates ($ price)" in df.columns else "rateValue"
    df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
    if rate_col in df.columns:
        df["_rate"] = pd.to_numeric(df[rate_col], errors="coerce")
    else:
        df["_rate"] = pd.NA
    g = df.dropna(subset=["Date"]).groupby(df["Date"].dt.date)
    out = pd.DataFrame(
        {
            "Date": pd.to_datetime(list(g.groups.keys())),
            "n_fixtures": [len(x) for _, x in g],
            "median_rate": [x["_rate"].median() for _, x in g],
        }
    )
    return out.sort_values("Date")


def fixtures_vlcc_monthly(
    config,
    start: date,
    end: date | None = None,
    *,
    from_zones: list[str] | None = None,
    to_zones: list[str] | None = None,
    size: int = 1000,
) -> pd.DataFrame:
    """Monthly VLCC fixture counts (no vessel names). ``to_zones=None`` = all destinations."""
    from kpler.sdk import VesselTypesOil
    from kpler.sdk.resources.fixtures import Fixtures

    end = end or date.today()
    client = Fixtures(config)
    kw: dict[str, Any] = {
        "size": size,
        "reported_date_after": start,
        "reported_date_before": end,
        "vessel_types_oil": [VesselTypesOil.VLCC],
    }
    if from_zones:
        kw["from_zones"] = from_zones
    if to_zones:
        kw["to_zones"] = to_zones
    raw = client.get(**kw)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Date", "n_fixtures"])
    df = raw.copy()
    date_col = "Reported date" if "Reported date" in df.columns else "reportedDate"
    df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["month"] = df["Date"].dt.to_period("M").dt.to_timestamp()
    out = df.groupby("month", as_index=False).size().rename(
        columns={"month": "Date", "size": "n_fixtures"}
    )
    return out.sort_values("Date")


def fixtures_corridor_monthly(
    config,
    start: date,
    end: date | None = None,
) -> pd.DataFrame:
    """MEG spot (all dest) + Atlantic→China VLCC monthly counts side by side."""
    end = end or date.today()
    meg = fixtures_vlcc_monthly(
        config, start, end, from_zones=[MEG_ZONE], to_zones=None
    ).rename(columns={"n_fixtures": "meg_spot"})
    # One pull per Atlantic load zone then sum — avoids empty multi-zone quirks.
    atl_parts = []
    for zone in ATLANTIC_LOAD_ZONES:
        part = fixtures_vlcc_monthly(
            config, start, end, from_zones=[zone], to_zones=[CHINA_ZONE]
        )
        if not part.empty:
            atl_parts.append(part.rename(columns={"n_fixtures": zone}))
    out = meg.copy()
    if atl_parts:
        atl = atl_parts[0]
        for p in atl_parts[1:]:
            atl = atl.merge(p, on="Date", how="outer")
        zone_cols = [c for c in atl.columns if c != "Date"]
        atl["atlantic_to_china"] = atl[zone_cols].sum(axis=1, min_count=1)
        out = out.merge(atl[["Date", "atlantic_to_china"] + zone_cols], on="Date", how="outer")
    else:
        out["atlantic_to_china"] = pd.NA
    return out.sort_values("Date")


# Live Vessels.get() fields — no as_of / PIT. Joining them onto historical
# Clarksons rows does NOT reconstruct Kpler's view on that day.
VESSEL_LIVE_COLUMNS = [
    "vessel_name",
    "vessel_imo",
    "vessel_status",
    "vessel_dead_weight",
    "vessel_type",
    "vessel_build_year",
    "last_port_call_location_name",
    "last_port_call_end",
    "next_destination_zone_name",
    "next destination eta",
    "vessel_availability_status",
    "vessel_availability_open",
    "Owners_names",
    "is_floating_storage",
    "last_speed_kn",
]

# Columns from the live fleet snapshot that change day-to-day (AIS / open).
# Identity fields (imo, dwt, type, build) are also live-only but usually stable.
VESSEL_STATE_LIVE_FIELDS = (
    "vessel_status",
    "last_port_call_location_name",
    "last_port_call_end",
    "next_destination_zone_name",
    "next destination eta",
    "vessel_availability_status",
    "vessel_availability_open",
    "is_floating_storage",
    "last_speed_kn",
    "Owners_names",
)


def vessels_vlcc_snapshot(
    config,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
    dwt_min: int = 200_000,
) -> pd.DataFrame:
    """Live VLCC-ish fleet snapshot. **No point-in-time** — ``pit_available=False``.

    Cached under ``cache_dir`` for the session; re-fetch with ``refresh=True``.
    """
    from kpler.sdk.resources.vessels import Vessels

    from freight.clarksons_meg_list import normalize_vessel_name

    def fetch() -> pd.DataFrame:
        client = Vessels(config)
        raw = client.get(columns=list(VESSEL_LIVE_COLUMNS), with_freight_view=True)
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.copy()
        df["vessel_dead_weight"] = pd.to_numeric(df.get("vessel_dead_weight"), errors="coerce")
        df = df.loc[df["vessel_dead_weight"].fillna(0) >= dwt_min].copy()
        df["vessel_norm"] = df["vessel_name"].map(normalize_vessel_name)
        df["kpler_snapshot_at"] = pd.Timestamp.utcnow().tz_localize(None)
        # Explicit: none of these rows are as-of a historical Clarksons date.
        df["pit_available"] = False
        return df

    if cache_dir is None:
        return fetch()
    return _series_cache(cache_dir, "kpler_vessels_vlcc_live", refresh, fetch)


def fixtures_vlcc_detail(
    config,
    start: date,
    end: date | None = None,
    *,
    from_zones: list[str] | None = None,
    to_zones: list[str] | None = None,
    size: int = 5000,
    dwt_min: int = 200_000,
) -> pd.DataFrame:
    """VLCC fixtures with vessel names for local matching. Has reported-date history.

    Vessel-level detail — keep local / gitignored; do not commit extracts.
    SDK ``vessel_types_oil=VLCC`` can still return smaller ships; ``dwt_min`` cleans that.
    """
    from kpler.sdk import VesselTypesOil
    from kpler.sdk.resources.fixtures import Fixtures

    from freight.clarksons_meg_list import normalize_vessel_name

    end = end or date.today()
    client = Fixtures(config)
    kw: dict[str, Any] = {
        "size": size,
        "reported_date_after": start,
        "reported_date_before": end,
        "vessel_types_oil": [VesselTypesOil.VLCC],
        "dwt_min": dwt_min,
    }
    if from_zones:
        kw["from_zones"] = from_zones
    if to_zones:
        kw["to_zones"] = to_zones
    raw = client.get(**kw)
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    # Column names vary slightly by SDK version / subscription.
    rename = {}
    for cand, std in (
        ("Reported date", "reported_date"),
        ("reportedDate", "reported_date"),
        ("Vessel", "vessel"),
        ("vesselName", "vessel"),
        ("Vessel name", "vessel"),
        ("IMO", "imo"),
        ("vesselImo", "imo"),
        ("Origin", "origin"),
        ("Destination", "destination"),
        ("Rates ($ price)", "rate_usd"),
        ("rateValue", "rate_usd"),
        ("Charterer", "charterer"),
        ("Status", "fixture_status"),
        ("Laycan start", "laycan_start"),
        ("Lay can start", "laycan_start"),
        ("Deadweight (t)", "dwt"),
        ("vesselDeadweight", "dwt"),
        ("Vessel Type Oil", "vessel_type_oil"),
    ):
        if cand in df.columns and std not in df.columns:
            rename[cand] = std
    df = df.rename(columns=rename)
    if "vessel" not in df.columns:
        for c in df.columns:
            if "vessel" in c.lower() and "type" not in c.lower() and "owner" not in c.lower():
                df = df.rename(columns={c: "vessel"})
                break
    if "reported_date" in df.columns:
        df["reported_date"] = pd.to_datetime(df["reported_date"], errors="coerce")
    if "dwt" in df.columns:
        df["dwt"] = pd.to_numeric(df["dwt"], errors="coerce")
        df = df.loc[df["dwt"].fillna(0) >= dwt_min].copy()
    if "vessel" in df.columns:
        df["vessel_norm"] = df["vessel"].map(normalize_vessel_name)
    df["pit_available"] = True  # fixtures are dated events
    return df


def _resolve_vessel_types(vessel_types: list[str] | None):
    from kpler.sdk import TonnageSupplyVesselTypes

    if not vessel_types:
        return [TonnageSupplyVesselTypes.VLCC]
    out = []
    for name in vessel_types:
        if isinstance(name, TonnageSupplyVesselTypes):
            out.append(name)
            continue
        # Enum value strings match UI labels (e.g. "Suezmax/LR3").
        try:
            out.append(TonnageSupplyVesselTypes(name))
        except ValueError:
            match = next((m for m in TonnageSupplyVesselTypes if m.value == name or m.name == name), None)
            if match is None:
                raise ValueError(f"Unknown vessel type: {name!r}") from None
            out.append(match)
    return out


def _resolve_vessel_states(vessel_states: list[str] | None):
    from kpler.sdk import TonnageSupplyVesselsState

    if not vessel_states:
        return None
    out = []
    for name in vessel_states:
        if isinstance(name, TonnageSupplyVesselsState):
            out.append(name)
            continue
        try:
            out.append(TonnageSupplyVesselsState(name))
        except ValueError:
            match = next((m for m in TonnageSupplyVesselsState if m.value == name or m.name == name), None)
            if match is None:
                raise ValueError(f"Unknown vessel state: {name!r}") from None
            out.append(match)
    return out


def tonnage_supply_vessels(
    config,
    start: date,
    end: date | None = None,
    *,
    destination: str = FUJAIRAH_ZONE,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
    vessel_types: list[str] | None = None,
    vessel_states: list[str] | None = None,
    products: list[str] | None = None,
    build_year_min: int | None = None,
    build_year_max: int | None = None,
    match_next_port_call: bool | None = None,
    columns: str | list[str] | None = "all",
) -> pd.DataFrame:
    """Matcher vessel list for a destination. Window ≤ 6 days (API limit).

    Default destination is **Fujairah** (Clarksons MEG open basis). Use
    ``MEG_ZONE`` only when you want the wider gulf polygon.
    ``pit_available=True`` for the ``Date`` returned by the endpoint.
    """
    from kpler.sdk.resources.tonnage_supply_vessels import TonnageSupplyVessels

    from freight.clarksons_meg_list import normalize_vessel_name

    end = end or date.today()
    if (end - start).days > 6:
        raise ValueError("TonnageSupplyVessels window cannot exceed 6 days; stitch in caller")
    kw: dict[str, Any] = {
        "destination": destination,
        "eta": eta,
        "speed": speed,
        "start_date": start,
        "end_date": end,
        "vessel_types": _resolve_vessel_types(vessel_types),
        "columns": columns,
    }
    states = _resolve_vessel_states(vessel_states)
    if states:
        kw["vessel_states"] = states
    if products:
        kw["products"] = products
    if build_year_min is not None:
        kw["build_year_min"] = build_year_min
    if build_year_max is not None:
        kw["build_year_max"] = build_year_max
    if match_next_port_call is not None:
        kw["match_next_port_call"] = match_next_port_call

    client = TonnageSupplyVessels(config)
    raw = client.get(**kw)
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = _ensure_date_col(raw)
    # Normalize column names for the app layer.
    rename = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "_")
        if cl == "vessel_imo":
            rename[c] = "vessel_imo"
        elif cl in ("vessel", "vessel_name"):
            rename[c] = "vessel"
        elif cl in ("vessel_dwt_tons", "vessel_deadweight", "deadweight"):
            rename[c] = "vessel_dwt_tons"
        elif cl == "vessel_state":
            rename[c] = "vessel_state"
        elif cl == "last_product_on_board":
            rename[c] = "last_product_on_board"
        elif cl == "last_port":
            rename[c] = "last_port"
        elif cl == "next_port":
            rename[c] = "next_port"
        elif cl == "next_eta":
            rename[c] = "next_eta"
        elif cl == "next_port_call_source":
            rename[c] = "next_port_call_source"
    if rename:
        df = df.rename(columns=rename)
    if "vessel" in df.columns:
        df["vessel_norm"] = df["vessel"].map(normalize_vessel_name)
    elif any("vessel" in c.lower() for c in df.columns):
        for c in df.columns:
            if "vessel" in c.lower() and "type" not in c.lower() and "imo" not in c.lower():
                df["vessel"] = df[c]
                df["vessel_norm"] = df[c].map(normalize_vessel_name)
                break
    df["matcher_destination"] = destination
    df["matcher_eta_days"] = eta
    df["matcher_speed_kn"] = speed
    df["pit_available"] = True
    return df


def tonnage_supply_vessels_meg(
    config,
    start: date,
    end: date | None = None,
    *,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
) -> pd.DataFrame:
    """Backward-compatible wrapper → Fujairah basis (not Ras Tanura / not MEG polygon)."""
    return tonnage_supply_vessels(
        config, start, end, destination=FUJAIRAH_ZONE, eta=eta, speed=speed
    )


def stitch_matcher_eta_ladder(
    config,
    start: date,
    end: date,
    *,
    destination: str = FUJAIRAH_ZONE,
    etas: tuple[int, ...] = MEG_AVAIL_ETAS,
    speed: int = SPEED_KN,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Stitch Fujairah (or other) matcher membership across dates × eta windows.

    Returns long frame: Date, vessel_norm, matcher_eta_days, (+ vessel, next_eta if present).
    Cached per destination when ``cache_dir`` set.
    """
    cache_name = f"matcher_ladder_{destination.replace(' ', '_').lower()}"

    def fetch() -> pd.DataFrame:
        parts: list[pd.DataFrame] = []
        for eta in etas:
            cur = start
            while cur <= end:
                win_end = min(cur + timedelta(days=5), end)
                try:
                    part = tonnage_supply_vessels(
                        config, cur, win_end, destination=destination, eta=eta, speed=speed
                    )
                except Exception as exc:  # noqa: BLE001
                    print("matcher ladder fail", destination, eta, cur, win_end, type(exc).__name__, exc)
                    part = pd.DataFrame()
                if not part.empty:
                    keep = [c for c in ("Date", "vessel_norm", "vessel", "vessel_imo", "next_eta",
                                         "vessel_state", "matcher_destination", "matcher_eta_days",
                                         "pit_available") if c in part.columns]
                    parts.append(part[keep])
                cur = win_end + timedelta(days=1)
        if not parts:
            return pd.DataFrame()
        out = pd.concat(parts, ignore_index=True)
        out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
        return out.drop_duplicates(["Date", "vessel_norm", "matcher_eta_days"])

    if cache_dir is None:
        return fetch()
    return _series_cache(cache_dir, cache_name, refresh, fetch)


def enrich_broker_vs_kpler_eta(
    meg: pd.DataFrame,
    ladder: pd.DataFrame,
    *,
    etas: tuple[int, ...] = MEG_AVAIL_ETAS,
) -> pd.DataFrame:
    """Compare broker open/ETA to Fujairah matcher windows (PIT when ladder is dated).

    Adds:
    - ``broker_target_date`` / ``broker_days_to_open`` (open_date else eta; PPT → NA)
    - ``kpler_min_eta_window`` — smallest matcher η where ship appears that as_of
    - ``kpler_can_make_broker_open`` — min window ≤ broker days-to-open (prompt→7 if already open)
    - per-window booleans ``kpler_in_fuj_eta{N}``
    """
    out = meg.copy()
    out["_d"] = pd.to_datetime(out["as_of"]).dt.normalize()
    # Broker commercial open date; ETA used only if open missing (PPT has no date).
    open_d = pd.to_datetime(out.get("open_date"), errors="coerce")
    eta_d = pd.to_datetime(out.get("eta"), errors="coerce")
    ppt = out["eta_is_ppt"].fillna(False) if "eta_is_ppt" in out.columns else False
    out["broker_target_date"] = open_d.fillna(eta_d)
    out.loc[ppt & open_d.isna(), "broker_target_date"] = pd.NaT
    out["broker_days_to_open"] = (out["broker_target_date"] - out["_d"]).dt.days

    for eta in etas:
        col = f"kpler_in_fuj_eta{eta}"
        out[col] = False

    out["kpler_min_eta_window"] = pd.NA
    out["kpler_matcher_next_eta"] = pd.NaT
    out["kpler_fuj_eta_pit_available"] = False

    if ladder is None or ladder.empty or "vessel_norm" not in ladder.columns:
        out["kpler_can_make_broker_open"] = pd.NA
        return out.drop(columns=["_d"], errors="ignore")

    lad = ladder.copy()
    lad["Date"] = pd.to_datetime(lad["Date"]).dt.normalize()
    out["kpler_fuj_eta_pit_available"] = True

    # Membership sets per (date, eta)
    for eta in etas:
        col = f"kpler_in_fuj_eta{eta}"
        keys = lad.loc[lad["matcher_eta_days"] == eta, ["Date", "vessel_norm"]].drop_duplicates()
        if keys.empty:
            continue
        hit = keys.assign(**{col: True})
        out = out.drop(columns=[col], errors="ignore")
        out = out.merge(hit, left_on=["_d", "vessel_norm"], right_on=["Date", "vessel_norm"], how="left")
        out[col] = out[col].eq(True)
        out = out.drop(columns=["Date"], errors="ignore")

    # Min window + next_eta from widest pull that contains the ship
    eta_cols = [f"kpler_in_fuj_eta{e}" for e in etas]
    def _min_eta(row) -> int | None:
        for e, c in zip(etas, eta_cols):
            if c in row.index and bool(row[c]):
                return int(e)
        return None

    out["kpler_min_eta_window"] = out.apply(_min_eta, axis=1)

    # Prefer next_eta from the smallest window row when available
    if "next_eta" in lad.columns:
        lad_sorted = lad.sort_values(["Date", "vessel_norm", "matcher_eta_days"])
        first = lad_sorted.groupby(["Date", "vessel_norm"], as_index=False).first()
        ne = first[["Date", "vessel_norm", "next_eta"]].rename(
            columns={"Date": "_d", "next_eta": "kpler_matcher_next_eta"}
        )
        ne["kpler_matcher_next_eta"] = pd.to_datetime(ne["kpler_matcher_next_eta"], errors="coerce")
        out = out.drop(columns=["kpler_matcher_next_eta"], errors="ignore")
        out = out.merge(ne, on=["_d", "vessel_norm"], how="left")

    # Can Kpler reach Fujairah by broker open?
    # Prefer dated matcher next_eta when present; else discrete η-window vs days-to-open.
    bar = pd.to_numeric(out["broker_days_to_open"], errors="coerce")
    bar_adj = bar.where(bar.isna() | (bar > 0), float(ETA_DAYS))
    min_w = pd.to_numeric(out["kpler_min_eta_window"], errors="coerce")
    nxt = pd.to_datetime(out.get("kpler_matcher_next_eta"), errors="coerce")
    tgt = pd.to_datetime(out["broker_target_date"], errors="coerce")
    can = pd.Series(pd.NA, index=out.index, dtype="object")
    by_next = tgt.notna() & nxt.notna()
    can.loc[by_next] = (nxt.loc[by_next].dt.normalize() <= tgt.loc[by_next].dt.normalize()).to_numpy()
    by_window = (~by_next) & tgt.notna() & min_w.notna()
    can.loc[by_window] = (min_w.loc[by_window] <= bar_adj.loc[by_window]).to_numpy()
    out["kpler_can_make_broker_open"] = can
    # Slack in days: broker target − kpler next_eta (or broker days − min window)
    slack = pd.Series(pd.NA, index=out.index, dtype="Float64")
    slack.loc[by_next] = (tgt.loc[by_next] - nxt.loc[by_next]).dt.days.astype("Float64")
    slack.loc[by_window] = (bar_adj.loc[by_window] - min_w.loc[by_window]).astype("Float64")
    out["kpler_vs_broker_eta_slack_days"] = slack
    return out.drop(columns=["_d"], errors="ignore")


def enrich_meg_list_kpler(
    meg: pd.DataFrame,
    vessels_live: pd.DataFrame,
    fixtures: pd.DataFrame | None = None,
    matcher: pd.DataFrame | None = None,
    *,
    fixture_lookback_days: int = 3,
) -> pd.DataFrame:
    """Left-join Clarksons MEG rows to Kpler live fleet + dated fixtures/matcher.

    Adds ``kpler_*`` columns and boolean ``*_pit_available`` flags. Live vessel
    state is stamped with ``pit_available=False`` so historical as_of rows are
    clearly not reconstructible — those fields will not show true day-over-day
    Kpler changes when the Clarksons date moves.
    """
    out = meg.copy()
    out["enrichment_run_at"] = pd.Timestamp.utcnow().tz_localize(None)

    # --- live fleet (no PIT) ---
    live_keep = [
        "vessel_norm",
        "vessel_imo",
        "vessel_status",
        "vessel_dead_weight",
        "vessel_type",
        "vessel_build_year",
        "last_port_call_location_name",
        "last_port_call_end",
        "next_destination_zone_name",
        "next destination eta",
        "vessel_availability_status",
        "vessel_availability_open",
        "Owners_names",
        "is_floating_storage",
        "last_speed_kn",
        "kpler_snapshot_at",
    ]
    live = vessels_live.copy()
    if not live.empty and "vessel_norm" in live.columns:
        live = live.drop_duplicates("vessel_norm", keep="last")
        have = [c for c in live_keep if c in live.columns]
        live = live[have].rename(
            columns={
                "vessel_imo": "kpler_imo",
                "vessel_status": "kpler_status",
                "vessel_dead_weight": "kpler_dwt",
                "vessel_type": "kpler_type",
                "vessel_build_year": "kpler_build_year",
                "last_port_call_location_name": "kpler_last_port",
                "last_port_call_end": "kpler_last_port_end",
                "next_destination_zone_name": "kpler_next_dest",
                "next destination eta": "kpler_next_eta",
                "vessel_availability_status": "kpler_avail_status",
                "vessel_availability_open": "kpler_avail_open",
                "Owners_names": "kpler_owners",
                "is_floating_storage": "kpler_floating_storage",
                "last_speed_kn": "kpler_speed_kn",
                "kpler_snapshot_at": "kpler_live_snapshot_at",
            }
        )
        out = out.merge(live, on="vessel_norm", how="left")
        out["kpler_name_matched"] = out["kpler_imo"].notna()
    else:
        out["kpler_name_matched"] = False

    # Live state: explicitly not PIT — will not show historical changes.
    out["kpler_vessel_state_pit_available"] = False
    out["kpler_vessel_state_note"] = (
        "Vessels.get is live-only; values are as-of enrichment_run_at, "
        "not as-of Clarksons as_of. Do not read day-over-day changes in these fields."
    )

    # --- fixtures (PIT via reported_date) ---
    out["kpler_fixture_pit_available"] = True
    out["kpler_n_fixtures_near"] = 0
    out["kpler_last_fixture_reported"] = pd.NaT
    out["kpler_last_fixture_origin"] = pd.NA
    out["kpler_last_fixture_dest"] = pd.NA
    out["kpler_last_fixture_rate"] = pd.NA
    if fixtures is not None and not fixtures.empty and "vessel_norm" in fixtures.columns:
        fx = fixtures.dropna(subset=["vessel_norm"]).copy()
        fx["reported_date"] = pd.to_datetime(fx.get("reported_date"), errors="coerce")
        fx_parts: list[pd.DataFrame] = []
        for as_of, chunk in out.groupby(pd.to_datetime(out["as_of"]).dt.normalize(), sort=False):
            lo = as_of - pd.Timedelta(days=fixture_lookback_days)
            hi = as_of + pd.Timedelta(days=1)
            sub = fx.loc[(fx["reported_date"] >= lo) & (fx["reported_date"] < hi)]
            if sub.empty:
                part = chunk.copy()
                part["kpler_n_fixtures_near"] = 0
                part["kpler_last_fixture_reported"] = pd.NaT
                part["kpler_last_fixture_origin"] = pd.NA
                part["kpler_last_fixture_dest"] = pd.NA
                part["kpler_last_fixture_rate"] = pd.NA
                fx_parts.append(part)
                continue
            counts = sub.groupby("vessel_norm").size().rename("kpler_n_fixtures_near")
            last = (
                sub.sort_values("reported_date")
                .groupby("vessel_norm", as_index=False)
                .tail(1)
                .rename(
                    columns={
                        "reported_date": "kpler_last_fixture_reported",
                        "origin": "kpler_last_fixture_origin",
                        "destination": "kpler_last_fixture_dest",
                        "rate_usd": "kpler_last_fixture_rate",
                    }
                )
            )
            keep = [
                "vessel_norm",
                "kpler_last_fixture_reported",
                "kpler_last_fixture_origin",
                "kpler_last_fixture_dest",
                "kpler_last_fixture_rate",
            ]
            keep = [c for c in keep if c in last.columns]
            part = chunk.drop(
                columns=[
                    "kpler_n_fixtures_near",
                    "kpler_last_fixture_reported",
                    "kpler_last_fixture_origin",
                    "kpler_last_fixture_dest",
                    "kpler_last_fixture_rate",
                ],
                errors="ignore",
            )
            part = part.merge(counts, on="vessel_norm", how="left")
            part = part.merge(last[keep], on="vessel_norm", how="left")
            part["kpler_n_fixtures_near"] = part["kpler_n_fixtures_near"].fillna(0).astype(int)
            fx_parts.append(part)
        out = pd.concat(fx_parts, ignore_index=True)

    # --- matcher (PIT for Date in window) ---
    out["kpler_matcher_pit_available"] = False
    out["kpler_in_matcher"] = False
    if matcher is not None and not matcher.empty and "vessel_norm" in matcher.columns:
        m = matcher.copy()
        date_col = "Date" if "Date" in m.columns else None
        if date_col:
            m[date_col] = pd.to_datetime(m[date_col], errors="coerce").dt.normalize()
            keys = (
                m.assign(_d=m[date_col], _in_matcher=True)[["vessel_norm", "_d", "_in_matcher"]]
                .drop_duplicates(["vessel_norm", "_d"])
            )
            out = out.copy()
            out["_d"] = pd.to_datetime(out["as_of"]).dt.normalize()
            out = out.drop(columns=["kpler_in_matcher"], errors="ignore")
            out = out.merge(keys, on=["vessel_norm", "_d"], how="left")
            out["kpler_in_matcher"] = out["_in_matcher"].eq(True)
            out = out.drop(columns=["_d", "_in_matcher"], errors="ignore")
            out["kpler_matcher_pit_available"] = True
        else:
            # No date on matcher → treat as live-only membership
            names = set(m["vessel_norm"].dropna())
            out["kpler_in_matcher"] = out["vessel_norm"].isin(names)
            out["kpler_matcher_pit_available"] = False

    return out


def fleet_development_summary_v2(repo_root: Path) -> dict[str, Any]:
    """All-fleet available count KPI. Summary periods on this key look stuck in 2019–20.

    Prefer fleet_development_available_series_v2 for a time series. Neither call is
    VLCC-filtered (summary rejects vesselTypes); treat as structural, not nowcast.
    """
    import requests

    r = requests.post(
        "https://api.kpler.com/v2/fleet-development/summary",
        headers=v2_headers(repo_root),
        json={"metric": "available", "granularity": "monthly", "aggMetric": "count"},
        timeout=40,
    )
    r.raise_for_status()
    return r.json()


def fleet_development_available_series_v2(repo_root: Path) -> pd.DataFrame:
    """Monthly all-fleet 'available' count from v2 series (not VLCC-specific)."""
    import requests

    r = requests.post(
        "https://api.kpler.com/v2/fleet-development/series",
        headers=v2_headers(repo_root),
        json={"metric": "available", "granularity": "monthly", "aggMetric": "count"},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    rows = []
    for item in payload.get("series") or []:
        date_str = item.get("date")
        val = None
        for ds in item.get("datasets") or []:
            vals = ds.get("values") or {}
            if "value" in vals:
                val = vals["value"]
                break
        rows.append({"Date": date_str, "available_count": val})
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["Date", "available_count"])
    # monthly labels like 2020-01
    out["Date"] = pd.to_datetime(out["Date"] + "-01", errors="coerce")
    out["available_count"] = pd.to_numeric(out["available_count"], errors="coerce")
    return out.dropna(subset=["Date"]).sort_values("Date")


# --- Tonnage-supply app helpers (zones / products / series / live fleet) ---

_LOCATION_TYPES = {
    "port",
    "sea",
    "gulf",
    "region",
    "country",
    "custom",
    "checkpoint",
    "anchorage",
    "strait",
    "bay",
    "canal",
}


def fetch_location_options(config, *, cache_path: Path | None = None, refresh: bool = False) -> pd.DataFrame:
    """Unique searchable destination names from Zones (port/sea/gulf/…)."""
    from kpler.sdk.resources.zones import Zones

    if cache_path and cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    raw = Zones(config).get()
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["name", "type"])
    df = raw.copy()
    df = df.loc[df["descendant_type"].astype(str).str.lower().isin(_LOCATION_TYPES)]
    out = (
        df[["descendant_name", "descendant_type"]]
        .dropna()
        .drop_duplicates(subset=["descendant_name"])
        .rename(columns={"descendant_name": "name", "descendant_type": "type"})
        .sort_values("name")
        .reset_index(drop=True)
    )
    # API accepts "Fujairah" even when Zones only lists checkpoints/anchorages.
    if not (out["name"] == FUJAIRAH_ZONE).any():
        out = pd.concat(
            [out, pd.DataFrame([{"name": FUJAIRAH_ZONE, "type": "custom"}])],
            ignore_index=True,
        )
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
    return out


def fetch_product_filter_options(config, *, cache_path: Path | None = None, refresh: bool = False) -> pd.DataFrame:
    """Flat product filter labels: Family + Group (matches Kpler last-product UI levels)."""
    from kpler.sdk.resources.products import Products

    if cache_path and cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    raw = Products(config).get(size=5000)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["label", "level", "family", "group"])

    rows: list[dict[str, str]] = []
    if "Family" in raw.columns:
        for fam in sorted(raw["Family"].dropna().astype(str).unique()):
            rows.append({"label": fam, "level": "family", "family": fam, "group": ""})
    if "Group" in raw.columns:
        for _, r in (
            raw[["Family", "Group"]].dropna().drop_duplicates().sort_values(["Family", "Group"]).iterrows()
        ):
            rows.append(
                {
                    "label": str(r["Group"]),
                    "level": "group",
                    "family": str(r["Family"]),
                    "group": str(r["Group"]),
                }
            )
    out = pd.DataFrame(rows)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
    return out


def tonnage_supply_series(
    config,
    destination: str,
    start: date,
    end: date | None = None,
    *,
    eta: int = ETA_DAYS,
    speed: int = SPEED_KN,
    metric: str = "count",
    vessel_types: list[str] | None = None,
    vessel_states: list[str] | None = None,
    products: list[str] | None = None,
    build_year_min: int | None = None,
    build_year_max: int | None = None,
    match_next_port_call: bool | None = None,
    split: str = "total",
) -> pd.DataFrame:
    """Daily tonnage-supply series (history chart). Metric: count | deadWeight | capacity."""
    from kpler.sdk import TonnageSupplySeriesMetric, TonnageSupplySeriesSplit
    from kpler.sdk.resources.tonnage_supply_series import TonnageSupplySeries

    end = end or date.today()
    metric_map = {
        "count": TonnageSupplySeriesMetric.Count,
        "deadweight": TonnageSupplySeriesMetric.DeadWeight,
        "dead_weight": TonnageSupplySeriesMetric.DeadWeight,
        "capacity": TonnageSupplySeriesMetric.Capacity,
    }
    split_map = {
        "total": TonnageSupplySeriesSplit.Total,
        "state": TonnageSupplySeriesSplit.State,
        "vesseltype": TonnageSupplySeriesSplit.VesselType,
        "vessel_type": TonnageSupplySeriesSplit.VesselType,
    }
    mkey = metric.replace(" ", "").lower()
    skey = split.replace(" ", "").lower()
    if mkey not in metric_map:
        raise ValueError(f"Unknown metric {metric!r}")
    if skey not in split_map:
        raise ValueError(f"Unknown split {split!r}")

    kw: dict[str, Any] = {
        "destination": destination,
        "eta": eta,
        "speed": speed,
        "start_date": start,
        "end_date": end,
        "metric": metric_map[mkey],
        "split": split_map[skey],
        "vessel_types": _resolve_vessel_types(vessel_types),
    }
    states = _resolve_vessel_states(vessel_states)
    if states:
        kw["vessel_states"] = states
    if products:
        kw["products"] = products
    if build_year_min is not None:
        kw["build_year_min"] = build_year_min
    if build_year_max is not None:
        kw["build_year_max"] = build_year_max
    if match_next_port_call is not None:
        kw["match_next_port_call"] = match_next_port_call

    client = TonnageSupplySeries(config)
    df = client.get(**kw)
    out = _ensure_date_col(df if df is not None else pd.DataFrame())
    if out.empty:
        return pd.DataFrame(columns=["Date", "value"])
    if "Total" in out.columns and "value" not in out.columns:
        out = out.rename(columns={"Total": "value"})
    elif "value" not in out.columns:
        num = [c for c in out.select_dtypes("number").columns if c != "Date"]
        if len(num) == 1:
            out = out.rename(columns={num[0]: "value"})
    return out


def vessels_live_snapshot(
    config,
    *,
    cache_path: Path | None = None,
    refresh: bool = False,
    with_freight_view: bool = True,
) -> pd.DataFrame:
    """Live Liquids vessels table (owner, build year, next dest). Cached when path set."""
    from kpler.sdk.resources.vessels import Vessels

    if cache_path and cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    cols = [
        "vessel_imo",
        "vessel_name",
        "vessel_build_year",
        "vessel_dead_weight",
        "Owners_names",
        "next_destination_zone_name",
        "next destination eta",
        "next_destination_source",
        "last_port_call_location_name",
        "vessel_status",
        "last_speed_kn",
    ]
    client = Vessels(config)
    try:
        df = client.get(columns=cols, with_freight_view=with_freight_view)
    except Exception:
        df = client.get(columns="all", with_freight_view=with_freight_view)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "vessel_imo" in out.columns:
        out["vessel_imo"] = pd.to_numeric(out["vessel_imo"], errors="coerce")
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
    return out


def liquids_vessel_type_labels() -> list[str]:
    """UI labels for LIQUIDS classifications on the matcher."""
    from kpler.sdk import TonnageSupplyVesselTypes

    liquids = [
        TonnageSupplyVesselTypes.VLCC,
        TonnageSupplyVesselTypes.SuezmaxLR3,
        TonnageSupplyVesselTypes.AframaxLR2,
        TonnageSupplyVesselTypes.PanamaxLR1,
        TonnageSupplyVesselTypes.MR,
        TonnageSupplyVesselTypes.HandyMR1,
        TonnageSupplyVesselTypes.IntermediateTankers,
        TonnageSupplyVesselTypes.ShortSeaTankers,
        TonnageSupplyVesselTypes.SmallTankers,
    ]
    return [m.value for m in liquids]
