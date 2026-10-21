"""Check whether TD3C FFA has quarterly/calendar strips in ICE MFT."""

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector


def fetch_df(cur):
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


cfg = SnowflakeConfig(
    database="ICE",
    schema="MFT",
    role="JG_GENERAL",
    warehouse="EU_COMMOD_RESEARCH_XS_WH",
)
with SnowflakeConnector(cfg) as conn:
    cur = conn.cursor()
    cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:td3c-quarter-strips'")

    cur.execute(
        """
        SELECT
          REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
          LONG_NAME,
          COUNT(DISTINCT STRIP) AS N_STRIPS,
          MIN(TRADE_DATE) AS FIRST_DT,
          MAX(TRADE_DATE) AS LAST_DT,
          COUNT(*) AS N
        FROM ICE.MFT.FUTURES
        WHERE LONG_NAME ILIKE '%TD3C%'
        GROUP BY 1, 2
        ORDER BY LAST_DT DESC
        """
    )
    print(fetch_df(cur).to_string(index=False))

    cur.execute(
        """
        SELECT STRIP, COUNT(*) AS N, MIN(TRADE_DATE) AS FIRST_DT, MAX(TRADE_DATE) AS LAST_DT
        FROM ICE.MFT.FUTURES
        WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
          AND (
                STRIP ILIKE 'Q%' OR STRIP ILIKE 'Cal%' OR STRIP ILIKE 'CAL%'
                OR STRIP ILIKE '%Yr%' OR STRIP ILIKE '%Qtr%'
              )
        GROUP BY 1
        ORDER BY 1
        """
    )
    odd = fetch_df(cur)
    print("\nTDL odd strips", len(odd))
    print(odd.to_string(index=False) if len(odd) else "none")

    cur.execute(
        """
        SELECT DISTINCT STRIP
        FROM ICE.MFT.FUTURES
        WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
          AND TRADE_DATE = (
                SELECT MAX(TRADE_DATE) FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = 'TDL'
              )
        ORDER BY 1
        """
    )
    strips = fetch_df(cur)["STRIP"].tolist()
    print("\nlatest TDL n", len(strips))
    print(strips)
    cur.close()
