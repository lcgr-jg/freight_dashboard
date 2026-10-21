"""Probe TDL FILE_FLAG / OI coverage so the notebook loader is correct."""

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
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:td3c-oi-probe'")
        cur.execute(
            """
            SELECT FILE_FLAG, SOURCE,
                   COUNT(*) AS n,
                   COUNT(OPEN_INTEREST) AS n_oi,
                   COUNT(TOTAL_VOLUME) AS n_vol,
                   MIN(TRADE_DATE) AS first_dt,
                   MAX(TRADE_DATE) AS last_dt
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
            GROUP BY 1, 2
            ORDER BY 7 DESC, 3 DESC
            """
        )
        cov = fetch_df(cur)
        cov.to_csv(OUT / "06_tdl_file_flag_coverage.csv", index=False)
        print(cov.to_string(index=False))

        cur.execute(
            """
            SELECT TRADE_DATE, FILE_FLAG, SOURCE, COUNT(*) n,
                   COUNT(OPEN_INTEREST) n_oi,
                   SUM(ZEROIFNULL(OPEN_INTEREST)) sum_oi
            FROM ICE.MFT.FUTURES
            WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
              AND TRADE_DATE >= DATEADD('month', -18, CURRENT_DATE())
            GROUP BY 1, 2, 3
            ORDER BY 1 DESC, 2
            LIMIT 40
            """
        )
        daily = fetch_df(cur)
        daily.to_csv(OUT / "06_tdl_daily_file_flags.csv", index=False)
        print("\nrecent days")
        print(daily.head(25).to_string(index=False))
        cur.close()


if __name__ == "__main__":
    main()
