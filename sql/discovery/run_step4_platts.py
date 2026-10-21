"""Phase 0 step 4: Platts freight / bunkers / arb-leg inventory via desk_core.

Metadata + coverage on curated symbols only. Writes CSVs under sql/discovery/_runs/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:discovery-platts"

REF = "SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA"
PRICE = "SPGICI_MARKETDATA_SHARE.MDV2.PRICEDATA"

# Columns we actually use from REF (keep SELECT tight).
REF_COLS = """
    SYMBOL, DESCRIPTION, COMMODITY, VESSEL_CLASS, UOM, QUOTATION_STYLE,
    ASSESSMENT_FREQUENCY, CARGO_SIZE, STANDARD_LOT_SIZE, STANDARD_LOT_UNITS,
    CURRENCY, MDC, MDC_DESCRIPTION, ORIGINATING_REGION, DELIVERY_REGION,
    SHIPPING_TERMS, CONTRACT_TYPE, ACTIVE, BENCHMARK
"""


def fetch_df(cur) -> pd.DataFrame:
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def run(cur, name: str, sql: str, params: list | None = None) -> pd.DataFrame:
    cur.execute(sql, params or [])
    df = fetch_df(cur)
    path = OUT / name
    df.to_csv(path, index=False)
    print(f"{name}: {len(df)} rows")
    return df


def main() -> None:
    cfg = SnowflakeConfig(
        database="SPGICI_MARKETDATA_SHARE",
        schema="MDV2",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # --- 1. Shipping universe profile ---
        run(
            cur,
            "06_platts_shipping_profile.csv",
            f"""
            SELECT
              COALESCE(COMMODITY, '(null)') AS COMMODITY,
              COALESCE(VESSEL_CLASS, '(null)') AS VESSEL_CLASS,
              COALESCE(UOM, '(null)') AS UOM,
              COALESCE(QUOTATION_STYLE, '(null)') AS QUOTATION_STYLE,
              IFF(DESCRIPTION ILIKE %s, 'MAvg', 'not_MAvg') AS MAVG_FLAG,
              COUNT(*) AS N_SYMBOLS
            FROM {REF}
            WHERE COMMODITY = 'Shipping'
               OR MDC ILIKE %s
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY N_SYMBOLS DESC
            """,
            ["%MAvg%", "%FRE%"],
        )

        # --- 2. Dirty / clean tanker assessments (spot + MAvg) ---
        tankers = run(
            cur,
            "06_platts_tanker_inventory.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE COMMODITY = 'Shipping'
              AND (
                    DESCRIPTION ILIKE 'Dirty %'
                 OR DESCRIPTION ILIKE 'Clean %'
                 OR DESCRIPTION ILIKE '%Tanker%'
                 OR DESCRIPTION ILIKE '% Wsc%'
                 OR DESCRIPTION ILIKE '%Wsc %'
              )
              AND DESCRIPTION NOT ILIKE '%Capesize%'
              AND DESCRIPTION NOT ILIKE '%Supramax%'
              AND DESCRIPTION NOT ILIKE '%Handysize%'
              AND DESCRIPTION NOT ILIKE '%Ultramax%'
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        # --- 3. Bunkers at core bunker hubs ---
        run(
            cur,
            "06_platts_bunker_inventory.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE (
                    DESCRIPTION ILIKE '%Bunker%'
                 OR DESCRIPTION ILIKE '%VLSFO%'
                 OR DESCRIPTION ILIKE '%HSFO%'
                 OR DESCRIPTION ILIKE '%380 CST%'
                 OR DESCRIPTION ILIKE '%MGO%'
                 OR DESCRIPTION ILIKE '%Marine Gasoil%'
                 OR COMMODITY ILIKE '%Bunker%'
              )
              AND (
                    DESCRIPTION ILIKE '%Singapore%'
                 OR DESCRIPTION ILIKE '%Rotterdam%'
                 OR DESCRIPTION ILIKE '%Fujairah%'
                 OR DESCRIPTION ILIKE '%Houston%'
                 OR DESCRIPTION ILIKE '%USGC%'
                 OR DESCRIPTION ILIKE '%ARA%'
                 OR DESCRIPTION ILIKE '%Gibraltar%'
                 OR DESCRIPTION ILIKE '%Panama%'
                 OR DESCRIPTION ILIKE '%Suez%'
                 OR DESCRIPTION ILIKE '%Ras Tanura%'
                 OR DELIVERY_REGION ILIKE '%Singapore%'
                 OR DELIVERY_REGION ILIKE '%Rotterdam%'
                 OR DELIVERY_REGION ILIKE '%Fujairah%'
                 OR DELIVERY_REGION ILIKE '%Houston%'
              )
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        # --- 4. Crude arb legs ---
        run(
            cur,
            "06_platts_arb_crude.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE (
                    DESCRIPTION ILIKE 'Dated Brent%'
                 OR DESCRIPTION ILIKE 'Brent Dated%'
                 OR DESCRIPTION ILIKE '%Dubai%' AND (DESCRIPTION ILIKE '%Crude%' OR COMMODITY ILIKE '%Crude%')
                 OR DESCRIPTION ILIKE 'Oman%' AND COMMODITY ILIKE '%Crude%'
                 OR DESCRIPTION ILIKE '%Murban%'
                 OR DESCRIPTION ILIKE '%WTI Houston%'
                 OR DESCRIPTION ILIKE '%WTI Midland%'
                 OR DESCRIPTION ILIKE 'Mars%' AND COMMODITY ILIKE '%Crude%'
                 OR DESCRIPTION ILIKE '%WCS%' AND COMMODITY ILIKE '%Crude%'
                 OR DESCRIPTION ILIKE 'ASP%' AND DESCRIPTION ILIKE '%Dubai%'
              )
              AND DESCRIPTION NOT ILIKE '%Freight%'
              AND DESCRIPTION NOT ILIKE '%Tanker%'
              AND DESCRIPTION NOT ILIKE '%Bunker%'
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        # --- 5. Product arb legs (diesel / gasoline / naphtha at four hubs) ---
        run(
            cur,
            "06_platts_arb_products.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE (
                    DESCRIPTION ILIKE '%ULSD%'
                 OR DESCRIPTION ILIKE '%Gasoil%'
                 OR DESCRIPTION ILIKE '%Diesel%'
                 OR DESCRIPTION ILIKE '%Gasoline%'
                 OR DESCRIPTION ILIKE '%Naphtha%'
              )
              AND (
                    DESCRIPTION ILIKE '%NWE%'
                 OR DESCRIPTION ILIKE '%ARA%'
                 OR DESCRIPTION ILIKE '%USGC%'
                 OR DESCRIPTION ILIKE '%US Gulf%'
                 OR DESCRIPTION ILIKE '%Singapore%'
                 OR DESCRIPTION ILIKE '%Arab Gulf%'
                 OR DESCRIPTION ILIKE '%Persian Gulf%'
                 OR DESCRIPTION ILIKE '%AG %'
              )
              AND DESCRIPTION NOT ILIKE '%Freight%'
              AND DESCRIPTION NOT ILIKE '%Tanker%'
              AND DESCRIPTION NOT ILIKE '%Bunker%'
              AND DESCRIPTION NOT ILIKE '%Swap%'
              AND DESCRIPTION NOT ILIKE '%Futures%'
              AND DESCRIPTION NOT ILIKE '%MAvg%'
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        # --- 6. eWindow dictionary: is there a freight market? ---
        # Column names vary; pull INFORMATION_SCHEMA first then keyword-search text cols.
        ewin_cols = run(
            cur,
            "06_ewindow_dictionary_columns.csv",
            """
            SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
            FROM SPGICI_EWINDOW_MARKETDATA.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'EWMD' AND TABLE_NAME = 'EWINDOW_DICTIONARY'
            ORDER BY ORDINAL_POSITION
            """,
        )
        text_cols = [
            str(c)
            for c in ewin_cols["COLUMN_NAME"].tolist()
            if str(c).upper()
            in {
                "MARKET",
                "HUB",
                "PRODUCT",
                "INSTRUMENT",
                "DESCRIPTION",
                "COMMODITY",
                "STRIP",
            }
        ]
        if text_cols:
            where = " OR ".join(f"COALESCE({c}::string, '') ILIKE %s" for c in text_cols)
            params = ["%freight%"] * len(text_cols)
            # Second pass tanker
            where2 = " OR ".join(f"COALESCE({c}::string, '') ILIKE %s" for c in text_cols)
            params2 = ["%tanker%"] * len(text_cols)
            run(
                cur,
                "06_ewindow_freight_dictionary.csv",
                f"""
                SELECT *
                FROM SPGICI_EWINDOW_MARKETDATA.EWMD.EWINDOW_DICTIONARY
                WHERE ({where}) OR ({where2})
                LIMIT 200
                """,
                params + params2,
            )
        else:
            print("eWindow dictionary: no expected text columns; skipping keyword search")

        # --- 7. Platts forward curves schema: any freight-named objects? ---
        run(
            cur,
            "06_platts_fc_freight_tables.csv",
            """
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM SPGICI_MARKETDATA_SHARE.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'FC'
              AND (
                    COLUMN_NAME ILIKE %s
                 OR COLUMN_NAME ILIKE %s
                 OR TABLE_NAME ILIKE %s
              )
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            ["%FREIGHT%", "%TANKER%", "%FREIGHT%"],
        )

        # --- 8. PRICEDATA coverage for curated tanker + later lists ---
        # Daily (not MAvg) tanker symbols only — smaller, more useful.
        daily_tankers = tankers
        if not daily_tankers.empty:
            desc = daily_tankers["DESCRIPTION"].astype(str)
            daily_tankers = daily_tankers.loc[~desc.str.contains("MAvg", case=False)].copy()

        # Cap coverage query: prefer Dirty/Clean daily with WSC or MT.
        if not daily_tankers.empty:
            uom = daily_tankers["UOM"].astype(str).str.upper()
            daily_tankers = daily_tankers.loc[uom.isin(["WSC", "MT"])].copy()

        symbols = []
        if not daily_tankers.empty:
            symbols.extend(daily_tankers["SYMBOL"].astype(str).unique().tolist())

        # Coverage query built after we also load bunker/arb CSVs from this same run.
        bunkers = pd.read_csv(OUT / "06_platts_bunker_inventory.csv")
        crude = pd.read_csv(OUT / "06_platts_arb_crude.csv")
        products = pd.read_csv(OUT / "06_platts_arb_products.csv")

        def pick_daily(df: pd.DataFrame, n: int = 80) -> list[str]:
            if df.empty:
                return []
            d = df.copy()
            desc = d["DESCRIPTION"].astype(str)
            d = d.loc[~desc.str.contains("MAvg", case=False)]
            # Prefer *00 daily codes when present
            d["_rank"] = d["SYMBOL"].astype(str).str.endswith("00").map({True: 0, False: 1})
            d = d.sort_values(["_rank", "DESCRIPTION"])
            return d["SYMBOL"].astype(str).unique().tolist()[:n]

        symbols.extend(pick_daily(bunkers, 60))
        symbols.extend(pick_daily(crude, 40))
        symbols.extend(pick_daily(products, 60))
        # Unique, keep order
        seen: set[str] = set()
        uniq: list[str] = []
        for s in symbols:
            if s and s not in seen:
                seen.add(s)
                uniq.append(s)

        print(f"coverage_symbols={len(uniq)}")
        pd.Series(uniq, name="SYMBOL").to_csv(OUT / "06_platts_coverage_symbols.csv", index=False)

        if uniq:
            # Snowflake IN list — bind as a temp table via VALUES to avoid giant IN.
            values_sql = ", ".join(f"('{s.replace(chr(39), '')}')" for s in uniq)
            cov = run(
                cur,
                "06_platts_pricedata_coverage.csv",
                f"""
                SELECT
                  p.SYMBOL,
                  MIN(p.ASSESSDATE::date) AS FIRST_ASSESS,
                  MAX(p.ASSESSDATE::date) AS LAST_ASSESS,
                  COUNT(*) AS N_ROWS,
                  COUNT(DISTINCT p.BATE) AS N_BATE,
                  SUM(IFF(p.BATE = 'c', 1, 0)) AS N_CLOSE
                FROM {PRICE} p
                WHERE p.SYMBOL IN ({values_sql})
                GROUP BY 1
                ORDER BY LAST_ASSESS DESC NULLS LAST, N_ROWS DESC
                """,
            )
            print("coverage last dates:")
            print(cov.head(15).to_string(index=False))

        # BATE codes on a single known-style tanker symbol if we have one
        probe = None
        if not daily_tankers.empty:
            probe = str(daily_tankers.iloc[0]["SYMBOL"])
        if probe:
            run(
                cur,
                "06_platts_bate_probe.csv",
                f"""
                SELECT SYMBOL, BATE, COUNT(*) AS N,
                       MIN(ASSESSDATE::date) AS FIRST_DT,
                       MAX(ASSESSDATE::date) AS LAST_DT
                FROM {PRICE}
                WHERE SYMBOL = %s
                GROUP BY 1, 2
                ORDER BY N DESC
                """,
                [probe],
            )

        # Latest close snapshot for a short curated list (values stay on-box CSVs).
        if uniq:
            sample = uniq[:25]
            values_sql = ", ".join(f"('{s.replace(chr(39), '')}')" for s in sample)
            run(
                cur,
                "06_platts_latest_closes_sample.csv",
                f"""
                WITH latest AS (
                  SELECT SYMBOL, MAX(ASSESSDATE) AS MAX_DT
                  FROM {PRICE}
                  WHERE SYMBOL IN ({values_sql})
                    AND BATE = 'c'
                  GROUP BY 1
                )
                SELECT p.SYMBOL, p.ASSESSDATE::date AS ASSESSDATE, p.VALUE, p.BATE
                FROM {PRICE} p
                JOIN latest l
                  ON p.SYMBOL = l.SYMBOL AND p.ASSESSDATE = l.MAX_DT
                WHERE p.BATE = 'c'
                ORDER BY p.SYMBOL
                """,
            )


if __name__ == "__main__":
    main()
