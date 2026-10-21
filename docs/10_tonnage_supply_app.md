# Tonnage supply app (v0 spike)

**Status:** v0 implemented 2026-10-13 — run `python -m apps.tonnage_supply.app` from `freight_dashboard/`.  
**Home:** `freight_dashboard` (not `vessel_crossing`).  
**Role:** Parallel spike for desk tonnage supply (Kpler-style). May supersede Phase 1 “thin Dash” in `09_phase0_synthesis.md`; does **not** block FFA productionise.

## Goal

Interactive Dash app: vessels that can reach a location within N days at a given speed, with filters matching Kpler Tonnage Supply, a vessel table + map, and desk overlays (shuttle available, OFAC sanctions, thin NOC tags).

## Defaults (landing state)

| Control | Default |
|---|---|
| Location | Fujairah (Clarksons MEG open basis) |
| Match next port call | off (toggle available) |
| ETA | 0–7 days (`eta=7`) |
| Avg speed | 11 kn |
| Selection units | Count (series metric; table always vessel-level) |
| State | All |
| Vessel classification | VLCC (`LIQUIDS`) |
| Build year | 2010–2026 |
| Last products | none (all) |

## v0 UI scope

- Filter bar: location (Zones search), match-next-port-call, ETA, speed, Count/Deadweight, All/Loaded/Ballast, **sanctions [All / Sanctioned / Clean]** (default All; client-side on OFAC flags), **AIS dark [All / Non-dark]** (default All; Non-dark drops ships with `last_seen` older than 10 days), vessel classification, build year, last products, reset.
- Charts: historical availability (`TonnageSupplySeries`) + loaded/ballast split + proximity buckets (from vessel `next_eta` / derived distance).
- Vessel table columns: name, DWT, build year, distance, state, previous port, next port, source, products, **next destination, ETA, position, Last position (age), loading region, owner**, **sanctioned** (display column; see overlays), plus `shuttle_available`, `is_noc`.
- Map: Plotly `Scattermapbox` / `Scattermap` style as in `vessel_crossing/polygon_tracker` notebook.

**Defer:** owner choropleth / NOC supply analytics tabs, FFA strip, fixtures, congestion/ballast tabs, Kpler v2 next-destination (403).

## Data sources

| Need | Source | Notes |
|---|---|---|
| Matcher list + series | Kpler Liquids SDK `TonnageSupplyVessels` / `TonnageSupplySeries` | Creds: `KPLER_EMAIL` / `KPLER_PASSWORD`. `with_freight_view=True` where applicable. Vessel window ≤ 6 days. |
| Location options | `Zones.get` | Searchable dropdown |
| Last products tree | `Products.get` | DPP / Crude / Clean hierarchy → `products=` filter |
| Classification / state / metric | SDK enums | `TonnageSupplyVesselTypes`, `TonnageSupplyVesselsState`, `TonnageSupplySeriesMetric` |
| Build year, owner, next dest (live) | `Vessels.get` join on IMO | Matcher lacks build year / owner / lat-lon |
| Positions (map) | **A→B fallback** | **A:** Bloomberg AIS by IMO (same path as polygon_tracker `fetch_bbg`). **B:** approximate last-port / `current_sea` centroid if BBG unavailable. Matcher and `Vessels` have **no lat/lon** (probed 2026-10-13). |
| Shuttle flag | `data/shuttle_tankers_class.xlsx` | Use **only** `SHUTTLE_AVAILABLE` (latest state), keyed by IMO |
| Sanctions | `vessel_crossing` OFAC CSVs | Same join as polygon_tracker `ofac_imo_sets`: `ofac_iran_vessels_history.csv` + latest `ofac_sdn_vessels_*.csv` → `sanctioned_iran`, `sanctioned_sdn`, `sanctioned_any` |
| NOC tag (thin) | Curated `data/noc_owners.yml` + shuttle `OWNER` | Seed from known NOCs in shuttle file (ADNOC, KOTC, BAHRI, …); editable; not a full owner graph |

### Probed matcher columns (Fujairah VLCC, `columns=all`)

`date`, `vessel_imo`, `vessel`, `vessel_dwt_tons`, `vessel_type`, `vessel_state`, `last_product_on_board`, `current_*` geo, `last_port` / `next_port`, `next_eta`, `next_port_call_source`, … — **no** distance, build year, owner, or coordinates. Distance: derive where possible (e.g. from ETA × speed) or show “—” until a better field appears. Loading region: prefer `current_sea` / `current_country` / last cargo origin from enrich if added later.

## Architecture

```
UI (Dash)  →  src/freight helpers  →  Kpler / BBG / local CSVs
                 ↑
         Keep API-clean for a future React front end
```

| Path | Purpose |
|---|---|
| `apps/tonnage_supply/app.py` | Layout + callbacks |
| `apps/tonnage_supply/config.py` | Defaults, paths to vessel_crossing OFAC, cache TTL |
| `apps/tonnage_supply/charts.py` | Series + state/proximity |
| `apps/tonnage_supply/map_view.py` | Plotly map (BBG dots or approx) |
| `apps/tonnage_supply/tables.py` | Vessel grid |
| `src/freight/kpler.py` | Extend: zones search, products tree, parameterized matcher/series, `match_next_port_call` |
| `src/freight/shuttle.py` | Load shuttle xlsx → IMO → `shuttle_available` |
| `src/freight/sanctions.py` | Load OFAC iran/sdn sets (mirror polygon_tracker; path via config) |
| `src/freight/noc.py` | Owner string → `is_noc` via YAML |
| `data/noc_owners.yml` | Curated NOC aliases |
| `data/shuttle_tankers_class.xlsx` | Already present |

Short-TTL parquet cache under `apps/tonnage_supply/.cache/` (gitignored) so filter changes do not hammer Kpler.

## Overlays (effective supply)

For each matcher vessel (IMO):

1. `shuttle_available` — from shuttle sheet only.  
2. `sanctioned_*` — from OFAC files (read-only path into `vessel_crossing`).  
3. `is_noc` — owner match against YAML / shuttle owners.

These are **flags in v0**, not yet used to auto-exclude from counts. Later: “effective open” = matcher − on-subs − sanctioned − (optional) shuttle-held, with explicit toggles.

**Sanctions UX (locked):** filter **All | Sanctioned | Clean** (default **All**), applied client-side after OFAC join (`sanctioned_any`). Always show a **Sanctioned** column on the tanker list (iran/sdn detail in hover or sub-label). Map may tint sanctioned dots differently when positions exist. Does not change Kpler API calls — only the visible table/map/chart subset.

## Stack

- **v0 front end:** Dash + Plotly (desk pattern: `dash_irr_database`).  
- **Future:** React possible; keep fetch/join logic in `src/freight/` (and optionally a thin FastAPI later).  
- Python 3.11+, pandas, existing Kpler SDK; Bloomberg optional for map A.

## Validation

- Fujairah VLCC ETA-7 @ 11 kn vessel count in the same ballpark as notebook 02 / live Kpler UI.  
- Sanction flags: spot-check IMOs present in OFAC CSVs appear as `sanctioned_any`.  
- Shuttle: only rows with `SHUTTLE_AVAILABLE` true light the flag.  
- App runs without Bloomberg (table + charts + map fallback B).

## Open items (non-blocking)

- Exact ETA control UX (single `eta=7` vs buckets 0–2 / 2–4 / 4–7 client-side). Prefer API `eta` + client proximity split like the screenshot.  
- Distance column derivation formula — confirm vs Kpler UI when side-by-side.  
- React migration trigger: only if Dash callback complexity or multi-page nav becomes painful.

## Run

```powershell
cd freight_dashboard
python -m apps.tonnage_supply.app
# http://127.0.0.1:8050
```

Needs `KPLER_EMAIL` / `KPLER_PASSWORD` in `freight_dashboard/.env`. Map prefers Bloomberg, else latest `vessel_crossing/polygon_tracker/output/enriched_*.csv`, else sea/port centroids.

## Implementation order

1. Helpers: parameterized matcher/series, zones, products, shuttle, sanctions, noc. ✅  
2. Dash shell + filters wired to helpers (table first). ✅  
3. Charts (series + state/proximity). ✅  
4. Map A (BBG) with fallback B. ✅  
5. Smoke against Fujairah VLCC (2026-10-13: 164 matcher VLCCs @ Fujairah/7d/11kn; 10 sanctioned, 20 shuttle_available). ✅
