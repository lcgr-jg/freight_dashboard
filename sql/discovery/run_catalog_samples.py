"""Extra samples for catalog candidates after steps 1-2."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)


def fetch_df(cur) -> pd.DataFrame:
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def main() -> None:
    cfg = SnowflakeConfig(
        database="SPGICI_MARKETDATA_SHARE",
        schema="MDV2",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:discovery-catalog-samples'")

        cur.execute(
            """
            SELECT SYMBOL, DESCRIPTION, COMMODITY, VESSEL_CLASS, UOM, QUOTATION_STYLE, MDC
            FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
            WHERE DESCRIPTION ILIKE %s
               OR DESCRIPTION ILIKE %s
               OR (DESCRIPTION ILIKE %s AND (DESCRIPTION ILIKE %s OR DESCRIPTION ILIKE %s))
            LIMIT 80
            """,
            ["%Dirty Tanker%", "%Clean Tanker%", "%Dirty%", "%Wsc%", "%$/mt%"],
        )
        df = fetch_df(cur)
        df.to_csv(OUT / "04_platts_tanker_assessments_sample.csv", index=False)
        print("platts_tanker", len(df))
        print(df.head(25).to_string(index=False))

        cur.execute(
            """
            SELECT VESSEL_CLASS, COUNT(*) AS n
            FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
            WHERE VESSEL_CLASS IS NOT NULL
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 40
            """
        )
        df = fetch_df(cur)
        df.to_csv(OUT / "04_platts_vessel_class.csv", index=False)
        print("vessel_class")
        print(df.to_string(index=False))

        cur.execute(
            """
            SELECT LONG_NAME, COUNT(*) AS n
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE %s
              AND (
                    LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s
                    OR LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s
                  )
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 60
            """,
            ["%FFA%", "%TD3%", "%TD15%", "%TD20%", "%TD22%", "%TC14%", "%TC2 %"],
        )
        df = fetch_df(cur)
        df.to_csv(OUT / "04_ice_ffa_route_products.csv", index=False)
        print("ice_ffa_routes", len(df))
        print(df.to_string(index=False))

        cur.execute(
            """
            SELECT
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              COUNT(*) AS n,
              MIN(LONG_NAME) AS EXAMPLE
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE %s
              AND (LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s OR LONG_NAME ILIKE %s)
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 50
            """,
            ["%FFA%", "%Baltic%", "%Wet Freight%", "%TD3%"],
        )
        df = fetch_df(cur)
        df.to_csv(OUT / "04_ice_ffa_product_codes.csv", index=False)
        print("ice_codes")
        print(df.to_string(index=False))

        # ArbFlow preferred freight flag meaning
        cur.execute(
            """
            SELECT column_name, data_type
            FROM SPGICI_ARBFLOW.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='ARBFLOW_V2' AND table_name='MARGINS_CATALOG'
            ORDER BY ordinal_position
            """
        )
        fetch_df(cur).to_csv(OUT / "04_arbflow_margins_catalog_cols.csv", index=False)

        cur.close()
    print("done")


if __name__ == "__main__":
    main()
