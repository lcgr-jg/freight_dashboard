# Phase 0 discovery plan

Work through the steps in order. After each step, update `04_data_catalog.md`, save queries
in `sql/discovery/`, and give a short summary. Stop at the end for human review.

## Step 1 — Map the estate
- List databases and schemas you can access. For each schema: tables/views, row counts, bytes, last altered.
- Produce `docs/estate_map.md`: a one-line description per schema, grouped by vendor (ICE, Platts, Kpler, internal).

## Step 2 — Find freight data by keyword
Search table names, column names and comments (ILIKE) for:
`FREIGHT, TANKER, BALTIC, BITR, WORLDSCALE, WS, FLAT, FFA, TD3C, TD2, TD15, TD20, TD22, TD25, TD6,
TC2, TC14, TC7, TC12, VLCC, SUEZMAX, AFRAMAX, MR, LR2, TCE, BUNKER, VLSFO, HSFO, FIXTURE, CHARTER`.
Then search the *values* of descriptive columns in instrument/contract master tables
(e.g. product name, description, symbol) for the same terms.

## Step 3 — ICE FFAs
- Identify every tanker freight contract: code, description, route, unit (WS or $/t), lot size,
  listed tenors (month/quarter/cal), first/last data date, settlement history, open interest/volume if present.
- Check whether options on freight exist.
- Check whether ICE data includes the **spot/index** (Baltic) values used for settlement.
- Output: table `route → ICE contract(s)`, unit, coverage.

## Step 4 — Platts
- Freight assessments (dirty/clean tanker, WS and/or $/t), route definitions, coverage.
- Bunker prices (VLSFO, HSFO, MGO by port).
- Crude and product prices needed for arbs: Dubai/Oman, Brent/Dated, WTI Houston/Midland, Murban;
  diesel/gasoline/naphtha at NWE, USG, Singapore, AG.
- Output: list of series ids by use (freight, bunkers, arb legs).

## Step 5 — Kpler in Snowflake
- Which Kpler tables already land in Snowflake (owner has pipelines)? Grain, refresh, history.
- Which freight-relevant SDK endpoints are NOT yet in Snowflake (TonnageSupply, Fixtures,
  FleetUtilization, FreightMetrics, Congestion, BallastCapacity)? Check entitlements by a small API call.
- Is there point-in-time history (snapshots), or only current state?

## Step 6 — Fundamentals and other
- Balances, refinery runs, inventories: note anything that maps to load-region export volumes.
- Existing desk tools (dark-fleet detection, Hormuz watch): tables they write, keys (IMO), refresh.

## Step 7 — Synthesis (stop here)
- Fill the usefulness matrix.
- Answer: What is the best available source for (a) Baltic daily assessments, (b) FFA curves,
  (c) flat rates, (d) bunkers, (e) arb legs? What is missing and must be bought or parsed?
- Propose Phase 1 scope with any changes to `02_project_plan.md`, and list open questions.

**Done 2026-10-07:** see `docs/09_phase0_synthesis.md`. Phase 0 paused for human review.
