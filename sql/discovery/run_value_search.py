"""Phase 0 step 2 value search on known instrument/ref masters."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:discovery-value-search"

# Keep patterns specific; avoid bare WS
PATTERNS = [
    "%TD3C%",
    "%TD15%",
    "%TD22%",
    "%TD20%",
    "%TD25%",
    "%TD6%",
    "%TC14%",
    "%TC2%",
    "%TC7%",
    "%TC12%",
    "%BALTIC%",
    "%WORLDSCALE%",
    "%VLCC%",
    "%SUEZMAX%",
    "%AFRAMAX%",
    "%TANKER%",
    "%FREIGHT%",
    "%BITR%",
    "%BUNKER%",
    "%VLSFO%",
    "%FLAT RATE%",
    "%FLATRATE%",
]


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
    results: list[dict] = []
    samples: list[dict] = []

    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # --- Platts REF_DATA columns ---
        cur.execute(
            """
            SELECT column_name, data_type
            FROM SPGICI_MARKETDATA_SHARE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema = 'MDV2' AND table_name = 'REF_DATA_MARKETDATA'
            ORDER BY ordinal_position
            """
        )
        platts_cols = fetch_df(cur)
        platts_cols.to_csv(OUT / "03_platts_ref_columns.csv", index=False)
        print("platts_ref_columns", len(platts_cols))

        text_cols = [
            c
            for c in platts_cols["COLUMN_NAME"].tolist()
            if any(x in c.upper() for x in ("DESC", "NAME", "PRODUCT", "MARKET", "HUB", "COMMODITY", "SYMBOL", "ASSESSMENT", "PATH", "SECTOR", "BENCH"))
        ]
        # Always include SYMBOL
        if "SYMBOL" not in text_cols:
            text_cols.insert(0, "SYMBOL")
        print("platts_text_cols", text_cols)

        # Search each text column for freight patterns (count only)
        for col in text_cols:
            like = " OR ".join([f"{col} ILIKE %s"] * len(PATTERNS))
            sql = f"""
                SELECT COUNT(*) AS n
                FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
                WHERE {like}
            """
            cur.execute(sql, PATTERNS)
            n = cur.fetchone()[0]
            results.append({"source": "PLATTS_REF_DATA_MARKETDATA", "column": col, "match_count": n})
            print(f"platts {col}: {n}")
            if n and n > 0:
                cur.execute(
                    f"""
                    SELECT SYMBOL, {col} AS matched_col, COUNT(*) AS n
                    FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
                    WHERE {like}
                    GROUP BY 1, 2
                    ORDER BY 2
                    LIMIT 200
                    """,
                    PATTERNS,
                )
                df = fetch_df(cur)
                df.insert(0, "source_column", col)
                samples.append(df)

        # --- ICE MFT FUTURES description columns ---
        cur.execute(
            """
            SELECT column_name, data_type
            FROM ICE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema = 'MFT' AND table_name = 'FUTURES'
            ORDER BY ordinal_position
            """
        )
        ice_cols = fetch_df(cur)
        ice_cols.to_csv(OUT / "03_ice_mft_futures_columns.csv", index=False)
        print("ice_futures_columns", len(ice_cols))
        ice_text = [
            c
            for c in ice_cols["COLUMN_NAME"].tolist()
            if any(x in c.upper() for x in ("DESC", "NAME", "PRODUCT", "SYMBOL", "CONTRACT", "MARKET", "COMMODITY", "HUB", "STRIP", "UNDERLY"))
        ]
        print("ice_text_cols", ice_text[:40])

        for col in ice_text[:25]:
            like = " OR ".join([f"CAST({col} AS VARCHAR) ILIKE %s"] * len(PATTERNS))
            try:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM ICE.MFT.FUTURES
                    WHERE {like}
                    """,
                    PATTERNS,
                )
                n = cur.fetchone()[0]
            except Exception as exc:  # noqa: BLE001
                print(f"ice fail {col}: {type(exc).__name__}")
                continue
            results.append({"source": "ICE.MFT.FUTURES", "column": col, "match_count": n})
            print(f"ice {col}: {n}")
            if n:
                cur.execute(
                    f"""
                    SELECT {col} AS matched_col, COUNT(*) AS n
                    FROM ICE.MFT.FUTURES
                    WHERE {like}
                    GROUP BY 1
                    ORDER BY 2 DESC
                    LIMIT 100
                    """,
                    PATTERNS,
                )
                df = fetch_df(cur)
                df.insert(0, "source_column", col)
                samples.append(df)

        # --- Bloomberg FUTURE_REF ---
        cur.execute(
            """
            SELECT column_name, data_type
            FROM BLOOMBERG.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema = 'BBGH_FUTURES' AND table_name = 'FUTURE_REF'
            ORDER BY ordinal_position
            """
        )
        bbg_cols = fetch_df(cur)
        bbg_cols.to_csv(OUT / "03_bbg_future_ref_columns.csv", index=False)
        bbg_text = [
            c
            for c in bbg_cols["COLUMN_NAME"].tolist()
            if any(x in c.upper() for x in ("DESC", "NAME", "TICKER", "SECURITY", "PRODUCT", "COMMODITY", "CATEGORY"))
        ]
        print("bbg_text_cols", bbg_text)
        for col in bbg_text:
            like = " OR ".join([f"CAST({col} AS VARCHAR) ILIKE %s"] * len(PATTERNS))
            try:
                cur.execute(
                    f"SELECT COUNT(*) AS n FROM BLOOMBERG.BBGH_FUTURES.FUTURE_REF WHERE {like}",
                    PATTERNS,
                )
                n = cur.fetchone()[0]
            except Exception as exc:  # noqa: BLE001
                print(f"bbg fail {col}: {type(exc).__name__}")
                continue
            results.append({"source": "BLOOMBERG.BBGH_FUTURES.FUTURE_REF", "column": col, "match_count": n})
            print(f"bbg {col}: {n}")
            if n:
                cur.execute(
                    f"""
                    SELECT {col} AS matched_col, COUNT(*) AS n
                    FROM BLOOMBERG.BBGH_FUTURES.FUTURE_REF
                    WHERE {like}
                    GROUP BY 1 ORDER BY 2 DESC LIMIT 100
                    """,
                    PATTERNS,
                )
                df = fetch_df(cur)
                df.insert(0, "source_column", col)
                samples.append(df)

        # BBG_DLPLUS freight MiFID fields — sample non-null
        try:
            cur.execute(
                """
                SELECT MIFID_FREIGHT_ROUTE, MIFID_FREIGHT_SUB_TYPE_SIZE, COUNT(*) AS n
                FROM BBG_DLPLUS.CORE.INSTRUMENT
                WHERE MIFID_FREIGHT_ROUTE IS NOT NULL
                GROUP BY 1, 2
                ORDER BY 3 DESC
                LIMIT 100
                """
            )
            df = fetch_df(cur)
            df.to_csv(OUT / "03_bbg_dlplus_freight_routes.csv", index=False)
            print("bbg_dlplus_freight_routes", len(df))
        except Exception as exc:  # noqa: BLE001
            print("bbg_dlplus fail", type(exc).__name__, str(exc)[:200])

        # SECURITY_MASTER quick name search if tables look promising
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM SECURITY_MASTER.INFORMATION_SCHEMA.TABLES
            WHERE table_schema != 'INFORMATION_SCHEMA'
              AND (table_name ILIKE '%INSTRUMENT%' OR table_name ILIKE '%SECURITY%' OR table_name ILIKE '%PRODUCT%')
            ORDER BY 1, 2
            LIMIT 40
            """
        )
        sm = fetch_df(cur)
        sm.to_csv(OUT / "03_security_master_candidates.csv", index=False)
        print("security_master_candidates", len(sm))

        pd.DataFrame(results).to_csv(OUT / "03_value_search_counts.csv", index=False)
        if samples:
            pd.concat(samples, ignore_index=True).to_csv(OUT / "03_value_search_samples.csv", index=False)
        cur.close()
    print("done")


if __name__ == "__main__":
    main()
