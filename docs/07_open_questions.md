# Open questions

- [x] ICE tanker FFA units and canonical codes — **$/t**; map in `docs/ice_ffa_map.md`. Prefer Final `FILE_FLAG` when present.
- [x] ICE Baltic **spot/index** in markers? **No.** Daily minis (e.g. DFN) are futures on the index day, not a Baltic licence feed.
- [ ] Are Platts dirty/clean tanker WS series settlement-equivalent to Baltic, or a parallel assessment? (ICE also lists Platts-settled FFAs: WDF, WPC, WNE, WGC, …). Step 4: MEG–China VLCC is `AASLC00`/$ + `AASLB00`/WS — same ballpark as DFN/Baltic on 5–6 Oct 2026, not an identity proof.
- [ ] Source of Worldscale flat rates for 2026 (and history)? Implied TD3C flat ≈ $19–20/t from TDL vs WS 1240 on 5 Oct 2026 — not a source. Platts often publishes both WS and $/mt, so flat can be implied per route/day.
- [x] Do Platts tables include tanker freight assessments? **Yes** — curated in `docs/platts_series.md`.
- [ ] Singapore 10ppm gasoil cargo symbol (FOB Spore) — not locked in step 4 name filters.
- [x] Is Kpler liquids already in Snowflake? **No** — `KPLER` DB is power-only; liquids via API.
- [x] Kpler **v2** auth is `Authorization: Basic <raw API_KEY>` (not Bearer). **On this key:** fleet-development 200; Next Destination / Routes / Arbitrage / voyage-legs **403**. Ask Kpler to enable those products if needed.
- [ ] Compliance: may Clarksons report data be used as input to trading signals?
- [ ] Definitions of TD27, TD33 as used in Clarksons reports.
- [x] **TD34:** ICE `T34` = Gulf of Oman→China (Baltic) monthly FFA, listed 2026-10-05. Live through at least 2026-10-12; no mini/balmo. Notebook `03_td34_vs_td3c`.
- [ ] Clarksons email body via Microsoft Graph: does plain-text conversion keep column spacing? (verify on backfill)
- [ ] Meaning of ArbFlow `PREFERRED_FREIGHT` and which freight series it points to.
- [ ] Do we need a Snowflake stocks/inventory source for freight, or is Kpler floating storage + China congestion enough?
- [ ] Land `vessel_crossing` Hormuz/dark-fleet parquet into Snowflake, or keep local-only for tool H?
