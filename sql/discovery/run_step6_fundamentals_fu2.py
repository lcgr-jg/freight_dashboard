"""Tiny follow-up: recent Saudi production + China demand samples."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"


def main() -> None:
    cfg = SnowflakeConfig(
        database="SPGICI_WORLDOILSUPPLY",
        schema="SUPPLY",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute("ALTER SESSION SET QUERY_TAG = 'freight-agent:discovery-fundamentals-fu2'")

        queries = {
            "08_supply_saudi_crude_recent.csv": """
                SELECT YEAR, MONTH, SCENARIO_TERM_NAME, VALUE, UNITS, GRADE_NAME
                FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
                WHERE YEAR BETWEEN 2023 AND 2026
                  AND COUNTRY_NAME = 'Saudi Arabia'
                  AND SUPPLY_TYPE_NAME = 'Crude'
                  AND PRODUCTION_TYPE_NAME = 'Production'
                ORDER BY YEAR, MONTH, SCENARIO_TERM_NAME
                LIMIT 80
            """,
            "08_demand_china_core_recent.csv": """
                SELECT YEAR, MONTH, PRODUCT_NAME, VALUE, UNITS, DATA_QUALITY_NAME
                FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
                WHERE COUNTRY_NAME ILIKE '%China%'
                  AND YEAR BETWEEN 2024 AND 2026
                  AND PRODUCT_NAME IN (
                    'Gasoil/Diesel',
                    'Motor Gasoline: Fin. And Blen. Comp.',
                    'Jet Fuel Kerosene',
                    'Crude Burn'
                  )
                ORDER BY YEAR DESC, MONTH DESC, PRODUCT_NAME
                LIMIT 80
            """,
            "08_supply_scenarios.csv": """
                SELECT SCENARIO_TERM_NAME, MIN(YEAR) YMIN, MAX(YEAR) YMAX, COUNT(*) N
                FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
                GROUP BY 1 ORDER BY 1
            """,
        }
        for name, sql in queries.items():
            cur.execute(sql)
            df = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
            df.to_csv(OUT / name, index=False)
            print(name, len(df))
            print(df.head(8).to_string(index=False))
            print()


if __name__ == "__main__":
    main()
