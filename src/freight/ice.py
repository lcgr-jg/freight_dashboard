"""ICE wet-freight futures helpers.

Prices are USD/t. Open interest is only populated on FILE_FLAG='Final'
(Early EOD has settle/volume, OI null) — prefer Final, fall back to Early
for the latest session's curve.
"""

from __future__ import annotations

import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ICE futures month letters (not calendar sequential: no I, no L)
ICE_MONTH_LETTER = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}
STRIP_MONTH = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# TD3C cargo used to translate lots into "ships of paper"
TD3C_CARGO_T = 270_000
TDL_LOT_T = 1_000  # ICE monthly spec


def ice_contract_code(contract_month: date) -> str:
    """e.g. 2026-10-01 -> V6 (October 2026)."""
    letter = ICE_MONTH_LETTER[contract_month.month]
    yy = contract_month.year % 10
    return f"{letter}{yy}"


def parse_dated_strip(strip: str) -> date | None:
    """Parse daily/balmo strip 'Oct-05-26' -> date."""
    if not isinstance(strip, str) or strip.count("-") != 2:
        return None
    mon, dd, yy = strip.split("-")
    if mon not in STRIP_MONTH or not dd.isdigit() or not yy.isdigit():
        return None
    try:
        return date(2000 + int(yy), STRIP_MONTH[mon], int(dd))
    except ValueError:
        return None


def parse_monthly_strip(strip: str) -> date | None:
    """Parse ICE MFT monthly strip 'Oct26' -> first of month. Dated strips return None."""
    if not isinstance(strip, str) or len(strip) < 5:
        return None
    mon, yy = strip[:3], strip[3:]
    if mon not in STRIP_MONTH or not yy.isdigit() or len(yy) != 2:
        return None
    year = 2000 + int(yy)
    return date(year, STRIP_MONTH[mon], 1)


def last_trading_day(contract_month: date) -> date:
    """ICE wet freight: LTD = last calendar day of month; December expires the 24th
    (or prior weekday if 24th is a weekend). Close enough for DTE charts."""
    if contract_month.month == 12:
        ltd = date(contract_month.year, 12, 24)
        if ltd.weekday() >= 5:
            ltd -= timedelta(days=ltd.weekday() - 4)
        return ltd
    last = monthrange(contract_month.year, contract_month.month)[1]
    return date(contract_month.year, contract_month.month, last)


def prefer_final(df: pd.DataFrame) -> pd.DataFrame:
    """One row per trade_date × strip: Final beats Early."""
    out = df.copy()
    out["_rank"] = out["FILE_FLAG"].map({"Final": 0, "Early": 1}).fillna(9)
    out = (
        out.sort_values(["TRADE_DATE", "STRIP", "_rank"])
        .drop_duplicates(["TRADE_DATE", "STRIP"], keep="first")
        .drop(columns="_rank")
    )
    return out


def enrich_monthly(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["TRADE_DATE"] = pd.to_datetime(out["TRADE_DATE"]).dt.date
    out["CONTRACT_MONTH"] = out["STRIP"].map(parse_monthly_strip)
    out = out.loc[out["CONTRACT_MONTH"].notna()].copy()
    out["LTD"] = out["CONTRACT_MONTH"].map(last_trading_day)
    out["DTE"] = [
        (ltd - td).days for td, ltd in zip(out["TRADE_DATE"], out["LTD"], strict=True)
    ]
    out["DAYS_TO_EXPIRY"] = -out["DTE"]  # same sign as the crude OI-vs-DTE charts
    out["CONTRACT_CODE"] = out["CONTRACT_MONTH"].map(ice_contract_code)
    out["OI_LOTS"] = pd.to_numeric(out["OPEN_INTEREST"], errors="coerce")
    out["VOLUME_LOTS"] = pd.to_numeric(out["TOTAL_VOLUME"], errors="coerce")
    out["SETTLE_USD_T"] = pd.to_numeric(out["SETTLEMENT_PRICE"], errors="coerce")
    out["OI_CARGOES"] = out["OI_LOTS"] * TDL_LOT_T / TD3C_CARGO_T
    return out.sort_values(["TRADE_DATE", "CONTRACT_MONTH"]).reset_index(drop=True)


def _ensure_desk_core() -> None:
    try:
        import desk_core  # noqa: F401
        return
    except ModuleNotFoundError:
        coding = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(coding / "desk_core"))


def load_ffa_monthly(
    product_code: str = "TDL",
    start: date | None = None,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Pull one ICE monthly FFA product. Caches parquet under cache_dir."""
    start = start or date(2016, 1, 1)
    cache_dir = cache_dir or Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"ice_{product_code.lower()}_monthly.parquet"
    if cache.exists() and not refresh:
        df = pd.read_parquet(cache)
        df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
        if "CONTRACT_MONTH" in df.columns:
            df["CONTRACT_MONTH"] = pd.to_datetime(df["CONTRACT_MONTH"]).dt.date
        if "LTD" in df.columns:
            df["LTD"] = pd.to_datetime(df["LTD"]).dt.date
        return df

    _ensure_desk_core()
    from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

    sql = """
        SELECT TRADE_DATE, STRIP, FILE_FLAG, SOURCE,
               SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST, LONG_NAME
        FROM ICE.MFT.FUTURES
        WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = %s
          AND LONG_NAME NOT ILIKE %s
          AND LONG_NAME NOT ILIKE %s
          AND LONG_NAME NOT ILIKE %s
          AND TRADE_DATE >= %s
        """
    cfg = SnowflakeConfig(
        database="ICE",
        schema="MFT",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:td3c-ffa-notebook'")
        cur.execute(sql, [product_code, "%Balmo%", "%Mini%", "%Option%", start])
        cols = [c[0] for c in cur.description]
        raw = pd.DataFrame(cur.fetchall(), columns=cols)
        cur.close()

    tidy = enrich_monthly(prefer_final(raw))
    tidy.to_parquet(cache, index=False)
    return tidy


def load_daily_prompt(
    product_code: str = "DFN",
    start: date | None = None,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Daily mini FFA: keep the strip that matches the trade date (index-day proxy)."""
    start = start or date(2018, 1, 1)
    cache_dir = cache_dir or Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"ice_{product_code.lower()}_prompt.parquet"
    if cache.exists() and not refresh:
        df = pd.read_parquet(cache)
        df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
        return df

    _ensure_desk_core()
    from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

    sql = """
        SELECT TRADE_DATE, STRIP, FILE_FLAG,
               SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST, LONG_NAME
        FROM ICE.MFT.FUTURES
        WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = %s
          AND TRADE_DATE >= %s
        """
    cfg = SnowflakeConfig(
        database="ICE",
        schema="MFT",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:td3c-ffa-notebook'")
        cur.execute(sql, [product_code, start])
        raw = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
        cur.close()

    raw = prefer_final(raw)
    raw["TRADE_DATE"] = pd.to_datetime(raw["TRADE_DATE"]).dt.date
    raw["STRIP_DATE"] = raw["STRIP"].map(parse_dated_strip)
    prompt = raw.loc[raw["STRIP_DATE"] == raw["TRADE_DATE"]].copy()
    prompt["SETTLE_USD_T"] = pd.to_numeric(prompt["SETTLEMENT_PRICE"], errors="coerce")
    prompt.to_parquet(cache, index=False)
    return prompt


def asof(df: pd.DataFrame, as_of: date | None = None) -> tuple[date, pd.DataFrame]:
    """Latest session with any rows, optionally capped at as_of."""
    dates = sorted(df["TRADE_DATE"].unique())
    if as_of is not None:
        dates = [d for d in dates if d <= as_of]
    if not dates:
        raise ValueError("no sessions in range")
    session = dates[-1]
    return session, df.loc[df["TRADE_DATE"] == session].copy()


def front_n(snap: pd.DataFrame, n: int = 12, session: date | None = None) -> pd.DataFrame:
    """Listed contracts with LTD on/after session, first n by month."""
    session = session or snap["TRADE_DATE"].max()
    live = snap.loc[snap["LTD"] >= session].sort_values("CONTRACT_MONTH")
    return live.head(n)


def total_oi(df: pd.DataFrame) -> pd.DataFrame:
    """Sum OI across listed strips; Final-only days (Early has all-null OI)."""
    g = (
        df.groupby("TRADE_DATE", as_index=False)
        .agg(OI_LOTS=("OI_LOTS", "sum"), VOLUME_LOTS=("VOLUME_LOTS", "sum"))
    )
    g["OI_CARGOES"] = g["OI_LOTS"] * TDL_LOT_T / TD3C_CARGO_T
    return g


def oi_delta(prev: pd.DataFrame, curr: pd.DataFrame) -> pd.DataFrame:
    a = curr.set_index("CONTRACT_MONTH")[["CONTRACT_CODE", "STRIP", "OI_LOTS", "SETTLE_USD_T"]]
    b = prev.set_index("CONTRACT_MONTH")[["OI_LOTS"]].rename(columns={"OI_LOTS": "OI_PREV"})
    out = a.join(b, how="left")
    out["OI_DELTA"] = out["OI_LOTS"] - out["OI_PREV"]
    return out.reset_index()
