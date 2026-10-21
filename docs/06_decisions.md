# Decisions log

Format: date — decision — reason — alternatives considered.

- 2026-10-05 — Parse Clarksons emails from plain-text bodies (VLCC side panel from PDF) — body is fixed-width and more reliable than PDF layout — PDF-only parsing.
- 2026-10-05 — Clarksons loads are idempotent per report_id; raw bodies retained — allows re-parsing history after parser fixes — append-only loads.
- 2026-10-05 — Discovery phase before any modelling — agent and owner have different data access and context — build-first.
- 2026-10-05 — Use `desk_core` + role `JG_GENERAL` for Snowflake discovery (not a freight-local connector / `FREIGHT_AGENT_RO` until that role exists).
- 2026-10-05 — Treat Snowflake `KPLER` as power-only; liquids/fleet/fixtures via Kpler API — avoid building on that DB for tanker tools.
- 2026-10-06 — ICE tanker FFAs stored/compared in **$/t**; canonical monthlies TDL/TDC/WF2/WHK/WNS/… per `docs/ice_ffa_map.md` — WS quotes and recoded 2024 product codes (WCN/WNU/WAC).
- 2026-10-06 — FFA **OI** from `FILE_FLAG=Final` only; Early is fine for same-day curve. TD3C positioning notebook uses that rule.
- 2026-10-13 — Treat **TD34 (`T34`)** as the outside-Hormuz China VLCC paper twin of TD3C; monitor OI/volume share vs TDL before calling a migration.
- 2026-10-13 — Tonnage-supply **Dash spike** in `freight_dashboard` (`docs/10_tonnage_supply_app.md`): Kpler matcher + Plotly map (BBG AIS positions, geo fallback); overlays = `SHUTTLE_AVAILABLE` + vessel_crossing OFAC iran/sdn by IMO + thin NOC YAML. Parallel to Phase 1; may replace thin Dash strip. Keep `src/freight/` API-clean for possible React later.
- 2026-10-06 — Platts tanker `PRICEDATA` often uses `BATE='u'` (not `c`). Always inspect bates per symbol. Curated series in `docs/platts_series.md`.
- 2026-10-06 — Kpler tanker data is **API-only** (SDK Liquids). Call `with_freight_view=True` on freight endpoints. Do not use Snowflake `KPLER` for liquids.
- 2026-10-07 — Fundamentals for freight context: Platts **PRODUCTION** (MEG crude MBD, Short Term), **DEMAND** (China products MBD), WRD **RUNS/OUTAGES**, desk **IIR** outages. Do **not** treat these as VLCC liftings or inventories. Hormuz/dark-fleet = reuse `vessel_crossing` (IMO parquet), not a new Snowflake build in Phase 0.
- 2026-10-07 — Phase 0 closed for review (`docs/09_phase0_synthesis.md`). No Baltic in Snowflake; FFA primary = ICE $/t; flats missing (imply or buy); bunkers/arb legs = Platts; physical = Kpler API. Phase 1 starts only after human OK on spot path + Clarksons compliance.
