# Known and suspected data sources

Status: **known** = confirmed exists for the owner; **suspected** = likely, verify in Phase 0.
Verified details belong in `04_data_catalog.md`, not here.

| Source | Status | What it should give | Notes |
|---|---|---|---|
| ICE futures prices in Snowflake | known | FFA settlements/curves for tanker routes | `ICE.MFT.FUTURES` $/t; map in `docs/ice_ffa_map.md`. No Baltic index in `MARKERS_AND_INDICES`. Options: TDL, WDF |
| Platts prices in Snowflake | known | Crude/product assessments; tanker freight + bunkers | Curated IDs: `docs/platts_series.md`. Not Baltic codes as symbols. Tanker bate often `u` |
| Fundamentals in Snowflake | known (verified step 6) | Production MBD, refinery runs/outages, product demand MBD; IIR outages | Not inventories/stocks; not VLCC liftings — see catalog |
| Kpler API (Liquids) | known | Fleet, positions, fixtures, tonnage supply, ton-miles, trades | SDK 1.0.64; map `docs/kpler_api_map.md`. Freight endpoints entitled. Same `.env` as `vessel_crossing` |
| Kpler Snowflake DB | known (not liquids) | Power load/generation only | Do **not** use for tanker freight; no liquids tables landed there |
| Clarksons emails | known | VLCC evening (fixtures, Baltic subset, bunkers, decade counts), Suezmax daily (fixtures, cargoes, Baltic subset, bunkers, Brent, EUA, Turkish Straits delays) | Parser in `packages/clarksons_ingest`. Licensing: check before use in signals |
| Clarksons weekly VLCC deck / position lists / cargo counts | known (files) | Availability, ballast positioning, China tracking, floating storage, fleet | Manual files today |
| Sparta research notes | known (PDF) | Arb boards, FSD model forecasts, trade ideas | Benchmark for our models; not a data feed |
| Baltic Exchange data licence | unknown | Full daily route assessments, history | ICE daily minis are a $/t proxy, not a Baltic licence. Still needed for WS prints and official index days |
| Worldscale flat rates | unknown | Annual $/t by route | Needed to convert WS ↔ $/t |
| Owner's existing tools | known | `vessel_crossing` Hormuz/dark-fleet (local parquet, IMO keys); IIR via `COMMOD.IIR`; crude vol / other Dash apps | Reuse, don't rebuild. Hormuz not in Snowflake yet |
