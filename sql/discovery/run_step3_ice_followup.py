"""Follow-up: TDL/WHK front strips, FILE_FLAG duplicates, TD20 monthly hunt."""

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"


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
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:discovery-ice-ffas-followup'")

        cur.execute(
            """
            SELECT FILE_FLAG, SOURCE, COUNT(*) n
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
              AND TRADE_DATE = '2026-10-05'
            GROUP BY 1, 2
            ORDER BY 3 DESC
            """
        )
        print("file_flag")
        print(fetch_df(cur).to_string(index=False))

        cur.execute(
            """
            SELECT TRADE_DATE, STRIP, FILE_FLAG, SOURCE, SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
              AND TRADE_DATE = '2026-10-05'
              AND STRIP IN ('Oct26','Nov26','Dec26','Jan27','Q4-26','Cal27','Oct-26','Nov-26')
            ORDER BY STRIP, FILE_FLAG, SOURCE
            """
        )
        front = fetch_df(cur)
        front.to_csv(OUT / "05_ice_tdl_front_2026-10-05.csv", index=False)
        print("tdl_front")
        print(front.to_string(index=False))

        cur.execute(
            """
            SELECT DISTINCT STRIP
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
              AND TRADE_DATE = '2026-10-05'
            ORDER BY 1
            """
        )
        strips = fetch_df(cur)
        strips.to_csv(OUT / "05_ice_tdl_strips_2026-10-05.csv", index=False)
        print("n_strips", len(strips))
        print(strips.head(40).to_string(index=False))

        # TD20 monthly? LONG_NAME like TD20 and not mini/balmo
        cur.execute(
            """
            SELECT
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              LONG_NAME,
              MIN(TRADE_DATE) first_dt,
              MAX(TRADE_DATE) last_dt,
              COUNT(*) n
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE '%TD20%'
            GROUP BY 1, 2
            ORDER BY last_dt DESC, n DESC
            """
        )
        td20 = fetch_df(cur)
        td20.to_csv(OUT / "05_ice_td20_products.csv", index=False)
        print("td20")
        print(td20.to_string(index=False))

        # WHK front Oct26
        cur.execute(
            """
            SELECT TRADE_DATE, STRIP, FILE_FLAG, SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'WHK'
              AND TRADE_DATE = '2026-10-05'
              AND STRIP IN ('Oct26','Nov26','Dec26','Jan27')
            ORDER BY STRIP, FILE_FLAG
            """
        )
        print("whk_front")
        print(fetch_df(cur).to_string(index=False))

        # DFN strip for 2026-10-05 itself (daily settlement vs Baltic)
        cur.execute(
            """
            SELECT TRADE_DATE, STRIP, FILE_FLAG, SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'DFN'
              AND TRADE_DATE = '2026-10-05'
              AND (STRIP ILIKE 'Oct-05-26' OR STRIP ILIKE 'Oct-06-26' OR STRIP ILIKE '%Oct-05%'
                   OR STRIP = 'Oct26' OR STRIP ILIKE '05-Oct%' OR STRIP ILIKE 'Oct 5%')
            ORDER BY STRIP, FILE_FLAG
            LIMIT 40
            """
        )
        print("dfn_spotish")
        print(fetch_df(cur).to_string(index=False))

        cur.execute(
            """
            SELECT DISTINCT STRIP
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'DFN'
              AND TRADE_DATE = '2026-10-05'
              AND STRIP ILIKE '%Oct%26%'
            ORDER BY 1
            LIMIT 40
            """
        )
        print("dfn_oct26_strips")
        print(fetch_df(cur).to_string(index=False))

        cur.close()
    print("done")


if __name__ == "__main__":
    main()
