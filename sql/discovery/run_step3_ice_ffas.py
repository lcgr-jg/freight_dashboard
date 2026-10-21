"""Phase 0 step 3: ICE tanker FFA inventory via desk_core.

Metadata + targeted aggregates only. Writes CSVs under sql/discovery/_runs/.
ICE product-list codes from https://www.ice.com/products/Futures-Options/Freight/Wet-Freight
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
OUT.mkdir(parents=True, exist_ok=True)
TAG = "freight-agent:discovery-ice-ffas"


def fetch_df(cur) -> pd.DataFrame:
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def main() -> None:
    cfg = SnowflakeConfig(
        database="ICE",
        schema="MFT",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        # --- Product inventory: one row per LONG_NAME (tanker / wet freight) ---
        # Filter Baltic + Platts wet freight; exclude obvious dry TCA names later in pandas.
        cur.execute(
            """
            SELECT
              REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
              LONG_NAME,
              MIN(TRADE_DATE) AS FIRST_TRADE_DATE,
              MAX(TRADE_DATE) AS LAST_TRADE_DATE,
              COUNT(*) AS N_ROWS,
              COUNT(DISTINCT STRIP) AS N_STRIPS,
              COUNT(DISTINCT CONTRACT_TYPE) AS N_CONTRACT_TYPES,
              COUNT(DISTINCT RELATIVE_PERIOD) AS N_REL_PERIODS,
              MIN(SETTLEMENT_PRICE) AS MIN_SETTLE,
              MAX(SETTLEMENT_PRICE) AS MAX_SETTLE,
              AVG(SETTLEMENT_PRICE) AS AVG_SETTLE,
              SUM(ZEROIFNULL(TOTAL_VOLUME)) AS SUM_VOLUME,
              SUM(ZEROIFNULL(OPEN_INTEREST)) AS SUM_OI,
              MAX(ZEROIFNULL(TOTAL_VOLUME)) AS MAX_DAILY_VOLUME,
              MAX(ZEROIFNULL(OPEN_INTEREST)) AS MAX_OI
            FROM ICE.MFT.FUTURES
            WHERE LONG_NAME ILIKE '%FFA%'
              AND (
                    LONG_NAME ILIKE '%(Baltic)%'
                    OR LONG_NAME ILIKE '%(Platts)%'
                    OR LONG_NAME ILIKE '%Wet Freight%'
                  )
            GROUP BY 1, 2
            ORDER BY PRODUCT_CODE, N_ROWS DESC
            """
        )
        products = fetch_df(cur)
        products.to_csv(OUT / "05_ice_ffa_products.csv", index=False)
        print("ffa_products", len(products))

        dry_mask = products["LONG_NAME"].str.contains(
            r"Capesize|Panamax|Supramax|Handysize|Timecharter", case=False, regex=True
        )
        lpg_mask = products["LONG_NAME"].str.contains(r"\bLPG\b|\bBLPG", case=False, regex=True)
        lng_mask = products["LONG_NAME"].str.contains(r"\bLNG\b|Spark", case=False, regex=True)
        wet = products.loc[~(dry_mask | lpg_mask | lng_mask)].copy()
        wet.to_csv(OUT / "05_ice_wet_ffa_products.csv", index=False)
        print("wet_ffa_products", len(wet))
        print(wet[["PRODUCT_CODE", "LONG_NAME", "FIRST_TRADE_DATE", "LAST_TRADE_DATE", "N_ROWS"]].to_string(index=False))

        codes = sorted({c for c in wet["PRODUCT_CODE"].dropna().astype(str) if c})
        print("wet_codes", len(codes), codes[:40])

        # --- Grain check on a liquid monthly (TDL if present else first wet code) ---
        grain_code = "TDL" if "TDL" in codes else (codes[0] if codes else None)
        if grain_code:
            cur.execute(
                """
                SELECT TRADE_DATE, STRIP, LONG_NAME, CONTRACT_TYPE, RELATIVE_PERIOD,
                       SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST, HUB, PRODUCT, COMMODITY
                FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = %s
                  AND TRADE_DATE >= DATEADD('day', -14, CURRENT_DATE())
                ORDER BY TRADE_DATE DESC, STRIP
                LIMIT 80
                """,
                [grain_code],
            )
            grain = fetch_df(cur)
            grain.to_csv(OUT / "05_ice_grain_sample.csv", index=False)
            print("grain_sample", grain_code, len(grain))
            if len(grain):
                print(grain.head(15).to_string(index=False))

            cur.execute(
                """
                SELECT TRADE_DATE, STRIP, COUNT(*) AS n
                FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = %s
                  AND TRADE_DATE >= DATEADD('day', -5, CURRENT_DATE())
                GROUP BY 1, 2
                HAVING COUNT(*) > 1
                ORDER BY n DESC
                LIMIT 20
                """,
                [grain_code],
            )
            dups = fetch_df(cur)
            dups.to_csv(OUT / "05_ice_grain_dups.csv", index=False)
            print("dup_keys", len(dups))

        # --- Strip / tenor vocabulary for canonical monthlies ---
        canonical = [c for c in ("TDL", "WCN", "WNU", "WF2", "TDA", "WF5") if c in set(codes)]
        if canonical:
            cur.execute(
                f"""
                SELECT
                  REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') AS PRODUCT_CODE,
                  STRIP,
                  COUNT(*) AS n,
                  MIN(TRADE_DATE) AS first_dt,
                  MAX(TRADE_DATE) AS last_dt
                FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') IN ({",".join(["%s"] * len(canonical))})
                GROUP BY 1, 2
                ORDER BY 1, 3 DESC
                LIMIT 200
                """,
                canonical,
            )
            strips = fetch_df(cur)
            strips.to_csv(OUT / "05_ice_canonical_strips.csv", index=False)
            print("strips", len(strips))
            print(strips.head(40).to_string(index=False))

        # --- Sanity: TD3C around 5 Oct 2026 (primer: WS 1240.63) ---
        for code, label in (("TDL", "TD3C monthly"), ("DFN", "TD3C daily mini"), ("TDM", "TD3C balmo")):
            cur.execute(
                """
                SELECT TRADE_DATE, STRIP, SETTLEMENT_PRICE, TOTAL_VOLUME, OPEN_INTEREST, LONG_NAME
                FROM ICE.MFT.FUTURES
                WHERE REGEXP_SUBSTR(LONG_NAME, '^[A-Z0-9]+') = %s
                  AND TRADE_DATE BETWEEN '2026-10-01' AND '2026-10-08'
                ORDER BY TRADE_DATE, STRIP
                LIMIT 80
                """,
                [code],
            )
            samp = fetch_df(cur)
            samp.to_csv(OUT / f"05_ice_sanity_{code}.csv", index=False)
            print(f"sanity {label} {code}: {len(samp)} rows")
            if len(samp):
                print(samp.head(20).to_string(index=False))

        # --- Options ---
        cur.execute(
            """
            SELECT column_name
            FROM ICE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='MFT' AND table_name='OPTIONS'
            ORDER BY ordinal_position
            """
        )
        opt_cols = [r[0] for r in cur.fetchall()]
        print("options_cols", opt_cols)
        pd.Series(opt_cols, name="column_name").to_csv(OUT / "05_ice_mft_options_columns.csv", index=False)

        name_col = "LONG_NAME" if "LONG_NAME" in opt_cols else None
        if name_col is None:
            name_col = next((c for c in opt_cols if "NAME" in c.upper() or "PRODUCT" in c.upper()), None)
        if name_col:
            cur.execute(
                f"""
                SELECT
                  REGEXP_SUBSTR({name_col}, '^[A-Z0-9]+') AS PRODUCT_CODE,
                  {name_col} AS LONG_NAME,
                  MIN(TRADE_DATE) AS FIRST_TRADE_DATE,
                  MAX(TRADE_DATE) AS LAST_TRADE_DATE,
                  COUNT(*) AS N_ROWS
                FROM ICE.MFT.OPTIONS
                WHERE {name_col} ILIKE '%FFA%'
                  AND (
                        {name_col} ILIKE '%(Baltic)%'
                        OR {name_col} ILIKE '%(Platts)%'
                        OR {name_col} ILIKE '%Wet Freight%'
                        OR {name_col} ILIKE '%freight%'
                      )
                GROUP BY 1, 2
                ORDER BY N_ROWS DESC
                LIMIT 80
                """
            )
            opts = fetch_df(cur)
            opts.to_csv(OUT / "05_ice_ffa_options.csv", index=False)
            print("ffa_options", len(opts))
            if len(opts):
                print(opts.head(30).to_string(index=False))

        # --- Markers / indices: retry with product codes and route strings ---
        marker_terms = [
            "%TD3C%",
            "%TD3 %",
            "%TC14%",
            "%TC2%",
            "%DFN%",
            "%TDL%",
            "%Baltic Exchange%",
            "%BITR%",
            "%BDTI%",
            "%Worldscale%",
            "%WS %",
        ]
        for term in marker_terms:
            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM ICE.MFT.MARKERS_AND_INDICES
                WHERE PRODUCTNAME ILIKE %s OR SHORTNAME ILIKE %s
                """,
                [term, term],
            )
            n = cur.fetchone()[0]
            print(f"marker {term}: {n}")
            if n:
                cur.execute(
                    """
                    SELECT PRODUCTNAME, SHORTNAME, PRODUCTID, COUNT(*) AS n,
                           MIN(DATE) AS first_dt, MAX(DATE) AS last_dt
                    FROM ICE.MFT.MARKERS_AND_INDICES
                    WHERE PRODUCTNAME ILIKE %s OR SHORTNAME ILIKE %s
                    GROUP BY 1, 2, 3
                    ORDER BY n DESC
                    LIMIT 30
                    """,
                    [term, term],
                )
                fetch_df(cur).to_csv(
                    OUT / f"05_ice_markers_{term.strip('%').replace(' ', '_')}.csv",
                    index=False,
                )

        # Distinct PRODUCTNAME containing Freight even if earlier keyword miss
        cur.execute(
            """
            SELECT PRODUCTNAME, SHORTNAME, COUNT(*) AS n
            FROM ICE.MFT.MARKERS_AND_INDICES
            WHERE PRODUCTNAME ILIKE '%Freight%'
               OR SHORTNAME ILIKE '%Freight%'
               OR PRODUCTNAME ILIKE '%TD3%'
               OR PRODUCTNAME ILIKE '%TC14%'
            GROUP BY 1, 2
            ORDER BY n DESC
            LIMIT 50
            """
        )
        mk = fetch_df(cur)
        mk.to_csv(OUT / "05_ice_markers_freightish.csv", index=False)
        print("markers_freightish", len(mk))
        if len(mk):
            print(mk.to_string(index=False))

        # ICE.CTF.SYMBOLS is small — check for freight
        cur.execute(
            """
            SELECT column_name
            FROM ICE.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='CTF' AND table_name='SYMBOLS'
            ORDER BY ordinal_position
            """
        )
        ctf_cols = [r[0] for r in cur.fetchall()]
        print("ctf_symbol_cols", ctf_cols)
        cur.execute("SELECT * FROM ICE.CTF.SYMBOLS LIMIT 5")
        sample_ctf = fetch_df(cur)
        sample_ctf.to_csv(OUT / "05_ice_ctf_symbols_sample.csv", index=False)
        print("ctf_sample_cols", list(sample_ctf.columns))

        # Search all text-ish columns isn't cheap; try ILIKE on whole-row cast of a few
        text_cols = [c for c in ctf_cols if c.upper() not in {"TRADE_DATE"}][:15]
        hits = []
        for col in text_cols:
            try:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM ICE.CTF.SYMBOLS
                    WHERE CAST({col} AS VARCHAR) ILIKE '%TD3%'
                       OR CAST({col} AS VARCHAR) ILIKE '%freight%'
                       OR CAST({col} AS VARCHAR) ILIKE '%TC14%'
                    """
                )
                n = cur.fetchone()[0]
            except Exception as exc:  # noqa: BLE001
                print("ctf fail", col, type(exc).__name__)
                continue
            print(f"ctf {col}: {n}")
            if n:
                cur.execute(
                    f"SELECT * FROM ICE.CTF.SYMBOLS WHERE CAST({col} AS VARCHAR) ILIKE '%TD3%' OR CAST({col} AS VARCHAR) ILIKE '%freight%' LIMIT 20"
                )
                hits.append(fetch_df(cur))
        if hits:
            pd.concat(hits, ignore_index=True).to_csv(OUT / "05_ice_ctf_freight_hits.csv", index=False)

        # COMMOD convenience view columns
        cur.execute(
            """
            SELECT column_name
            FROM COMMOD.INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema='ICE_MFT' AND table_name='ICE_MFT_FUTURES'
            ORDER BY ordinal_position
            """
        )
        commod_cols = [r[0] for r in cur.fetchall()]
        print("commod_ice_mft_cols", commod_cols)
        pd.Series(commod_cols, name="column_name").to_csv(OUT / "05_commod_ice_mft_futures_columns.csv", index=False)

        cur.close()
    print("done")


if __name__ == "__main__":
    main()
