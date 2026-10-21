"""Step 6 follow-up: year spans, MEG/China slices, RUNS/OUTAGES grains."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
TAG = "freight-agent:discovery-fundamentals-fu"


def fetch_df(cur) -> pd.DataFrame:
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


def run(cur, name: str, sql: str) -> pd.DataFrame:
    cur.execute(sql)
    df = fetch_df(cur)
    df.to_csv(OUT / name, index=False)
    print(f"{name}: {len(df)} rows")
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

        run(
            cur,
            "08_supply_production_profile.csv",
            """
            SELECT
              MIN(YEAR) AS YEAR_MIN, MAX(YEAR) AS YEAR_MAX,
              COUNT(*) AS N_ROWS,
              COUNT(DISTINCT COUNTRY_NAME) AS N_COUNTRIES,
              COUNT(DISTINCT SCENARIO_TERM_NAME) AS N_SCENARIOS,
              COUNT(DISTINCT UNITS) AS N_UNITS
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            """,
        )
        run(
            cur,
            "08_supply_production_units.csv",
            """
            SELECT UNITS, COUNT(*) AS N
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            GROUP BY 1 ORDER BY N DESC LIMIT 20
            """,
        )
        run(
            cur,
            "08_supply_production_meg_china.csv",
            """
            SELECT YEAR, MONTH, COUNTRY_NAME, REGION_NAME,
                   SUPPLY_TYPE_NAME, PRODUCTION_TYPE_NAME, GRADE_NAME,
                   UNITS, VALUE, SCENARIO_TERM_NAME
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            WHERE YEAR >= 2024
              AND (
                COUNTRY_NAME ILIKE '%Saudi%'
                OR COUNTRY_NAME ILIKE '%United Arab%'
                OR COUNTRY_NAME ILIKE '%Iraq%'
                OR COUNTRY_NAME ILIKE '%Kuwait%'
                OR COUNTRY_NAME ILIKE '%Iran%'
                OR COUNTRY_NAME ILIKE '%China%'
                OR REGION_NAME ILIKE '%Middle East%'
              )
            ORDER BY YEAR DESC, MONTH DESC, COUNTRY_NAME
            LIMIT 200
            """,
        )
        run(
            cur,
            "08_supply_production_countries.csv",
            """
            SELECT COUNTRY_NAME, REGION_NAME, COUNT(*) AS N,
                   MIN(YEAR) AS YMIN, MAX(YEAR) AS YMAX
            FROM SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION
            GROUP BY 1, 2
            HAVING COUNTRY_NAME ILIKE '%Saudi%'
                OR COUNTRY_NAME ILIKE '%China%'
                OR COUNTRY_NAME ILIKE '%United Arab%'
                OR COUNTRY_NAME ILIKE '%Iraq%'
                OR COUNTRY_NAME ILIKE '%Kuwait%'
                OR COUNTRY_NAME ILIKE '%Iran%'
                OR COUNTRY_NAME ILIKE '%Brazil%'
                OR COUNTRY_NAME ILIKE '%United States%'
            ORDER BY N DESC
            """,
        )

        run(
            cur,
            "08_wrd_runs_profile.csv",
            """
            SELECT MIN(YEAR) AS YEAR_MIN, MAX(YEAR) AS YEAR_MAX,
                   COUNT(*) AS N_ROWS,
                   COUNT(DISTINCT REFINERY_NAME) AS N_REFINERIES,
                   COUNT(DISTINCT PROCESS_UNIT_NAME) AS N_UNITS
            FROM SPGICI_WORLDREFINERYDATA.WRD.RUNS
            """,
        )
        run(
            cur,
            "08_wrd_runs_china_sample.csv",
            """
            SELECT YEAR, QUARTER, REFINERY_NAME, OWNER_NAME,
                   PROCESS_UNIT_NAME, CAPACITY_STATUS_NAME,
                   MBCD, MBSD, MODIFIED_DATE
            FROM SPGICI_WORLDREFINERYDATA.WRD.RUNS
            WHERE YEAR >= 2024
              AND (REFINERY_NAME ILIKE '%China%'
                   OR OWNER_NAME ILIKE '%Sinopec%'
                   OR OWNER_NAME ILIKE '%PetroChina%'
                   OR OWNER_NAME ILIKE '%CNPC%'
                   OR REFINERY_NAME ILIKE '%Zhenhai%'
                   OR REFINERY_NAME ILIKE '%Ningbo%')
            ORDER BY YEAR DESC, QUARTER DESC
            LIMIT 100
            """,
        )
        # Refinery master: country if present
        run(
            cur,
            "08_wrd_refineries_cols_check.csv",
            """
            SELECT *
            FROM SPGICI_WORLDREFINERYDATA.WRD.REF_DATA_REFINERIES
            LIMIT 3
            """,
        )
        run(
            cur,
            "08_wrd_outages_profile.csv",
            """
            SELECT MIN(DATE) AS D_MIN, MAX(DATE) AS D_MAX, COUNT(*) AS N
            FROM SPGICI_WORLDREFINERYDATA.WRD.OUTAGES
            """,
        )
        run(
            cur,
            "08_wrd_outages_sample.csv",
            """
            SELECT *
            FROM SPGICI_WORLDREFINERYDATA.WRD.OUTAGES
            WHERE DATE >= '2025-01-01'
            ORDER BY DATE DESC
            LIMIT 20
            """,
        )

        run(
            cur,
            "08_demand_profile.csv",
            """
            SELECT MIN(YEAR) AS YEAR_MIN, MAX(YEAR) AS YEAR_MAX,
                   COUNT(*) AS N_ROWS,
                   COUNT(DISTINCT COUNTRY_NAME) AS N_COUNTRIES,
                   COUNT(DISTINCT PRODUCT_NAME) AS N_PRODUCTS,
                   COUNT(DISTINCT UNITS) AS N_UNITS
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            """,
        )
        run(
            cur,
            "08_demand_china_products.csv",
            """
            SELECT YEAR, MONTH, PRODUCT_NAME, UNITS, VALUE, SCENARIO_ID, DATA_QUALITY_NAME
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            WHERE COUNTRY_NAME ILIKE '%China%'
              AND YEAR >= 2023
            ORDER BY YEAR DESC, MONTH DESC, PRODUCT_NAME
            LIMIT 150
            """,
        )
        run(
            cur,
            "08_demand_product_list.csv",
            """
            SELECT PRODUCT_NAME, COUNT(*) AS N
            FROM SPGICI_GLOBALOILDEMAND.MGODF.DEMAND
            GROUP BY 1 ORDER BY N DESC LIMIT 40
            """,
        )

        # IIR petroleum outages — China / MEG countries (freight demand context)
        run(
            cur,
            "08_iir_petchem_country_counts.csv",
            """
            SELECT COUNTRY, COUNT(*) AS N_EVENTS,
                   MIN(START_DATE) AS D_MIN, MAX(START_DATE) AS D_MAX,
                   COUNT(DISTINCT PLANT_NAME) AS N_PLANTS
            FROM COMMOD.IIR.OFFLINE_EVENTS
            WHERE IND_DESC ILIKE '%Petroleum%'
               OR IND_DESC ILIKE '%Refin%'
               OR FUEL_GROUP ILIKE '%Oil%'
            GROUP BY 1
            HAVING COUNTRY ILIKE '%China%'
                OR COUNTRY ILIKE '%Saudi%'
                OR COUNTRY ILIKE '%United Arab%'
                OR COUNTRY ILIKE '%Iraq%'
                OR COUNTRY ILIKE '%Kuwait%'
                OR COUNTRY ILIKE '%India%'
                OR COUNTRY ILIKE '%Korea%'
                OR COUNTRY ILIKE '%Japan%'
                OR COUNTRY ILIKE '%U.S.A%'
                OR COUNTRY ILIKE '%United States%'
            ORDER BY N_EVENTS DESC
            """,
        )
        run(
            cur,
            "08_iir_china_recent.csv",
            """
            SELECT START_DATE, END_DATE, PLANT_NAME, UNIT_NAME, COUNTRY,
                   EVENT_TYPE, E_STATUS_RESEARCH, CAP_OFFLINE, CAP_UOM, IND_DESC
            FROM COMMOD.IIR.OFFLINE_EVENTS
            WHERE COUNTRY ILIKE '%China%'
              AND START_DATE >= '2025-01-01'
              AND (IND_DESC ILIKE '%Petroleum%' OR IND_DESC ILIKE '%Refin%')
            ORDER BY START_DATE DESC
            LIMIT 40
            """,
        )


if __name__ == "__main__":
    main()
