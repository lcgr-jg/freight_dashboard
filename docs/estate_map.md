# Snowflake estate map (Phase 0 step 1)

Access method: `desk_core` with role `JG_GENERAL`, warehouse `EU_COMMOD_RESEARCH_XS_WH`.
Session tag: `freight-agent:discovery-steps-1-2`.
Verified: 2026-10-05. Raw outputs under `sql/discovery/_runs/`.

**48 databases** visible. Below: freight-relevant grouping. Full schema list: `_runs/01_schemas.csv`.

## Exchange / paper

| Database | Schemas (n) | One-line description | Freight relevance |
|---|---|---|---|
| **ICE** | 6 | ICE futures/options (MFT, flash, CTF, CME, integration/stage) | **High** — wet freight FFAs present in `MFT.FUTURES` (`LONG_NAME`) |
| **EEX** | 4 | Power derivatives / spot | Low for tanker FFAs (power) |
| **ASX** | 5 | ASX market data | Unlikely tanker freight |
| **COMMOD** | 5 | Internal ICE_MFT views, IIR, Bloomberg snaps, PRICES_* | Medium — convenient ICE views; not Baltic primary |

## Platts / S&P Global

| Database | Schemas (n) | One-line description | Freight relevance |
|---|---|---|---|
| **SPGICI_MARKETDATA_SHARE** | 2 (`MDV2`, `FC`) | Spot assessments + forward curves | **High** — tanker/bunker assessments in `REF_DATA` / `PRICEDATA` |
| **SPGICI_EWINDOW_MARKETDATA** | 1 (`EWMD`) | Platts eWindow orders/trades | Bunker markets only (no tanker FFA `MARKET`); see step 4 |
| **SPGICI_ARBFLOW** | 1 | Arb / margin calculators | Medium — `PREFERRED_FREIGHT` on margins catalog |
| **SPGICI_ENERGYPRICE_FORECAST** | 1 | Energy price forecasts | Low–medium (scenarios) |
| **SPGICI_WORLDOILSUPPLY** | 1 (`SUPPLY`) | World oil **production** MBD (not exports) | Medium — MEG crude Short Term; step 6 |
| **SPGICI_WORLDREFINERYDATA** | 1 (`WRD`) | Refinery runs (→2024) + outages | Medium — China runs/outages; step 6 |
| **SPGICI_GLOBALOILDEMAND** | 1 (`MGODF`) | Product demand MBD by country | Medium — China demand regime; step 6 |
| **COMMOD.IIR** | — | IIR offline/outage events | Medium — live plant outages; step 6 |
| **SPGICI_GLOBALLNGANALYTICS\*** | 1 each | LNG analytics | Low for tanker oil freight (LNG charter rates exist) |
| Other `SPGICI_*` | varies | Chemicals, EU gas, LNG+, crude risk, NA gas pipelines, Xpress | Mostly out of scope |

## Kpler

| Database | Schemas (n) | One-line description | Freight relevance |
|---|---|---|---|
| **KPLER** | 2 (`KPLER_POWER`, `ONGOING`) | **Power** load/generation/availability only | **None for liquids freight** — liquids/fleet/fixtures via API, not this DB |

## Bloomberg / security master

| Database | Schemas (n) | One-line description | Freight relevance |
|---|---|---|---|
| **BLOOMBERG** | 3 | Futures ref/px, on-demand snaps | TBD — ticker search on `FUTURE_REF` found no TD3/TC14 strings in ticker fields |
| **BBG_DLPLUS** | 9 | Broad instrument master | Low so far — `MIFID_FREIGHT_ROUTE` columns exist but sample of non-null routes was empty |
| **BBG_BULK** | 2 | Bulk BBG | Low |
| **SECURITY_MASTER** / `_UAT` | 11 / 8 | Firm security master | TBD for FFA mapping |
| **GOLDENSOURCE** | 8 | Enterprise/security MDM | Low (keyword hit was false positive on “chartered”) |

## Internal trading / other

| Database | Schemas (n) | One-line description | Freight relevance |
|---|---|---|---|
| **TRADING** / `_UAT` | 3 | OMS / positions / instrument | Possibly useful for desk FFA positions later |
| **VENDOR_PLUS**, **TRAYPORT_DEV**, **FINANCE**, metals, weather, FactSet, etc. | — | Other vendors / platform | Out of scope for Phase 0 freight core |

## Step-2 keyword summary

Table-name keywords (`FREIGHT`, `BALTIC`, `VLCC`, …) were **almost useless**: freight is embedded in ICE `LONG_NAME` and Platts `DESCRIPTION`, not table names.

False positives to ignore: Cybersyn air-freight / export-screening views; LNG charter tables; Xpress `CIQAFFACTOR\*`.

Value-search winners:
- **ICE.MFT.FUTURES.LONG_NAME** — many Baltic tanker FFAs (TD3C, TD20, TD22, TC2, TC14, …) plus dry/LNG/LPG.
- **MDV2.REF_DATA_MARKETDATA.DESCRIPTION** — dirty/clean tanker assessments (WS and $/mt), bunkers/VLSFO; commodity often `Shipping`; `VESSEL_CLASS` populated for VLCC/Suezmax/Aframax/MR/LR.
- **KPLER Snowflake** — not a liquids source.

## Access notes

- Role used: `JG_GENERAL` (not the aspirational `FREIGHT_AGENT_RO` in `.env.example`).
- `SHOW TABLES` on share DBs can look sparse while views (`PRICEDATA`, `REF_DATA_*`) are queryable — same quirk noted in `window_trades_report`.
- No access errors across the 48 DBs in this pass (`_runs/00_access_errors.csv` empty).
