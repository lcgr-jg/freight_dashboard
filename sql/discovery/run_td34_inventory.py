"""Inventory TD34 (T34) vs TD3C (TDL) in ICE.MFT.FUTURES."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:td34-vs-td3c"


def fetch_df(cur) -> pd.DataFrame:
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


def main() -> None:
    cfg = SnowflakeConfig(
        database="ICE",
        schema="MFT",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # All TD34 / T34 product variants
        cur.execute(
            """
            SELECT
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              LONG_NAME,
              MIN(TRADE_DATE) AS FIRST_DT,
              MAX(TRADE_DATE) AS LAST_DT,
              COUNT(*) AS N_ROWS,
              COUNT(DISTINCT STRIP) AS N_STRIPS,
              COUNT(DISTINCT TRADE_DATE) AS N_SESSIONS,
              SUM(ZEROIFNULL(TOTAL_VOLUME)) AS SUM_VOL,
              SUM(ZEROIFNULL(OPEN_INTEREST)) AS SUM_OI,
              MIN(SETTLEMENT_PRICE) AS MIN_SETTLE,
              MAX(SETTLEMENT_PRICE) AS MAX_SETTLE,
              AVG(SETTLEMENT_PRICE) AS AVG_SETTLE
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE '%TD34%'
               OR REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'T34'
            GROUP BY 1, 2
            ORDER BY LAST_DT DESC, N_ROWS DESC
            """
        )
        products = fetch_df(cur)
        products.to_csv(OUT / "07_td34_products.csv", index=False)
        print("=== TD34 products ===")
        print(products.to_string(index=False))

        # FILE_FLAG coverage for T34
        cur.execute(
            """
            SELECT FILE_FLAG, SOURCE,
                   COUNT(*) AS n,
                   COUNT(OPEN_INTEREST) AS n_oi,
                   MIN(TRADE_DATE) AS first_dt,
                   MAX(TRADE_DATE) AS last_dt
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'T34'
            GROUP BY 1, 2
            ORDER BY 6 DESC
            """
        )
        flags = fetch_df(cur)
        flags.to_csv(OUT / "07_td34_file_flags.csv", index=False)
        print("\n=== T34 FILE_FLAG ===")
        print(flags.to_string(index=False))

        # Daily totals T34 vs TDL since T34 birth
        cur.execute(
            """
            WITH t34 AS (
              SELECT MIN(TRADE_DATE) AS birth
              FROM ICE.MFT.FUTURES
              WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'T34'
            )
            SELECT
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              TRADE_DATE,
              FILE_FLAG,
              COUNT(*) AS n_strips,
              SUM(ZEROIFNULL(TOTAL_VOLUME)) AS volume,
              SUM(ZEROIFNULL(OPEN_INTEREST)) AS oi,
              AVG(SETTLEMENT_PRICE) AS avg_settle
            FROM ICE.MFT.FUTURES, t34
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') IN ('T34', 'TDL')
              AND LONG_NAME NOT ILIKE '%Balmo%'
              AND LONG_NAME NOT ILIKE '%Mini%'
              AND LONG_NAME NOT ILIKE '%Option%'
              AND TRADE_DATE >= DATEADD('day', -14, t34.birth)
            GROUP BY 1, 2, 3
            ORDER BY 2, 1, 3
            """
        )
        daily = fetch_df(cur)
        daily.to_csv(OUT / "07_td34_tdl_daily.csv", index=False)
        print("\n=== daily T34/TDL (from 14d before T34 birth) ===")
        print(daily.to_string(index=False))

        # Front-month same-session compare (prefer Final, else Early)
        cur.execute(
            """
            SELECT
              TRADE_DATE,
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              STRIP,
              FILE_FLAG,
              SETTLEMENT_PRICE,
              TOTAL_VOLUME,
              OPEN_INTEREST,
              LONG_NAME
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') IN ('T34', 'TDL')
              AND LONG_NAME NOT ILIKE '%Balmo%'
              AND LONG_NAME NOT ILIKE '%Mini%'
              AND LONG_NAME NOT ILIKE '%Option%'
              AND TRADE_DATE >= (
                    SELECT MIN(TRADE_DATE) FROM ICE.MFT.FUTURES
                    WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'T34'
                  )
            ORDER BY TRADE_DATE, PRODUCT_CODE, STRIP, FILE_FLAG
            """
        )
        curves = fetch_df(cur)
        curves.to_csv(OUT / "07_td34_tdl_curves_raw.csv", index=False)
        print("\ncurve rows", len(curves))

        # Latest session strips for T34
        if len(products) and products["LAST_DT"].notna().any():
            last = products["LAST_DT"].max()
            cur.execute(
                """
                SELECT STRIP, FILE_FLAG, SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST
                FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'T34'
                  AND TRADE_DATE = %s
                ORDER BY STRIP, FILE_FLAG
                """,
                [last],
            )
            latest = fetch_df(cur)
            latest.to_csv(OUT / "07_td34_latest_curve.csv", index=False)
            print(f"\n=== T34 curve on {last} ===")
            print(latest.to_string(index=False))

        # Any other TD34-adjacent (daily/balmo)
        cur.execute(
            """
            SELECT REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS CODE, LONG_NAME,
                   MIN(TRADE_DATE), MAX(TRADE_DATE), COUNT(*)
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE '%Gulf of Oman%'
               OR LONG_NAME ILIKE '%GoO%'
               OR LONG_NAME ILIKE '%TD34%'
            GROUP BY 1, 2
            ORDER BY 4 DESC
            """
        )
        goo = fetch_df(cur)
        goo.to_csv(OUT / "07_td34_goo_name_hits.csv", index=False)
        print("\n=== Gulf of Oman / TD34 name hits ===")
        print(goo.to_string(index=False) if len(goo) else "none")

        cur.close()
    print("done")


if __name__ == "__main__":
    main()
