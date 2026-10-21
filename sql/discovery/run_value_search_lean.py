"""Lean Phase 0 step-2 value probes (avoid full-table OR-ILIKE storms)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:discovery-value-lean"

# One pattern at a time on the most useful columns only
PLATTS_TERMS = [
    "%freight%",
    "%worldscale%",
    "%baltic%",
    "%vlcc%",
    "%suezmax%",
    "%aframax%",
    "%tanker%",
    "%bunker%",
    "%vlsfo%",
    "%td3c%",
    "%tc14%",
    "%tc2%",
]

ICE_TERMS = PLATTS_TERMS + ["%ffa%", "%bitr%"]
BBG_TERMS = ["%freight%", "%baltic%", "%td3%", "%tc14%", "%vlcc%", "%worldscale%", "%tanker%"]


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
    counts: list[dict] = []

    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # 1) Platts REF columns + dictionary sample of commodity/sector paths
        cur.execute(
            """
            SELECT column_name
            FROM SPGICI_MARKETDATA_SHARE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='MDV2' AND table_name='REF_DATA_MARKETDATA'
            ORDER BY ordinal_position
            """
        )
        ref_cols = [r[0] for r in cur.fetchall()]
        pd.Series(ref_cols, name="column_name").to_csv(OUT / "03_platts_ref_columns.csv", index=False)
        print("platts_ref_cols", len(ref_cols))
        print(ref_cols)

        # Prefer dictionary if present (usually smaller / clearer)
        for table in ("MARKETDATA_DICTIONARY", "REF_DATA_MARKETDATA"):
            cur.execute(
                f"""
                SELECT column_name
                FROM SPGICI_MARKETDATA_SHARE.INFORMATION_SCHEMA.COLUMNS
                WHERE table_schema='MDV2' AND table_name=%s
                ORDER BY ordinal_position
                """,
                [table],
            )
            cols = [r[0] for r in cur.fetchall()]
            print(f"{table} cols", cols[:30])

        # Probe DESCRIPTION-like fields one term at a time
        # Common Platts fields from desk usage: DESCRIPTION, COMMODITY, MARKET, HUB, PRODUCT, BENCHMARK
        candidate_cols = [
            c
            for c in ref_cols
            if c.upper()
            in {
                "DESCRIPTION",
                "COMMODITY",
                "MARKET",
                "HUB",
                "PRODUCT",
                "BENCHMARK",
                "ASSESSMENT_NAME",
                "SYMBOL",
                "SECTOR",
                "PATH",
                "HIERARCHY",
                "SHORT_NAME",
                "LONG_NAME",
            }
        ]
        if not candidate_cols:
            candidate_cols = [c for c in ref_cols if "DESC" in c.upper() or c.upper() == "SYMBOL"][:5]
        print("probe_cols", candidate_cols)

        for col in candidate_cols:
            for term in PLATTS_TERMS:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
                    WHERE {col} ILIKE %s
                    """,
                    [term],
                )
                n = cur.fetchone()[0]
                counts.append({"source": "MDV2.REF_DATA_MARKETDATA", "column": col, "term": term, "n": n})
                print(f"platts {col} {term}: {n}")
                if n:
                    cur.execute(
                        f"""
                        SELECT SYMBOL, {col} AS matched_value
                        FROM SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA
                        WHERE {col} ILIKE %s
                        LIMIT 30
                        """,
                        [term],
                    )
                    fetch_df(cur).to_csv(
                        OUT / f"03_platts_sample_{col}_{term.strip('%')}.csv",
                        index=False,
                    )

        # 2) ICE MFT FUTURES / MARKERS — columns then targeted probes
        cur.execute(
            """
            SELECT column_name
            FROM ICE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='MFT' AND table_name='FUTURES'
            ORDER BY ordinal_position
            """
        )
        ice_cols = [r[0] for r in cur.fetchall()]
        pd.Series(ice_cols, name="column_name").to_csv(OUT / "03_ice_mft_futures_columns.csv", index=False)
        print("ice_cols", ice_cols)

        ice_probe = [
            c
            for c in ice_cols
            if any(
                x in c.upper()
                for x in ("PRODUCT", "CONTRACT", "SYMBOL", "NAME", "DESC", "MARKET", "COMMODITY", "HUB")
            )
        ][:8]
        print("ice_probe", ice_probe)

        for col in ice_probe:
            for term in ["%freight%", "%baltic%", "%td3%", "%tanker%", "%vlcc%", "%worldscale%"]:
                try:
                    cur.execute(
                        f"""
                        SELECT COUNT(*) AS n
                        FROM ICE.MFT.FUTURES
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        """,
                        [term],
                    )
                    n = cur.fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    print(f"ice fail {col} {term}: {type(exc).__name__}")
                    continue
                counts.append({"source": "ICE.MFT.FUTURES", "column": col, "term": term, "n": n})
                print(f"ice {col} {term}: {n}")
                if n:
                    cur.execute(
                        f"""
                        SELECT CAST({col} AS VARCHAR) AS matched_value, COUNT(*) AS n
                        FROM ICE.MFT.FUTURES
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        GROUP BY 1
                        ORDER BY 2 DESC
                        LIMIT 40
                        """,
                        [term],
                    )
                    fetch_df(cur).to_csv(
                        OUT / f"03_ice_sample_{col}_{term.strip('%')}.csv",
                        index=False,
                    )

        # Also try MARKERS_AND_INDICES for Baltic spot
        cur.execute(
            """
            SELECT column_name
            FROM ICE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='MFT' AND table_name='MARKERS_AND_INDICES'
            ORDER BY ordinal_position
            """
        )
        marker_cols = [r[0] for r in cur.fetchall()]
        print("marker_cols", marker_cols)
        m_probe = [
            c
            for c in marker_cols
            if any(x in c.upper() for x in ("PRODUCT", "CONTRACT", "SYMBOL", "NAME", "DESC", "MARKET"))
        ][:6]
        for col in m_probe:
            for term in ["%freight%", "%baltic%", "%td3%", "%tanker%"]:
                try:
                    cur.execute(
                        f"""
                        SELECT COUNT(*) AS n
                        FROM ICE.MFT.MARKERS_AND_INDICES
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        """,
                        [term],
                    )
                    n = cur.fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    print(f"marker fail {col}: {type(exc).__name__}")
                    continue
                counts.append({"source": "ICE.MFT.MARKERS_AND_INDICES", "column": col, "term": term, "n": n})
                print(f"marker {col} {term}: {n}")
                if n:
                    cur.execute(
                        f"""
                        SELECT CAST({col} AS VARCHAR) AS matched_value, COUNT(*) AS n
                        FROM ICE.MFT.MARKERS_AND_INDICES
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        GROUP BY 1 ORDER BY 2 DESC LIMIT 40
                        """,
                        [term],
                    )
                    fetch_df(cur).to_csv(
                        OUT / f"03_ice_marker_{col}_{term.strip('%')}.csv",
                        index=False,
                    )

        # 3) Bloomberg FUTURE_REF
        cur.execute(
            """
            SELECT column_name
            FROM BLOOMBERG.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='BBGH_FUTURES' AND table_name='FUTURE_REF'
            ORDER BY ordinal_position
            """
        )
        bbg_cols = [r[0] for r in cur.fetchall()]
        pd.Series(bbg_cols, name="column_name").to_csv(OUT / "03_bbg_future_ref_columns.csv", index=False)
        bbg_probe = [
            c
            for c in bbg_cols
            if any(x in c.upper() for x in ("DESC", "NAME", "TICKER", "SECURITY", "PRODUCT", "CATEGORY"))
        ]
        print("bbg_probe", bbg_probe)
        for col in bbg_probe:
            for term in BBG_TERMS:
                try:
                    cur.execute(
                        f"""
                        SELECT COUNT(*) AS n
                        FROM BLOOMBERG.BBGH_FUTURES.FUTURE_REF
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        """,
                        [term],
                    )
                    n = cur.fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    print(f"bbg fail {col}: {type(exc).__name__}")
                    continue
                counts.append({"source": "BLOOMBERG.FUTURE_REF", "column": col, "term": term, "n": n})
                print(f"bbg {col} {term}: {n}")
                if n:
                    cur.execute(
                        f"""
                        SELECT CAST({col} AS VARCHAR) AS matched_value, COUNT(*) AS n
                        FROM BLOOMBERG.BBGH_FUTURES.FUTURE_REF
                        WHERE CAST({col} AS VARCHAR) ILIKE %s
                        GROUP BY 1 ORDER BY 2 DESC LIMIT 40
                        """,
                        [term],
                    )
                    fetch_df(cur).to_csv(
                        OUT / f"03_bbg_sample_{col}_{term.strip('%')}.csv",
                        index=False,
                    )

        # 4) BBG DL+ MiFID freight fields
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
            fetch_df(cur).to_csv(OUT / "03_bbg_dlplus_freight_routes.csv", index=False)
            print("bbg_dlplus_ok")
        except Exception as exc:  # noqa: BLE001
            print("bbg_dlplus", type(exc).__name__, str(exc)[:200])

        pd.DataFrame(counts).to_csv(OUT / "03_value_search_counts.csv", index=False)
        cur.close()
    print("done")


if __name__ == "__main__":
    main()
