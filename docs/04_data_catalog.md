# Data catalog (verified only)

Filled in by agents during discovery. Every entry cites the query that verified it.
Usefulness: 0 = not useful, 1 = marginal, 2 = useful, 3 = core. Workstreams per `02_project_plan.md`.

ICE FFA map: `docs/ice_ffa_map.md`. Platts series: `docs/platts_series.md`. Kpler API: `docs/kpler_api_map.md`.

## Usefulness matrix
| Dataset | 1b Baltic | 1c Flat | 1d FFA | A | B | C | D | E | F | G | H | Report |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ICE.MFT.FUTURES (wet freight) | 1 | 0 | 3 | 0 | 0 | 1 | 3 | 0 | 0 | 0 | 0 | 3 |
| ICE.MFT.OPTIONS (TDL, WDF) | 0 | 0 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| ICE.MFT.MARKERS_AND_INDICES | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SPGICI MDV2.REF_DATA + PRICEDATA (Shipping/tanker/bunker) | 2 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 2 |
| SPGICI EWMD eWindow | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 1 |
| SPGICI_ARBFLOW (PREFERRED_FREIGHT) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 1 |
| KPLER.* (Snowflake) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Kpler Liquids SDK / Freight (`api.kpler.com/v1`) | 0 | 0 | 0 | 3 | 3 | 2 | 0 | 2 | 2 | 2 | 1 | 2 |
| BLOOMBERG.BBGH_FUTURES.FUTURE_REF | 0* | 0 | 0* | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| BBG_DLPLUS MiFID freight cols | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 1 | 0 | 1 |
| SPGICI_WORLDREFINERYDATA.WRD.RUNS / OUTAGES | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 1 |
| SPGICI_GLOBALOILDEMAND.MGODF.DEMAND | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 1 | 0 | 1 |
| COMMOD.IIR.OFFLINE_EVENTS | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 1 |
| vessel_crossing polygon_tracker (local) | 0 | 0 | 0 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 2 |

\*Probed; no freight hits in the columns searched. Revisit with better keys in step 3.

## Entries

### `ICE.MFT.FUTURES`
- **What it is:** ICE MFT futures (wet freight FFAs among many other products).
- **Grain / primary key:** `TRADE_DATE` × product (`LONG_NAME` / `COMMODITY` code) × `STRIP` × `FILE_FLAG` (`SOURCE`). Early vs Final can duplicate a session.
- **Coverage:** tanker monthlies from ~2014–2016; last print at least **2026-10-12**. Front-month strips `MonYY`; daily minis/balmos use dated strips.
- **Refresh:** MFT Early/EOD same day; Final later. OI populated on Final; Early OI often null.
- **Key columns & units:** `SETTLEMENT_PRICE` is **USD/t** (ICE specs: $0.0001/t). Also `STRIP`, `TOTAL_VOLUME`, `OPEN_INTEREST`, `FILE_FLAG`. Lot 1,000 t monthly / 100 t daily mini (sampled specs).
- **Freight-relevant subset:** see `docs/ice_ffa_map.md`. Desk defaults: TDL, TDC, WF2, WHK, WNS, WSN, TDK, WNC, WF5, WFW, **T34**.
- **Sample values:** 2026-10-05 TDL Oct26 **238.294**; DFN Oct-05-26 **250.7313**; WHK Oct26 **89.247**. **T34** listed 2026-10-05; 2026-10-12 total OI **4,737** vs TDL **~35.8k**.
- **Quality issues:** `%FFA%` filter misses **TDC**. Code recodes Dec-2024 (WCN→WHK, WNU→WNS, WSL→WSN, WAC→TDC). Dry TCA / LPG / LNG in the same table. Historical day-coded balmos (`1A0`…).
- **Joins:** `COMMOD.ICE_MFT.ICE_MFT_FUTURES`; options on TDL/WDF.
- **Overlaps / validation:** Platts tanker assessments; Clarksons Baltic WS (need flat rates to convert). TD3C−TD34 = Hormuz gap notebook `03_td34_vs_td3c`.
- **Verified by:** `sql/discovery/run_step3_ice_ffas.py`, `run_step3_ice_followup.py`, `run_td34_inventory.py` → `_runs/07_td34_*.csv`; ICE product list.
- **Usefulness notes:** **1d/D/Report = core**. Daily minis are a $/t proxy for index days, not a licensed Baltic series. T34 is seed liquidity (not a full migration from TDL).

### `ICE.MFT.OPTIONS`
- **What it is:** ICE MFT options on the same wet-freight underlyings.
- **Grain / primary key:** as futures plus `PUT_CALL` / `STRIKE`.
- **Coverage:** **TDL** avg-price options 2020-10-22–2026-10-02; **WDF** 2026-04-10–2026-10-02. Older TC2/TC6/TD3 options expired.
- **Refresh:** same MFT files.
- **Key columns & units:** `SETTLEMENT_PRICE`, `OPTION_VOLATILITY`, `DELTA_FACTOR`, volume/OI. Premium unit TBD (likely $/t).
- **Freight-relevant subset:** TDL, WDF (live); ignore expired.
- **Verified by:** `run_step3_ice_ffas.py` → `_runs/05_ice_ffa_options.csv`.
- **Usefulness notes:** 2 for implied vol vs crude vol dashboard; not required for v1 report.

### `ICE.MFT.MARKERS_AND_INDICES`
- **What it is:** ICE markers/indices view.
- **Grain / primary key:** `DATE` × `PRODUCTNAME` / `PRODUCTID`.
- **Freight-relevant subset:** **none** — TD3C/TC14/TDL/DFN/Baltic/BITR/BDTI/Worldscale all 0.
- **Verified by:** `run_step3_ice_ffas.py` (second, code-aware probe).
- **Usefulness notes:** 0. No Baltic spot feed here.

### `SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA` (+ `PRICEDATA`)
- **What it is:** Platts symbol dictionary; prices in sibling `PRICEDATA`. Curated IDs in `docs/platts_series.md`.
- **Grain / primary key:** `SYMBOL` (ref); prices `SYMBOL` × `ASSESSDATE` × `BATE`.
- **Coverage:** tanker prints through **2026-10-06** (Asia) / **2026-10-05** (Atlantic). Some series back to 1980s. Daily weekday + MAvg (`03`) pairs. `FC` schema: **no** freight-named objects.
- **Refresh:** EOD Platts share (desk-standard).
- **Key columns & units:** `DESCRIPTION`, `COMMODITY='Shipping'` for routes, `VESSEL_CLASS`, `UOM` (`WSC`, `MT`, `LSM`), `ACTIVE`, `BENCHMARK`, `ASSESSMENT_FREQUENCY`. Prices: `VALUE`.
- **Freight-relevant subset:** 477 active daily dirty/clean (ex-carbon, WSC/MT/LSM). MEG–China VLCC **AASLC00** $/t + **AASLB00** WS. Bunkers: `MFSPD00`/`MFRDD00`/`MFFJD00`/`MFHOD00` VLSFO delivered. Crude: `PCAAS00`, `PCAAT00`, `PCABS00`, `AMIFA00`, `AAYRG00`.
- **Sample values (on-box):** 2026-10-06 AASLC00 **251.56 $/t**, AASLB00 **WS 1210**. Use `_runs/06_platts_tanker_latest_allbate.csv`.
- **Quality issues:** tanker `BATE` often **`u` not `c`** — `BATE='c'` (window_trades pattern) drops most routes. `MDC ILIKE '%FRE%'` is noisy. Carbon (`TDZ`) and CTI $/day indexes are not route FFAs. Baltic codes are not Platts symbols.
- **Joins:** `PRICEDATA` on `SYMBOL`. ICE Platts-settled FFAs (WDF, WPC, WGC, WNE) vs matching Platts route, not Baltic.
- **Overlaps / validation:** vs ICE $/t (AASLC00 ≈ DFN same week); vs Baltic WS still open.
- **Verified by:** `run_step4_platts.py`, `run_step4_platts_followup.py`.
- **Usefulness notes:** **core for G/C/Report bunkers + Platts routes**. Parallel to Baltic, not a substitute until overlay.

### `SPGICI_EWINDOW_MARKETDATA.EWMD.*`
- **What it is:** eWindow dictionary/metadata/tradedata.
- **Grain / primary key:** order/trade level (see window_trades_report). `EWINDOW_DICTIONARY` is **column documentation** (`COLUMN_NAME`, `DEFINITION`), not a product list.
- **Coverage / refresh:** known desk source. 77 `MARKET` values in `TRADEDATA`.
- **Key columns & units:** `MARKET`, `HUB`, `PRODUCT`, prices (`PRICE` / `C1_PRICE` quirks).
- **Freight-relevant subset:** **bunker** markets only — `EU Bunker`, `US Bunkers`, `ASIA Bunker SG`, `ASIA Bunker North`, `Asia Bunker AG`. **No** tanker/FFA `MARKET`.
- **Sample values:** `_runs/06_ewindow_markets.csv` (row counts; ASIA FO Swap is largest).
- **Quality issues:** licensed SPGICI data.
- **Joins:** Platts bunker symbols / ICE paper.
- **Overlaps / validation:** bunker eWindow vs `PRICEDATA` delivered bunkers.
- **Verified by:** `run_step4_platts_followup.py`.
- **Usefulness notes:** 1 for bunker liquidity colour; 0 for FFA curve.

### `SPGICI_ARBFLOW.ARBFLOW_V2.MARGINS_CATALOG`
- **What it is:** ArbFlow margins catalog.
- **Grain / primary key:** TODO.
- **Coverage / refresh:** TODO.
- **Key columns & units:** includes `PREFERRED_FREIGHT` (boolean) — meaning TODO.
- **Freight-relevant subset:** rows with preferred freight flags; likely links freight into margin calcs.
- **Sample values:** TODO.
- **Quality issues:** TODO.
- **Joins:** other ArbFlow margin tables (step 4/6).
- **Overlaps / validation:** vs desk arb boards / Sparta.
- **Verified by:** column keyword hit in step 2.
- **Usefulness notes:** useful for tool G (arb-to-fixture) once understood.

### `KPLER.KPLER_POWER` / `KPLER.ONGOING`
- **What it is:** Kpler **power** generation/load/availability tables.
- **Grain / primary key:** power-unit / fuel-type time series.
- **Coverage:** large power histories.
- **Refresh:** ongoing schemas suggest operational power feeds.
- **Key columns & units:** power-specific.
- **Freight-relevant subset:** **none**.
- **Sample values:** n/a for freight.
- **Quality issues:** name collision — do not assume liquids Kpler is in Snowflake.
- **Joins:** n/a.
- **Overlaps / validation:** liquids fleet/fixtures/tonnage → **Kpler API** (`vessel_crossing` credentials).
- **Verified by:** `01_tables_KPLER.csv`.
- **Usefulness notes:** 0 for this project’s tanker workstreams.

### Kpler Liquids / Freight API (`kpler.sdk`, `Platform.Liquids`)
- **What it is:** REST `https://api.kpler.com/v1` via Python SDK. Freight resources documented at [python-sdk.dev.kpler.com](https://python-sdk.dev.kpler.com/index.html); REST spec [developers.kpler.com/spec/freight](https://developers.kpler.com/spec/freight). Map: `docs/kpler_api_map.md`.
- **Grain / primary key:** series = date × split; vessels/fixtures/trades = IMO / fixture / trade id.
- **Coverage:** Liquids auth **ok**. Fixtures, tonnage (series + 6-day vessel list), freight metrics, fleet util, ballast, congestion all returned data. Tonnage series history at least **2024-10**. `TradesSnapshot` PIT **yes**.
- **Refresh:** live API (not in Snowflake).
- **Key columns & units:** fixtures `rateValue` ($); tonnage count/dwt; ton-miles `kt/nmi`.
- **Freight-relevant subset:** all of the above. `with_freight_view=True` accepted; identical totals vs False on global Total probes.
- **Quality issues:** fixture `$` ≠ Baltic WS ≠ ICE $/t. Vessel lists max 6-day windows. Do not commit extracts.
- **Joins:** IMO to `vessel_crossing` / AIS; origin/dest zones to Platts/ICE routes (manual map).
- **Overlaps / validation:** Clarksons fixture sheets; Platts tanker; ICE FFAs (rates).
- **Verified by:** `sql/discovery/run_step5_kpler.py`.
- **Usefulness notes:** **core for A/B** (tonnage + fixtures). Not a Baltic/FFA price source.

### `BLOOMBERG.BBGH_FUTURES.FUTURE_REF`
- **What it is:** Bloomberg futures reference.
- **Grain / primary key:** TODO (ticker keys).
- **Coverage:** ~18k rows in base table metadata.
- **Key columns & units:** probed `BBG_FULL_TICKER`, `BBG_ORIG_TICKER` — no hits for freight/baltic/td3/tc14/vlcc/worldscale/tanker.
- **Freight-relevant subset:** unknown; may use different ticker conventions.
- **Verified by:** `run_value_search_lean.py` (negative on ticker fields).
- **Usefulness notes:** revisit via Bloomberg yellow-key / category fields or `desk_core.bloomberg` live refdata in a later step.

### `BBG_DLPLUS.CORE.INSTRUMENT` (MiFID freight fields)
- **What it is:** DL+ instrument master with `MIFID_FREIGHT_ROUTE`, `MIFID_FREIGHT_SUB_TYPE_SIZE`.
- **Freight-relevant subset:** columns exist; `WHERE MIFID_FREIGHT_ROUTE IS NOT NULL` returned **0 rows** in this pass.
- **Verified by:** `03_bbg_dlplus_freight_routes.csv`.
- **Usefulness notes:** 0 for now.

### `SPGICI_WORLDOILSUPPLY.SUPPLY.PRODUCTION`
- **What it is:** Platts World Oil Supply — country/grade crude & NGL production (and capacity / disruption rows).
- **Grain / primary key:** `YEAR` × `MONTH` × country × supply/production/grade elements × `SCENARIO_TERM_NAME` (`Short Term` / `Long Term`).
- **Coverage:** years **1995–2060** (~1.3M rows live; archive much larger). Short Term to **2027**; Long Term annual-ish (`MONTH=0`).
- **Refresh:** share feed (not probed cadence).
- **Key columns & units:** `VALUE` in **MBD**; Saudi/UAE/Iraq/Kuwait/Iran/China all present.
- **Freight-relevant subset:** MEG producer crude `Production` Short Term monthly → cargo generation context for TD3C; not exports and not VLCC liftings.
- **Sample values:** Saudi Short Term 2023-01 crude production rows by grade (e.g. Medium Sour ~1.1 MBD slices).
- **Quality issues:** Long Term mixes with Short Term — filter scenario. Not a substitute for Kpler MEG liftings / fixtures.
- **Joins:** country name → Kpler zones (manual). No IMO.
- **Overlaps / validation:** Kpler ton-miles / trades; Clarksons MEG liftings charts.
- **Verified by:** `run_step6_fundamentals.py`, `run_step6_fundamentals_followup.py`, `08_supply_*.csv`.
- **Usefulness notes:** **2 for F** (demand regime / producer context). Marginal for A/B vs physical tape.

### `SPGICI_WORLDREFINERYDATA.WRD` (`RUNS`, `OUTAGES`, `REF_DATA_REFINERIES`)
- **What it is:** Platts World Refinery Data — quarterly runs/slate and outage schedule by refinery/unit.
- **Grain:** `RUNS` = `YEAR`×`QUARTER`×refinery×process unit; `OUTAGES` = dated outage events (`DATE` 2011–2027).
- **Coverage:** RUNS **2005–2024**, ~250k rows, ~1.7k refineries. China plants named `China | …` (Sinopec/CNPC/CNOOC).
- **Key columns & units:** `MBCD` / `MBSD` run rates; outage `OUTAGE_VOL_MBD`.
- **Freight-relevant subset:** China (and India/Korea) runs/outages as **discharge-basin demand**; MEG refinery outages secondary.
- **Quality issues:** RUNS stop at **2024** in this pull (stale vs 2026). Not crude export volumes.
- **Verified by:** `08_wrd_*.csv`.
- **Usefulness notes:** **1–2** for E/F/G context (China runs), not core tonnage nowcast.

### `SPGICI_GLOBALOILDEMAND.MGODF.DEMAND`
- **What it is:** Global oil product demand by country.
- **Grain:** `YEAR`×`MONTH`×country×product×scenario.
- **Coverage:** **2015–2028**, 152 countries, 10 products (gasoil, gasoline, jet, naphtha, LPG, RFO, …). Units **MBD**. China includes Forecast months into 2026.
- **Freight-relevant subset:** China (and India) product demand as import/haulage backdrop — still not VLCC cargo counts.
- **Quality issues:** `Crude Burn` is not crude imports. No inventory/stocks series here.
- **Verified by:** `08_demand_*.csv`.
- **Usefulness notes:** **2 for F** regime; pair with Kpler China ton-miles, not instead of them.

### `COMMOD.IIR.OFFLINE_EVENTS` (+ `_CURRENT` / `_RAW`)
- **What it is:** Industrial Info Resources plant/unit outage events (desk already uses via `dash_irr_database` / `desk_core.presets.iir`).
- **Grain:** `EVENT_ID` × unit; dates `START_DATE`/`END_DATE`.
- **Coverage:** ~772k rows; petroleum/refining events for China (~64k), Saudi, UAE, Iraq, Kuwait, India, Korea, Japan, US.
- **Refresh:** file loads (`TIME_STAMP` / `FILE_NAME` on rows); sample LIVE_DATE **2026-10-06**.
- **Key columns:** `PLANT_NAME`, `COUNTRY`, `CAP_OFFLINE`, `CAP_UOM` (often BBL/d), `EVENT_TYPE`, `IND_DESC`.
- **Freight-relevant subset:** China/MEG refining outages → product/crude pull context.
- **Joins:** plant/geo only; no IMO. Prefer this over WRD outages for live desk workflow if dashboard already wired.
- **Verified by:** `08_iir_*.csv`, `08_iir_offline_events_sample.csv`.
- **Usefulness notes:** **1–2** for E/G; tool H still needs vessel-level dark fleet, not IIR.

### `vessel_crossing` Hormuz / dark-fleet stores (local, not Snowflake)
- **What it is:** Desk tools — `polygon_tracker` zone events/snapshots; `kpler_vs_soh` Hormuz reconciliations; OFAC/sanction flags as dark fleet.
- **Grain / primary key:** **IMO** × `run_id` / `as_of` (parquet under tool `cache/`; Snowflake-shaped schema in `store.py`, warehouse load TBD).
- **Coverage:** operational AIS/zone history for blockade / SoH corridor; not a global VLCC position list like Clarksons East/West %.
- **Freight-relevant subset:** tool **H** (restricted vs clean), Hormuz premium context, SoH flow vs loadings.
- **Verified by:** code review `vessel_crossing/polygon_tracker/{store,config,README}.md` (step 6); no Snowflake landing yet.
- **Usefulness notes:** **3 for H**; **2 for A** when MEG list must exclude dark/restricted. Reuse — do not rebuild.

## Not yet in catalog (next steps)
- Flat rates (Worldscale Association) — still unknown source.
- Baltic daily assessments as a clean series — not confirmed in ICE markers; Platts tanker WS exists but settlement-equivalence TBD.
- Crude **inventory/stocks** time series in Snowflake — not found in the three SPGICI fundamentals schemas probed (demand ≠ stocks).
- `vessel_crossing` parquet → Snowflake (optional) for shared queries.
