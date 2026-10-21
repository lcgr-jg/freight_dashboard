# Phase 0 synthesis (step 7)

**Date:** 2026-10-07  
**Status:** Discovery complete — stop for human review before Phase 1 build.  
**Evidence:** `docs/04_data_catalog.md`, `ice_ffa_map.md`, `platts_series.md`, `kpler_api_map.md`, notebooks `01`–`03`, `sql/discovery/_runs/`.

Phase 0 exit criteria (from `02_project_plan.md`): catalog filled, usefulness matrix agreed, open questions listed, Phase 1 scope proposed. This note is that exit pack.

---

## 1. Best available source (today)

| Need | Best available now | Unit / grain | Gap / must buy or parse |
|---|---|---|---|
| **(a) Baltic daily assessments** | **No Baltic licence feed in Snowflake.** Closest: Platts tanker WS + $/mt (e.g. MEG–China VLCC `AASLB00` / `AASLC00`); ICE **DFN** = index-day **futures** in $/t, not Baltic. Clarksons emails/PDF as broker validation (compliance TBD). | WS, $/t, TCE in reports | Official Baltic BITR history + daily; or compliance OK to treat Platts≡settlement after proof; or parse Clarksons as primary |
| **(b) FFA curves** | **ICE.MFT.FUTURES** wet freight — TDL/TDC/… in **$/t**; Final for OI. Helpers + notebook 01. | $/t × strip × session | Production tidy table in sandbox/warehouse; options (TDL/WDF) optional |
| **(c) Flat rates** | **None as a table.** Implied flat ≈ Platts $/t ÷ (WS/100) per route/day; one-day TD3C sanity ~$19–20/t (Oct 2026). | $/t by route × year | Worldscale Association (or vendor) flat file for 2026 + history |
| **(d) Bunkers** | **Platts MDV2** curated bunker symbols (`docs/platts_series.md`); eWindow is bunker-heavy. | $/t (port) | Confirm ports used in TCE (Fujairah, Singapore, Rotterdam, Houston) |
| **(e) Arb legs** | **Platts MDV2** crude/product assessments (step 4 core list); ArbFlow `PREFERRED_FREIGHT` exists but meaning TBD. | $/bbl etc. | Lock Spore gasoil FOB symbol; clarify ArbFlow |

**Physical tape (not in the five boxes above, but core for A–H):** Kpler Liquids **API** (not Snowflake `KPLER`). Notebook 02 + `src/freight/kpler.py`. Dark fleet / Hormuz: reuse `vessel_crossing` (IMO, local parquet).

**Fundamentals (PRODUCTION / DEMAND):** share views, last altered **2026-07-21**; DEMAND History ends **2024**. Curiosity only (`notebooks/03_…`) — not freight core.

---

## 2. Usefulness matrix

Authoritative copy lives in `docs/04_data_catalog.md` (updated through step 6). Headline:

| Tier | Datasets | Role |
|---|---|---|
| **Core** | ICE MFT wet FFAs; Kpler Liquids API (tonnage, fixtures, util, congestion, ton-miles); `vessel_crossing` for H | Paper + physical + restricted fleet |
| **Useful** | Platts tanker/bunker/arb assessments; IIR outages; Clarksons ingest (pending compliance) | Spot colour, bunkers, arbs, broker tape |
| **Marginal / park** | Platts PRODUCTION/DEMAND/WRD (stale demand history); BBG futures ref (no freight hits); Snowflake KPLER power | Context only or dead ends |
| **Missing** | Baltic licence; Worldscale flats; Kpler voyage-legs / next-dest (403); stocks/inventories | Buy, enable, or imply |

---

## 3. What we already prototyped (ahead of Phase 1)

| Artifact | Covers |
|---|---|
| `src/freight/ice.py` + `notebooks/01_td3c_ffa_positioning.ipynb` | 1d FFA / OI / curve (TDL, DFN) |
| `src/freight/kpler.py` + `notebooks/02_kpler_td3c_physical.ipynb` | A/B/E/F-style tape, China ton-miles, Clarksons-style proxies |
| `packages/clarksons_ingest` | 1a parser (samples tested; deploy + compliance open) |
| `notebooks/03_fundamentals_curiosity.ipynb` | Explicitly **not** freight |

Phase 1 should **promote** ice/kpler helpers into durable tables/jobs, not rediscover them.

---

## 4. Proposed Phase 1 scope (revised)

Keep the spirit of `02_project_plan.md` Phase 1; reorder around what discovery proved.

### Must do (Phase 1)

1. **1d′ — FFA productionise** — Scheduled pull of ICE wet FFAs (Final preferred) into a tidy table; TDL (+ desk default basket) from `ice.py`. Notebook 01 becomes a consumer, not the store.
2. **1b′ — Spot assessment decision** — Pick one primary for “Baltic-like” daily TD3C:
   - **Path A:** Platts WS + $/t as working spot (document ≠ Baltic until proven);
   - **Path B:** Buy/license Baltic;
   - **Path C:** Clarksons parse as primary (needs compliance).  
   Deliver one clean series: `route, date, ws, usd_t` (TCE later).
3. **1c′ — Flat rates** — Either ingest Worldscale flats **or** ship an implied-flat helper from Platts dual prints + annual flat cache when acquired.
4. **1a — Clarksons deploy** — Backfill + monitor only after compliance answer on signal use.
5. **Kpler physical jobs** — Snapshot matcher + fixture counts (+ util/congestion) daily to parquet/Snowflake sandbox for PIT backtests (tool A/B/E). Reuse `kpler.py`.
6. **H wiring** — Call `vessel_crossing` dark-fleet / Hormuz flags by IMO when building effective supply; do not rebuild.

### Explicitly defer

- Spot nowcast model (C) and FFA basis engine (D) → Phase 2 (need 1b + 1d stable).
- Voyage-legs / next-destination → wait for Kpler entitlement.
- Platts PRODUCTION/DEMAND in freight report → park (staleness).
- Full East/West location % like Clarksons pack → needs positions product we do not have.

### Phase 1 exit

Human sign-off on: spot primary (A/B/C), flat strategy, Clarksons compliance, and which routes are v1 (recommend **TD3C / TDL / DFN** only).

---

## 5. Open questions (carry to Phase 1)

See `docs/07_open_questions.md`. Blockers for build:

1. Platts tanker ≡ Baltic settlement?  
2. Flat-rate source (buy vs imply)?  
3. Clarksons → trading signals compliance?  
4. Kpler voyage-legs / next-dest entitlement (nice-to-have)?  
5. Spore gasoil FOB symbol for arb G?

---

## 6. Recommended first build after approval

**Week-1 slice:** production ICE FFA table + daily Kpler MEG matcher / China congestion / MEG→China fixture counts into sandbox + thin HTML/Dash strip for TD3C. Spot series decision in parallel (does not block paper + physical tape).
