"""Phase 0 step 4 follow-up: curate Platts series + tighter arb/bunker/eWindow probes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desk_core.snowflake.connector import SnowflakeConfig, SnowflakeConnector

OUT = Path(__file__).resolve().parent / "_runs"
REF = "SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA"
PRICE = "SPGICI_MARKETDATA_SHARE.MDV2.PRICEDATA"
TAG = "freight-agent:discovery-platts-followup"

REF_COLS = """
    SYMBOL, DESCRIPTION, COMMODITY, VESSEL_CLASS, UOM, QUOTATION_STYLE,
    ASSESSMENT_FREQUENCY, CARGO_SIZE, CURRENCY, MDC, ORIGINATING_REGION,
    DELIVERY_REGION, SHIPPING_TERMS, ACTIVE
"""

# Description patterns aligned to ICE wet-freight map (not Baltic codes as symbols).
ROUTE_RULES: list[tuple[str, str, str]] = [
    ("TD3C analog", r"Dirty.*Arab Gulf.*China.*(270|260).*VLCC|Dirty.*Arab Gulf.*Far East.*270", "dirty"),
    ("TD15 analog", r"Dirty.*West Africa.*China.*260|Dirty.*West Africa.*Far East.*260", "dirty"),
    ("TD22 analog", r"Dirty.*(USGC|US Gulf|USG).*China.*(270|260|VLCC)", "dirty"),
    ("TD20 analog", r"Dirty.*West Africa.*(UKC|UK Continent).*130", "dirty"),
    ("TD25 analog", r"Dirty.*(USGC|US Gulf).*(ARA|UKC|UK Continent).*(70|80|Aframax)", "dirty"),
    ("TD7 analog", r"Dirty.*(North Sea|UKNS|UKC).*(Continent|UKC).*(80|Aframax)", "dirty"),
    ("TD8 analog", r"Dirty.*(Kuwait|Arab Gulf).*Singapore.*(80|130)", "dirty"),
    ("TD19 analog", r"Dirty.*Ceyhan.*(Lavera|Med).*(80|135)", "dirty"),
    ("TD6 analog", r"Dirty.*(CPC|Black Sea).*Med.*(80|135)", "dirty"),
    ("Brazil-China VLCC", r"Dirty.*Brazil.*China", "dirty"),
    ("Guyana-UKC", r"Dirty.*Guyana", "dirty"),
    ("Platts USGC-UKC (WDF)", r"Dirty.*(USGC|US Gulf).*(UKC|UK Continent|UK).*Aframax|Dirty.*(USGC|US Gulf).*UKC.*70", "dirty"),
    ("Platts PG-China (WPC)", r"Dirty.*(Persian Gulf|Arab Gulf).*China", "dirty"),
    ("Platts WAF-UKC", r"Dirty.*West Africa.*(UKC|UK Continent)", "dirty"),
    ("Cross-UKC dirty", r"Dirty.*(UKC-UKC|Cross.?UKC)", "dirty"),
    ("Vancouver-China", r"Dirty.*Vancouver.*China", "dirty"),
    ("TC2 analog", r"Clean.*(UKC|NWE|Continent).*USAC.*37|Clean.*UKC.*US Atlantic.*37", "clean"),
    ("TC14 analog", r"Clean.*(USGC|US Gulf).*Continent.*38|Clean.*(USGC|US Gulf).*UKC.*38", "clean"),
    ("TC6 analog", r"Clean.*(Skikda|Algeria).*Lavera|Clean.*Med.*Med.*30", "clean"),
    ("TC5 analog", r"Clean.*Arab Gulf.*Japan.*(55|75)", "clean"),
    ("TC7 analog", r"Clean.*Singapore.*(Australia|E Aus)", "clean"),
    ("TC12 analog", r"Clean.*(West Coast India|WCI).*Japan", "clean"),
    ("TC20 analog", r"Clean.*Arab Gulf.*(UKC|UK Continent|NWE)", "clean"),
    ("TC17 analog", r"Clean.*Arab Gulf.*East Africa", "clean"),
    ("TC18 analog", r"Clean.*(USGC|US Gulf).*Brazil", "clean"),
]


def fetch_df(cur) -> pd.DataFrame:
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def run(cur, name: str, sql: str, params: list | None = None) -> pd.DataFrame:
    cur.execute(sql, params or [])
    df = fetch_df(cur)
    df.to_csv(OUT / name, index=False)
    print(f"{name}: {len(df)} rows")
    return df


def curate_tankers() -> pd.DataFrame:
    t = pd.read_csv(OUT / "06_platts_tanker_inventory.csv")
    desc = t["DESCRIPTION"].astype(str)
    active = t["ACTIVE"].astype(str).eq("Active - Public")
    daily = t["ASSESSMENT_FREQUENCY"].astype(str).str.contains("Daily", case=False, na=False)
    not_avg = ~desc.str.contains(r"MAvg|WAvg|cargo size|Cargo Size", case=False, regex=True)
    not_carbon = ~desc.str.contains(r"Carbon|CTI |CTISE", case=False, regex=True)
    uom_ok = t["UOM"].astype(str).str.upper().isin(["WSC", "MT", "LSM"])
    core = t.loc[active & daily & not_avg & not_carbon & uom_ok].copy()

    def tag_route(d: str) -> str:
        hits = [name for name, pat, _ in ROUTE_RULES if pd.Series([d]).str.contains(pat, case=False, regex=True).iloc[0]]
        return "|".join(hits)

    core["ROUTE_TAG"] = core["DESCRIPTION"].map(tag_route)
    core["DIRTY_CLEAN"] = core["DESCRIPTION"].map(
        lambda d: "Dirty" if str(d).startswith("Dirty") else ("Clean" if str(d).startswith("Clean") else "Other")
    )
    core.to_csv(OUT / "06_platts_tanker_daily_core.csv", index=False)
    tagged = core.loc[core["ROUTE_TAG"] != ""].copy()
    tagged.to_csv(OUT / "06_platts_tanker_ice_route_map.csv", index=False)
    print("tanker_daily_core", len(core), "tagged", len(tagged))
    print(tagged.groupby("ROUTE_TAG").size().sort_values(ascending=False).head(25).to_string())
    return core


def main() -> None:
    core = curate_tankers()

    cfg = SnowflakeConfig(
        database="SPGICI_MARKETDATA_SHARE",
        schema="MDV2",
        role="JG_GENERAL",
        warehouse="EU_COMMOD_RESEARCH_XS_WH",
    )
    with SnowflakeConnector(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"ALTER SESSION SET QUERY_TAG = '{TAG}'")

        bunkers = run(
            cur,
            "06_platts_bunker_core.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE ACTIVE = 'Active - Public'
              AND ASSESSMENT_FREQUENCY ILIKE 'Daily%%'
              AND DESCRIPTION NOT ILIKE '%%MAvg%%'
              AND DESCRIPTION NOT ILIKE '%%WAvg%%'
              AND DESCRIPTION NOT ILIKE '%%Bio%%'
              AND DESCRIPTION NOT ILIKE '%%Mirror%%'
              AND (
                    DESCRIPTION ILIKE '%%VLSFO%%'
                 OR DESCRIPTION ILIKE '%%Marine Fuel 0.5%%'
                 OR DESCRIPTION ILIKE '%%HSFO%%'
                 OR DESCRIPTION ILIKE '%%380 CST%%'
                 OR DESCRIPTION ILIKE '%%MGO%%'
                 OR DESCRIPTION ILIKE '%%Marine Gasoil%%'
              )
              AND (
                    DESCRIPTION ILIKE '%%Singapore%%'
                 OR DESCRIPTION ILIKE '%%Rotterdam%%'
                 OR DESCRIPTION ILIKE '%%Fujairah%%'
                 OR DESCRIPTION ILIKE '%%Houston%%'
                 OR DESCRIPTION ILIKE '%%USGC%%'
                 OR DELIVERY_REGION ILIKE '%%Singapore%%'
                 OR DELIVERY_REGION ILIKE '%%Rotterdam%%'
                 OR DELIVERY_REGION ILIKE '%%Fujairah%%'
                 OR DELIVERY_REGION ILIKE '%%Houston%%'
                 OR DELIVERY_REGION ILIKE '%%US Gulf%%'
              )
              AND UOM IN ('MT', 'M3')
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        crude = run(
            cur,
            "06_platts_arb_crude_core.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE ACTIVE = 'Active - Public'
              AND COMMODITY = 'Crude oil'
              AND ASSESSMENT_FREQUENCY ILIKE 'Daily%%'
              AND DESCRIPTION NOT ILIKE '%%MAvg%%'
              AND DESCRIPTION NOT ILIKE '%%WAvg%%'
              AND DESCRIPTION NOT ILIKE '%%vs %%'
              AND DESCRIPTION NOT ILIKE '%%Diff%%'
              AND (
                    DESCRIPTION ILIKE 'Dated Brent%%'
                 OR DESCRIPTION ILIKE 'Dubai%%'
                 OR DESCRIPTION ILIKE 'Oman%%'
                 OR DESCRIPTION ILIKE 'Murban%%'
                 OR DESCRIPTION ILIKE 'WTI Houston%%'
                 OR DESCRIPTION ILIKE 'WTI Midland%%'
                 OR DESCRIPTION ILIKE 'Mars%%'
              )
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        products = run(
            cur,
            "06_platts_arb_products_core.csv",
            f"""
            SELECT {REF_COLS}
            FROM {REF}
            WHERE ACTIVE = 'Active - Public'
              AND ASSESSMENT_FREQUENCY ILIKE 'Daily%%'
              AND DESCRIPTION NOT ILIKE '%%MAvg%%'
              AND DESCRIPTION NOT ILIKE '%%WAvg%%'
              AND DESCRIPTION NOT ILIKE '%%Freight%%'
              AND DESCRIPTION NOT ILIKE '%%Tanker%%'
              AND DESCRIPTION NOT ILIKE '%%Swap%%'
              AND DESCRIPTION NOT ILIKE '%%Crack%%'
              AND DESCRIPTION NOT ILIKE '%%vs %%'
              AND (
                    (DESCRIPTION ILIKE '%%ULSD%%' OR DESCRIPTION ILIKE '%%Gasoil%%' OR DESCRIPTION ILIKE '%%10ppm%%')
                 OR DESCRIPTION ILIKE '%%Gasoline%%'
                 OR DESCRIPTION ILIKE '%%Naphtha%%'
              )
              AND (
                    DESCRIPTION ILIKE '%%FOB ARA%%'
                 OR DESCRIPTION ILIKE '%%CIF NWE%%'
                 OR DESCRIPTION ILIKE '%%CIF NWE Cargo%%'
                 OR DESCRIPTION ILIKE '%%FOB USGC%%'
                 OR DESCRIPTION ILIKE '%%USGC%%'
                 OR DESCRIPTION ILIKE '%%FOB Singapore%%'
                 OR DESCRIPTION ILIKE '%%FOB Arab Gulf%%'
                 OR DESCRIPTION ILIKE '%%C+F Japan%%'
              )
              AND (UOM IN ('MT', 'BBL') OR UOM IS NULL)
            ORDER BY DESCRIPTION, SYMBOL
            """,
        )

        run(
            cur,
            "06_ewindow_dictionary_freight.csv",
            """
            SELECT *
            FROM SPGICI_EWINDOW_MARKETDATA.EWMD.EWINDOW_DICTIONARY
            WHERE COALESCE(DEFINITION, '') ILIKE %s
               OR COALESCE(DESCRIPTION_EXAMPLE, '') ILIKE %s
               OR COALESCE(COLUMN_NAME, '') ILIKE %s
               OR COALESCE(DEFINITION, '') ILIKE %s
               OR COALESCE(DESCRIPTION_EXAMPLE, '') ILIKE %s
            """,
            ["%freight%", "%freight%", "%freight%", "%tanker%", "%tanker%"],
        )

        # Distinct eWindow markets — one pass, no product scan.
        run(
            cur,
            "06_ewindow_markets.csv",
            """
            SELECT MARKET, COUNT(*) AS N_ROWS
            FROM SPGICI_EWINDOW_MARKETDATA.EWMD.EWINDOW_TRADEDATA
            GROUP BY 1
            ORDER BY N_ROWS DESC
            """,
        )

        # Coverage + BATE for curated symbols
        cov_syms: list[str] = []
        for df in (core, bunkers, crude, products):
            if df is not None and not df.empty and "SYMBOL" in df.columns:
                cov_syms.extend(df["SYMBOL"].astype(str).tolist())
        # Prefer tagged tanker routes + bunkers + crude/products (cap)
        tagged = pd.read_csv(OUT / "06_platts_tanker_ice_route_map.csv")
        prefer = tagged["SYMBOL"].astype(str).tolist()
        prefer.extend(bunkers["SYMBOL"].astype(str).tolist() if not bunkers.empty else [])
        prefer.extend(crude["SYMBOL"].astype(str).tolist() if not crude.empty else [])
        prefer.extend(products["SYMBOL"].astype(str).head(80).tolist() if not products.empty else [])
        seen: set[str] = set()
        uniq: list[str] = []
        for s in prefer:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        print("followup_coverage_n", len(uniq))
        if uniq:
            values_sql = ", ".join(f"('{s.replace(chr(39), '')}')" for s in uniq)
            cov = run(
                cur,
                "06_platts_core_pricedata_coverage.csv",
                f"""
                SELECT
                  p.SYMBOL,
                  MIN(p.ASSESSDATE::date) AS FIRST_ASSESS,
                  MAX(p.ASSESSDATE::date) AS LAST_ASSESS,
                  COUNT(*) AS N_ROWS,
                  LISTAGG(DISTINCT p.BATE, ',') WITHIN GROUP (ORDER BY p.BATE) AS BATES,
                  SUM(IFF(LOWER(p.BATE) = 'c', 1, 0)) AS N_CLOSE
                FROM {PRICE} p
                WHERE p.SYMBOL IN ({values_sql})
                GROUP BY 1
                """,
            )
            print(cov.sort_values("LAST_ASSESS", ascending=False).head(12).to_string(index=False))

            # Latest close (bate c) for tagged tankers that have coverage
            tsyms = tagged["SYMBOL"].astype(str).unique().tolist()[:40]
            values_sql = ", ".join(f"('{s.replace(chr(39), '')}')" for s in tsyms)
            run(
                cur,
                "06_platts_tanker_latest_closes.csv",
                f"""
                WITH latest AS (
                  SELECT SYMBOL, MAX(ASSESSDATE) AS MAX_DT
                  FROM {PRICE}
                  WHERE SYMBOL IN ({values_sql})
                    AND LOWER(BATE) = 'c'
                  GROUP BY 1
                )
                SELECT r.SYMBOL, r.DESCRIPTION, r.VESSEL_CLASS, r.UOM,
                       p.ASSESSDATE::date AS ASSESSDATE, p.VALUE, p.BATE
                FROM {PRICE} p
                JOIN latest l ON p.SYMBOL = l.SYMBOL AND p.ASSESSDATE = l.MAX_DT AND LOWER(p.BATE) = 'c'
                JOIN {REF} r ON r.SYMBOL = p.SYMBOL
                ORDER BY r.DESCRIPTION
                """,
            )


if __name__ == "__main__":
    main()
