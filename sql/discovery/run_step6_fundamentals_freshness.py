"""Probe refresh / staleness for World Oil Supply PRODUCTION and Global Oil Demand."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
TAG = "freight-agent:discovery-fundamentals-fresh"


def run(cur, name: str, sql: str) -> pd.DataFrame:
    cur.execute(sql)
    df = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
    df.to_csv(OUT / name, index=False)
    print(f"\n=== {name} ({len(df)} rows)")
    print(df.to_string(index=False))
    return df


def main() -> None:
    cfg = SnowflakeConfig(
        database="SPGICI_WORLDOILSUPPLY",
        schema="SUPPLY",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # Object-level last altered (share views)
        run(
            cur,
            "08_fresh_info_schema_objects.csv",
            """
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE,
                   ROW_COUNT, BYTES, CREATED, LAST_ALTERED
            FROM SPGICI_WORLDOILSUPPLY.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'SUPPLY'
              AND TABLE_NAME IN ('PRODUCTION', 'PRODUCTION_ARCHIVE')
            UNION ALL
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE,
                   ROW_COUNT, BYTES, CREATED, LAST_ALTERED
            FROM SPGICI_GLOBALOILDEMAND.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'MGODF'
              AND TABLE_NAME IN ('DEMAND', 'DEMAND_ARCHIVE')
            ORDER BY 1, 3
            """,
        )

        # Column inventory: any modified / load / asof stamps?
        run(
            cur,
            "08_fresh_production_time_cols.csv",
            """
            SELECT COLUMN_NAME, DATA_TYPE
            FROM SPGICI_WORLDOILSUPPLY.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'SUPPLY' AND TABLE_NAME = 'PRODUCTION'
              AND (
                UPPER(COLUMN_NAME) ILIKE '%DATE%'
                OR UPPER(COLUMN_NAME) ILIKE '%TIME%'
                OR UPPER(COLUMN_NAME) ILIKE '%MODIF%'
                OR UPPER(COLUMN_NAME) ILIKE '%LOAD%'
                OR UPPER(COLUMN_NAME) ILIKE '%UPDATE%'
                OR UPPER(COLUMN_NAME) ILIKE '%ASOF%'
                OR UPPER(COLUMN_NAME) ILIKE '%AS_OF%'
                OR UPPER(COLUMN_NAME) ILIKE '%PUBLISH%'
                OR UPPER(COLUMN_NAME) ILIKE '%VERSION%'
              )
            ORDER BY ORDINAL_POSITION
            """,
        )
        run(
            cur,
            "08_fresh_demand_time_cols.csv",
            """
            SELECT COLUMN_NAME, DATA_TYPE
            FROM SPGICI_GLOBALOILDEMAND.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'MGODF' AND TABLE_NAME = 'DEMAND'
            ORDER BY ORDINAL_POSITION
            """,
        )

        # Short Term: latest calendar months with data (Saudi crude production)
        run(
            cur,
            "08_fresh_saudi_short_term_tail.csv",
            """
            SELECT YEAR, MONTH, COUNT(*) AS N_ROWS,
                   SUM(VALUE) AS SUM_VALUE_MBD,
                   COUNT(DISTINCT GRADE_NAME) AS N_GRADES
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            WHERE SCENARIO_TERM_NAME = 'Short Term'
              AND COUNTRY_NAME = 'Saudi Arabia'
              AND SUPPLY_TYPE_NAME = 'Crude'
              AND PRODUCTION_TYPE_NAME = 'Production'
              AND YEAR >= 2024
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
        )

        # China demand: quality flag by year-month at the frontier
        run(
            cur,
            "08_fresh_china_demand_tail.csv",
            """
            SELECT YEAR, MONTH, DATA_QUALITY_NAME, COUNT(*) AS N_PRODUCTS,
                   SUM(VALUE) AS SUM_VALUE_MBD
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            WHERE COUNTRY_NAME ILIKE '%China%'
              AND YEAR >= 2024
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            """,
        )

        # When does "actual-like" stop and Forecast dominate for China?
        run(
            cur,
            "08_fresh_china_demand_quality_by_month.csv",
            """
            SELECT YEAR, MONTH, DATA_QUALITY_NAME, COUNT(*) N
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            WHERE COUNTRY_NAME ILIKE '%China%'
              AND YEAR BETWEEN 2025 AND 2026
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            """,
        )

        # Distinct DATA_QUALITY values globally
        run(
            cur,
            "08_fresh_demand_quality_values.csv",
            """
            SELECT DATA_QUALITY_NAME, MIN(YEAR) YMIN, MAX(YEAR) YMAX, COUNT(*) N
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            GROUP BY 1 ORDER BY N DESC
            """,
        )

        # Compare archive vs live row counts / year max (are archives historical dumps?)
        run(
            cur,
            "08_fresh_archive_vs_live.csv",
            """
            SELECT 'PRODUCTION' AS OBJ, 'LIVE' AS KIND,
                   MIN(YEAR) YMIN, MAX(YEAR) YMAX, COUNT(*) N
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            UNION ALL
            SELECT 'PRODUCTION', 'ARCHIVE', MIN(YEAR), MAX(YEAR), COUNT(*)
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION_ARCHIVE
            UNION ALL
            SELECT 'DEMAND', 'LIVE', MIN(YEAR), MAX(YEAR), COUNT(*)
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            UNION ALL
            SELECT 'DEMAND', 'ARCHIVE', MIN(YEAR), MAX(YEAR), COUNT(*)
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND_ARCHIVE
            """,
        )

        # Dictionary / any publish metadata tables
        run(
            cur,
            "08_fresh_supply_dictionary.csv",
            """
            SELECT *
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.WORLDOILSUPPLY_DICTIONARY
            LIMIT 50
            """,
        )
        run(
            cur,
            "08_fresh_demand_dictionary.csv",
            """
            SELECT *
            FROM SPGICI_GLOBALOILDEMAND.MGODF.GLOBALOILDEMAND_DICTIONARY
            LIMIT 50
            """,
        )


if __name__ == "__main__":
    main()
