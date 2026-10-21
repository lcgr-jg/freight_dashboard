"""Phase 0 step 6: fundamentals DBs + IIR; note desk Hormuz/dark-fleet stores.

Metadata / coverage only. Writes CSVs under sql/discovery/_runs/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:discovery-fundamentals"

# Estate map (step 1) freight-relevant fundamentals
TARGETS = [
    ("SPGICI_WORLDOILSUPPLY", "SUPPLY"),
    ("SPGICI_WORLDREFINERYDATA", "WRD"),
    ("SPGICI_GLOBALOILDEMAND", "MGODF"),
    ("COMMOD", "IIR"),
    ("COMMOD", "IIR_DATA"),
]

# Name tokens that might map to export / balance / China / MEG demand context
NAME_KW = (
    "%EXPORT%",
    "%IMPORT%",
    "%BALANCE%",
    "%INVENT%",
    "%STOCK%",
    "%REFIN%",
    "%RUN%",
    "%CRUDE%",
    "%PRODUCT%",
    "%DEMAND%",
    "%SUPPLY%",
    "%SAUDI%",
    "%MEG%",
    "%GULF%",
    "%CHINA%",
    "%ASIA%",
    "%OUTAGE%",
    "%OFFLINE%",
    "%MAINT%",
)


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


def list_objects(cur, database: str, schema: str) -> pd.DataFrame:
    # Shares often expose views; SHOW TABLES alone looks sparse.
    run(
        cur,
        f"08_{database}_{schema}_tables.csv".replace(" ", "_"),
        f"SHOW TABLES IN SCHEMA {database}.{schema}",
    )
    views = run(
        cur,
        f"08_{database}_{schema}_views.csv".replace(" ", "_"),
        f"SHOW VIEWS IN SCHEMA {database}.{schema}",
    )
    # Prefer information_schema for row counts when available
    try:
        meta = run(
            cur,
            f"08_{database}_{schema}_info_tables.csv".replace(" ", "_"),
            f"""
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE,
                   ROW_COUNT, BYTES, LAST_ALTERED, COMMENT
            FROM {database}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY COALESCE(BYTES, 0) DESC NULLS LAST, TABLE_NAME
            """,
            [schema],
        )
    except Exception as exc:  # noqa: BLE001 — discovery: shares vary
        print(f"  info_schema skip {database}.{schema}: {type(exc).__name__}")
        meta = pd.DataFrame()
    return views if meta.empty else meta


def keyword_objects(cur, database: str, schema: str) -> pd.DataFrame:
    like_clause = " OR ".join(["UPPER(TABLE_NAME) LIKE %s"] * len(NAME_KW))
    params = [schema] + [k.upper() for k in NAME_KW]
    try:
        return run(
            cur,
            f"08_{database}_{schema}_kw_tables.csv".replace(" ", "_"),
            f"""
            SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT, BYTES, LAST_ALTERED
            FROM {database}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
              AND ({like_clause})
            ORDER BY COALESCE(BYTES, 0) DESC NULLS LAST
            """,
            params,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  kw skip {database}.{schema}: {type(exc).__name__}: {exc}")
        return pd.DataFrame()


def sample_columns(cur, database: str, schema: str, table: str) -> pd.DataFrame:
    safe = table.replace("/", "_")
    try:
        return run(
            cur,
            f"08_cols_{database}_{schema}_{safe}.csv",
            f"""
            SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
            FROM {database}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            [schema, table],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  cols skip {database}.{schema}.{table}: {type(exc).__name__}")
        return pd.DataFrame()


def probe_date_span(cur, fq: str, date_candidates: list[str]) -> dict:
    """Try common date column names; return first that works."""
    for col in date_candidates:
        try:
            cur.execute(
                f"""
                SELECT COUNT(*) AS N,
                       MIN({col}) AS D_MIN,
                       MAX({col}) AS D_MAX
                FROM {fq}
                """
            )
            row = fetch_df(cur).iloc[0].to_dict()
            row["DATE_COL"] = col
            row["FQ"] = fq
            row["OK"] = True
            return row
        except Exception:  # noqa: BLE001
            continue
    return {"FQ": fq, "OK": False}


def main() -> None:
    cfg = SnowflakeConfig(
        database="COMMOD",
        schema="IIR",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    summaries: list[dict] = []
    probes: list[dict] = []

    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        for database, schema in TARGETS:
            print(f"=== {database}.{schema}")
            try:
                cur.execute(f"USE DATABASE {database}")
                cur.execute(f"USE SCHEMA {schema}")
            except Exception as exc:  # noqa: BLE001
                print(f"  USE failed: {type(exc).__name__}: {exc}")
                summaries.append(
                    {
                        "DATABASE": database,
                        "SCHEMA": schema,
                        "OK": False,
                        "ERROR": f"{type(exc).__name__}",
                    }
                )
                continue

            meta = list_objects(cur, database, schema)
            kw = keyword_objects(cur, database, schema)
            summaries.append(
                {
                    "DATABASE": database,
                    "SCHEMA": schema,
                    "OK": True,
                    "N_INFO_OR_VIEWS": len(meta),
                    "N_KW_HITS": len(kw),
                    "ERROR": "",
                }
            )

            # Deep-dive: top keyword hits or largest objects
            candidates: list[str] = []
            if not kw.empty and "TABLE_NAME" in kw.columns:
                candidates = kw["TABLE_NAME"].astype(str).head(12).tolist()
            elif not meta.empty and "TABLE_NAME" in meta.columns:
                candidates = meta["TABLE_NAME"].astype(str).head(8).tolist()

            for table in candidates:
                sample_columns(cur, database, schema, table)
                fq = f"{database}.{schema}.{table}"
                # Prefer not to scan huge facts without a date filter — MIN/MAX on
                # date cols only; skip if table looks like a dimension with no date.
                probes.append(
                    probe_date_span(
                        cur,
                        fq,
                        [
                            "DATE",
                            "AS_OF_DATE",
                            "ASOF_DATE",
                            "PERIOD_DATE",
                            "MONTH",
                            "YEAR_MONTH",
                            "ASSESSMENT_DATE",
                            "EVENT_START",
                            "START_DATE",
                            "END_DATE",
                            "REPORT_DATE",
                            "SNAPSHOT_DATE",
                            "TRADE_DATE",
                            "VALUE_DATE",
                        ],
                    )
                )

        # Known desk IIR object from desk_core README
        print("=== COMMOD.IIR.OFFLINE_EVENTS probe")
        probes.append(
            probe_date_span(
                cur,
                "COMMOD.IIR.OFFLINE_EVENTS",
                ["START_DATE", "END_DATE", "EVENT_START", "DATE", "AS_OF_DATE"],
            )
        )
        sample_columns(cur, "COMMOD", "IIR", "OFFLINE_EVENTS")
        try:
            run(
                cur,
                "08_iir_offline_events_sample.csv",
                """
                SELECT *
                FROM COMMOD.IIR.OFFLINE_EVENTS
                ORDER BY 1 DESC
                LIMIT 5
                """,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  OFFLINE_EVENTS sample failed: {type(exc).__name__}: {exc}")

    pd.DataFrame(summaries).to_csv(OUT / "08_fundamentals_schema_summary.csv", index=False)
    pd.DataFrame(probes).to_csv(OUT / "08_fundamentals_date_probes.csv", index=False)
    print("wrote 08_fundamentals_schema_summary.csv / 08_fundamentals_date_probes.csv")


if __name__ == "__main__":
    main()
