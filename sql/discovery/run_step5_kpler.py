"""Phase 0 step 5: Kpler Liquids SDK entitlement probes.

Metadata only: status, row/col counts, date span, column ids.
Does not write vessel names, IMOs, cargoes, or metric values.
"""

from __future__ import annotations

import traceback
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)

ROOT = Path(__file__).resolve().parents[2]
ENV_CANDIDATES = [
    ROOT / ".env",
    ROOT.parent / "vessel_crossing" / ".env",
]


def _parse_env(path: Path) -> dict[str, str]:
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


def load_kpler_creds() -> tuple[str, str, str]:
    merged: dict[str, str] = {}
    used = ""
    for p in ENV_CANDIDATES:
        cred = _parse_env(p)
        if cred.get("KPLER_EMAIL") and cred.get("KPLER_PASSWORD"):
            merged = cred
            used = str(p.name)  # not full path with client names
            break
        merged.update(cred)
    email = merged.get("KPLER_EMAIL") or merged.get("EMAIL")
    password = merged.get("KPLER_PASSWORD") or merged.get("PASSWORD")
    if not email or not password:
        raise RuntimeError("KPLER_EMAIL / KPLER_PASSWORD not found in local .env files")
    return email, password, used


def summarize_df(df: pd.DataFrame) -> dict:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {"n_rows": 0, "n_cols": 0, "columns": "", "first_date": "", "last_date": ""}
    cols = [str(c) for c in df.columns]
    first_dt = last_dt = ""
    for cand in ("Date", "date", "reportedDate", "Date (timestamp)"):
        if cand in df.columns:
            s = pd.to_datetime(df[cand], errors="coerce")
            if s.notna().any():
                first_dt = str(s.min().date())
                last_dt = str(s.max().date())
                break
    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": ",".join(cols[:40]),
        "first_date": first_dt,
        "last_date": last_dt,
    }


def probe(name: str, fn) -> dict:
    row = {
        "endpoint": name,
        "ok": False,
        "error": "",
        "n_rows": None,
        "n_cols": None,
        "columns": "",
        "first_date": "",
        "last_date": "",
    }
    try:
        df = fn()
        meta = summarize_df(df)
        row.update(meta)
        row["ok"] = True
    except Exception as exc:
        msg = str(exc).replace("\n", " ")[:400]
        row["error"] = f"{type(exc).__name__}: {msg}"
        traceback.print_exc()
    print(f"{name}: ok={row['ok']} n={row['n_rows']} err={row['error'][:120] if row['error'] else ''}")
    return row


def main() -> None:
    from kpler.sdk import (
        BallastCapacitySeriesMetric,
        BallastCapacitySeriesPeriod,
        BallastCapacitySeriesSplit,
        CongestionSeriesMetric,
        CongestionSeriesPeriod,
        CongestionSeriesSplit,
        FleetUtilizationSeriesMetric,
        FleetUtilizationSeriesPeriod,
        FleetUtilizationSeriesSplit,
        FreightMetricsSeriesMetric,
        FreightMetricsSeriesPeriod,
        FreightMetricsSeriesSplit,
        FreightMetricsSeriesUnit,
        Platform,
        TonnageSupplySeriesMetric,
        TonnageSupplySeriesSplit,
        TonnageSupplyVesselTypes,
        VesselTypesOil,
    )
    from kpler.sdk.configuration import Configuration
    from kpler.sdk.resources.ballast_capacity_series import BallastCapacitySeries
    from kpler.sdk.resources.congestion_series import CongestionSeries
    from kpler.sdk.resources.fixtures import Fixtures
    from kpler.sdk.resources.fleet_utilization_series import FleetUtilizationSeries
    from kpler.sdk.resources.freight_metrics_series import FreightMetricsSeries
    from kpler.sdk.resources.tonnage_supply_series import TonnageSupplySeries
    from kpler.sdk.resources.tonnage_supply_vessels import TonnageSupplyVessels
    from kpler.sdk.resources.trades import Trades
    from kpler.sdk.resources.trades_snapshot import TradesSnapshot
    from kpler.sdk.resources.vessels import Vessels

    email, password, env_name = load_kpler_creds()
    print(f"creds_source={env_name} email_set=True")  # never print the email
    config = Configuration(Platform.Liquids, email, password, timeout=90, log_level="ERROR")
    print(f"auth_validated={config.auth_validated}")

    today = date.today()
    d7 = today - timedelta(days=7)
    d90 = today - timedelta(days=90)
    d365 = today - timedelta(days=365)

    rows: list[dict] = []

    trades = Trades(config)
    rows.append(probe("trades.get_columns", trades.get_columns))
    rows.append(
        probe(
            "trades.get_crude_last7d_count_only",
            lambda: trades.get(
                products=["crude"],
                start_date=d7,
                end_date=today,
                with_forecast=False,
                columns=["vessel_name", "start", "end"],
            ),
        )
    )

    snap = TradesSnapshot(config)
    rows.append(probe("trades_snapshot.get_columns", getattr(snap, "get_columns", lambda: pd.DataFrame())))

    vessels = Vessels(config)
    rows.append(probe("vessels.get_columns", vessels.get_columns))

    fx = Fixtures(config)
    rows.append(probe("fixtures.get_columns", fx.get_columns))
    rows.append(
        probe(
            "fixtures.get_vlcc_size5",
            lambda: fx.get(size=5, vessel_types_oil=[VesselTypesOil.VLCC], reported_date_after=d7),
        )
    )

    tss = TonnageSupplySeries(config)
    rows.append(
        probe(
            "tonnage_supply_series.vlcc_houston_90d",
            lambda: tss.get(
                destination="Houston",
                eta=7,
                speed=11,
                start_date=d90,
                end_date=today,
                metric=TonnageSupplySeriesMetric.Count,
                split=TonnageSupplySeriesSplit.VesselType,
                vessel_types=[TonnageSupplyVesselTypes.VLCC],
            ),
        )
    )

    tsv = TonnageSupplyVessels(config)
    rows.append(probe("tonnage_supply_vessels.get_columns", tsv.get_columns))
    rows.append(
        probe(
            "tonnage_supply_vessels.vlcc_houston_6d",
            lambda: tsv.get(
                destination="Houston",
                eta=7,
                speed=11,
                start_date=today - timedelta(days=5),
                end_date=today,
                vessel_types=[TonnageSupplyVesselTypes.VLCC],
            ),
        )
    )

    fus = FleetUtilizationSeries(config)
    rows.append(
        probe(
            "fleet_utilization_series.vlcc_90d",
            lambda: fus.get(
                start_date=d90,
                end_date=today,
                metric=FleetUtilizationSeriesMetric.Count,
                period=FleetUtilizationSeriesPeriod.Daily,
                split=FleetUtilizationSeriesSplit.State,
                vessel_types_oil=[VesselTypesOil.VLCC],
            ),
        )
    )

    fms = FreightMetricsSeries(config)
    rows.append(probe("freight_metrics_series.get_columns", fms.get_columns))
    rows.append(
        probe(
            "freight_metrics_tonmiles_vlcc_12m",
            lambda: fms.get(
                metric=FreightMetricsSeriesMetric.TonMiles,
                split=FreightMetricsSeriesSplit.VesselTypeOil,
                unit=FreightMetricsSeriesUnit.KTNMI,
                period=FreightMetricsSeriesPeriod.Monthly,
                start_date=d365,
                end_date=today,
                vessel_types_oil=[VesselTypesOil.VLCC],
                with_freight_view=False,
            ),
        )
    )
    rows.append(
        probe(
            "freight_metrics_tonmiles_with_freight_view",
            lambda: fms.get(
                metric=FreightMetricsSeriesMetric.TonMiles,
                split=FreightMetricsSeriesSplit.Total,
                unit=FreightMetricsSeriesUnit.KTNMI,
                period=FreightMetricsSeriesPeriod.Monthly,
                start_date=d365,
                end_date=today,
                vessel_types_oil=[VesselTypesOil.VLCC],
                with_freight_view=True,
            ),
        )
    )

    bcs = BallastCapacitySeries(config)
    rows.append(
        probe(
            "ballast_capacity_series.vlcc_30d",
            lambda: bcs.get(
                start_date=today - timedelta(days=30),
                end_date=today,
                metric=BallastCapacitySeriesMetric.Count,
                period=BallastCapacitySeriesPeriod.Daily,
                split=BallastCapacitySeriesSplit.VesselTypeOil,
                vessel_types_oil=[VesselTypesOil.VLCC],
                with_freight_view=False,
            ),
        )
    )
    rows.append(
        probe(
            "ballast_capacity_with_freight_view",
            lambda: bcs.get(
                start_date=today - timedelta(days=7),
                end_date=today,
                metric=BallastCapacitySeriesMetric.Count,
                period=BallastCapacitySeriesPeriod.Daily,
                split=BallastCapacitySeriesSplit.Total,
                with_freight_view=True,
            ),
        )
    )

    cgs = CongestionSeries(config)
    rows.append(
        probe(
            "congestion_series.china_vlcc_90d",
            lambda: cgs.get(
                start_date=d90,
                end_date=today,
                zones=["China"],
                metric=CongestionSeriesMetric.Count,
                period=CongestionSeriesPeriod.Weekly,
                split=CongestionSeriesSplit.VesselTypeOil,
                vessel_types_oil=[VesselTypesOil.VLCC],
                with_freight_view=False,
            ),
        )
    )
    rows.append(
        probe(
            "congestion_with_freight_view",
            lambda: cgs.get(
                start_date=d90,
                end_date=today,
                zones=["China"],
                metric=CongestionSeriesMetric.Count,
                period=CongestionSeriesPeriod.Monthly,
                split=CongestionSeriesSplit.Total,
                with_freight_view=True,
            ),
        )
    )

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "07_kpler_sdk_entitlements.csv", index=False)
    print("wrote 07_kpler_sdk_entitlements.csv", len(out))


if __name__ == "__main__":
    main()
