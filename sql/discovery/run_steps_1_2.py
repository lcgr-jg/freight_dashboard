"""Phase 0 steps 1-2: estate map + freight keyword search via desk_core.

Read-only metadata queries. Writes CSVs under sql/discovery/_runs/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)

ROLE = "JG_GENERAL"
WH = "EU_COMMOD_RESEARCH_XS_WH"
TAG = "freight-agent:discovery-steps-1-2"

# Seed list from desk tools + freight keywords; also discover via SHOW DATABASES.
PRIORITY_DBS = [
    "ICE",
    "SPGICI_MARKETDATA_SHARE",
    "SPGICI_EWINDOW_MARKETDATA",
    "SPGICI_ENERGYPRICE_FORECAST",
    "COMMOD",
    "COMMOD_UAT",
    "TRADING",
    "TRADING_UAT",
    "BLOOMBERG",
]

TABLE_KEYWORDS = [
    "%FREIGHT%",
    "%TANKER%",
    "%BALTIC%",
    "%BITR%",
    "%WORLDSCALE%",
    "%FFA%",
    "%TD3C%",
    "%VLCC%",
    "%SUEZMAX%",
    "%AFRAMAX%",
    "%BUNKER%",
    "%VLSFO%",
    "%FIXTURE%",
    "%CHARTER%",
    "%TONNAGE%",
    "%KPLER%",
]

# Avoid bare %WS% / %ICE% — too noisy. Prefer route codes and freight terms.
COLUMN_KEYWORDS = [
    "%FREIGHT%",
    "%WORLDSCALE%",
    "%TCE%",
    "%FLAT_RATE%",
    "%FLATRATE%",
    "%BUNKER%",
    "%VLSFO%",
    "%LAYCAN%",
    "%CHARTER%",
    "%TON_MILE%",
    "%TONMILE%",
]


def connect(database: str, schema: str = "INFORMATION_SCHEMA") -> SnowflakeConnector:
    return SnowflakeConnector(
        SnowflakeConfig(database=database, schema=schema, role=ROLE, warehouse=WH)
    )


def fetch_df(cur) -> pd.DataFrame:
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def main() -> None:
    # Use a known share DB as session anchor
    with connect("SPGICI_MARKETDATA_SHARE", "MDV2") as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")
        cur.execute("SHOW DATABASES")
        dbs = fetch_df(cur)
        dbs.to_csv(OUT / "00_databases.csv", index=False)
        name_col = "name" if "name" in dbs.columns else dbs.columns[1]
        available = set(dbs[name_col].astype(str).str.upper())
        print(f"databases_accessible={len(available)}")
        for n in sorted(available):
            print(f"  DB {n}")

        schema_rows: list[dict] = []
        table_hits: list[dict] = []
        column_hits: list[dict] = []
        access_errors: list[dict] = []

        # Prefer full estate; fall back to priority list if SHOW is huge
        targets = sorted(available)
        # Always include priority names even if SHOW naming differs
        for p in PRIORITY_DBS:
            if p.upper() not in available:
                # still try — SHOW may omit some shares depending on role
                targets.append(p)

        seen = set()
        for db in targets:
            db_u = db.upper()
            if db_u in seen:
                continue
            seen.add(db_u)

            try:
                cur.execute(f"SHOW SCHEMAS IN DATABASE {db_u}")
                schemas = fetch_df(cur)
                s_name = "name" if "name" in schemas.columns else schemas.columns[1]
                schema_names = [
                    s for s in schemas[s_name].astype(str).tolist() if s.upper() != "INFORMATION_SCHEMA"
                ]
                for s in schema_names:
                    schema_rows.append({"database": db_u, "schema": s})
                print(f"schemas {db_u}: {len(schema_names)}")
            except Exception as exc:  # noqa: BLE001 - discovery must continue
                access_errors.append({"database": db_u, "step": "show_schemas", "error": str(exc)[:300]})
                print(f"FAIL schemas {db_u}: {type(exc).__name__}")
                continue

            # Table inventory (metadata only)
            try:
                cur.execute(
                    f"""
                    SELECT table_catalog, table_schema, table_name, table_type,
                           row_count, bytes, last_altered, comment
                    FROM {db_u}.INFORMATION_SCHEMA.TABLES
                    WHERE table_schema != 'INFORMATION_SCHEMA'
                    ORDER BY table_schema, table_name
                    """
                )
                tables = fetch_df(cur)
                tables.to_csv(OUT / f"01_tables_{db_u}.csv", index=False)
                print(f"tables {db_u}: {len(tables)}")
            except Exception as exc:  # noqa: BLE001
                access_errors.append({"database": db_u, "step": "list_tables", "error": str(exc)[:300]})
                print(f"FAIL tables {db_u}: {type(exc).__name__}")
                continue

            # Keyword filter on names/comments
            try:
                like_table = " OR ".join(["table_name ILIKE %s"] * len(TABLE_KEYWORDS))
                like_comment = " OR ".join(["IFNULL(comment,'') ILIKE %s"] * len(TABLE_KEYWORDS))
                cur.execute(
                    f"""
                    SELECT table_catalog, table_schema, table_name, table_type,
                           row_count, bytes, last_altered, comment
                    FROM {db_u}.INFORMATION_SCHEMA.TABLES
                    WHERE table_schema != 'INFORMATION_SCHEMA'
                      AND (({like_table}) OR ({like_comment}))
                    ORDER BY table_schema, table_name
                    """,
                    TABLE_KEYWORDS + TABLE_KEYWORDS,
                )
                th = fetch_df(cur)
                for rec in th.to_dict(orient="records"):
                    table_hits.append(rec)
                print(f"table_keyword_hits {db_u}: {len(th)}")
            except Exception as exc:  # noqa: BLE001
                access_errors.append({"database": db_u, "step": "table_keywords", "error": str(exc)[:300]})
                print(f"FAIL table keywords {db_u}: {type(exc).__name__}")

            try:
                like_col = " OR ".join(["column_name ILIKE %s"] * len(COLUMN_KEYWORDS))
                cur.execute(
                    f"""
                    SELECT table_catalog, table_schema, table_name, column_name, data_type, comment
                    FROM {db_u}.INFORMATION_SCHEMA.COLUMNS
                    WHERE table_schema != 'INFORMATION_SCHEMA'
                      AND ({like_col})
                    ORDER BY table_schema, table_name, ordinal_position
                    LIMIT 500
                    """,
                    COLUMN_KEYWORDS,
                )
                ch = fetch_df(cur)
                for rec in ch.to_dict(orient="records"):
                    column_hits.append(rec)
                print(f"column_keyword_hits {db_u}: {len(ch)}")
            except Exception as exc:  # noqa: BLE001
                access_errors.append({"database": db_u, "step": "column_keywords", "error": str(exc)[:300]})
                print(f"FAIL column keywords {db_u}: {type(exc).__name__}")

        pd.DataFrame(schema_rows).to_csv(OUT / "01_schemas.csv", index=False)
        pd.DataFrame(table_hits).to_csv(OUT / "02_table_keyword_hits.csv", index=False)
        pd.DataFrame(column_hits).to_csv(OUT / "02_column_keyword_hits.csv", index=False)
        pd.DataFrame(access_errors).to_csv(OUT / "00_access_errors.csv", index=False)
        print(f"done schemas={len(schema_rows)} table_hits={len(table_hits)} col_hits={len(column_hits)} errors={len(access_errors)}")
        cur.close()


if __name__ == "__main__":
    main()
