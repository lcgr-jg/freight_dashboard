# Project plan

Goal: a set of tools and a daily report that tell the desk (1) where tanker spot rates are going
over 1–3 weeks, (2) whether FFA paper is mispriced against that view, and (3) how freight
changes crude and product arb economics. Phases are sequential; each ends with a human review.

## Phase 0 — Discovery (no building)
Inventory what exists in Snowflake and other tools; fill `docs/04_data_catalog.md`.
Follow `docs/05_discovery_plan.md`. Exit: catalog reviewed, usefulness matrix agreed,
open questions listed, Phase 1 scope confirmed.

**Status (2026-10-07):** Discovery steps 1–7 done. Synthesis and proposed Phase 1 scope:
`docs/09_phase0_synthesis.md`. **Stop for human review** before Phase 1 build.

## Phase 1 — Foundations
*(Revised after discovery — full rationale in `09_phase0_synthesis.md`.)*

- **1d′. FFA productionise** — ICE wet FFAs already mapped (`docs/ice_ffa_map.md`, `src/freight/ice.py`,
  notebook 01). Promote to a scheduled tidy table (Final for OI); start with TDL / DFN / desk basket.
- **1b′. Spot assessment decision** — No Baltic feed in Snowflake. Choose primary: Platts tanker WS+$/t
  (working proxy), buy Baltic, or Clarksons parse (compliance). One clean `route, date, ws, usd_t`.
- **1c′. Flat rates** — No flat table found. Acquire Worldscale flats **or** imply from Platts dual prints.
- **1a. Clarksons ingestion** — Deploy/backfill only after compliance on use in signals.
- **Kpler physical snapshots** — Daily matcher / fixtures / util / congestion (from `src/freight/kpler.py`
  + notebook 02) into sandbox for PIT backtests (feeds Phase 2 tools A/B/E).
- **H wiring** — Reuse `vessel_crossing` dark-fleet / Hormuz by IMO; do not rebuild.

## Phase 2 — Core analytics (priority order)
| ID | Tool | Inputs | Output |
|---|---|---|---|
| A | Effective tonnage nowcast | Kpler TonnageSupply(Vessels), Fixtures, shadow-fleet flags | Open ships per route window, z-score vs 90d |
| B | Cargo demand by load decade | Kpler Fixtures/Trades, Clarksons decade counts | Cargoes per decade, fail rate |
| C | Spot rate nowcast | A, B, Baltic history | 1–2 week rate forecast per route |
| D | FFA settlement & basis monitor | Baltic daily, ICE FFAs, C | MTD average, implied rest-of-month, basis vs nowcast |
| E | Fleet positioning | Kpler FleetUtilization, BallastCapacity, Congestion | Laden/ballast, East/West, waiting, storage |
| F | Ton-mile demand | Kpler FreightMetrics, balances | Volume vs distance decomposition |
| G | Arb-to-fixture lead | Product arbs (Platts?), Kpler Fixtures | Lead/lag of arb openness on fixture counts |
| H | Mainstream vs restricted fleet | Existing dark-fleet detection | Correct effective supply |

Additional analytics enabled by Clarksons reports + ICE:
- Fixture-to-Baltic lead (today's fixtures vs tomorrow's print).
- Inside vs outside Hormuz premium (Ras Tanura vs Fujairah fixtures, in $/t or TCE).
- Freight-adjusted crude arbs (USG/Brazil/WAF → China landed cost with spot and forward freight).
- Curve and spread monitors (calendar spreads, TD3C vs TD15/TD22, TD20 vs TD3C, TC2–TC14).
- FFA realised vol (and implied, if ICE options exist) → link to the crude vol dashboard.
- MEG ships-per-cargo by decade vs TD3C.

## Phase 3 — Delivery
- Daily report (HTML/PDF or Dash page): spot vs nowcast, FFA basis, key lists, fixtures of note.
- Dash app integrated with existing desk tools.
- Prefect scheduling, data-quality alerts.

## Principles
- Each tool is a tested module in `src/freight/` with a thin app/report layer on top.
- Backtests use point-in-time snapshots only (store daily snapshots of Kpler supply and fixture status).
- Start simple (ratios, z-scores, log-linear fits); add complexity only when validated out of sample.
