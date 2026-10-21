# Kpler liquids / freight API (Phase 0 step 5)

Team explainer (what each series *means*): `docs/kpler_signals.html`. MEG→China tape vs ICE TDL/DFN: `notebooks/02_kpler_td3c_physical.ipynb`.

Verified: 2026-10-06. SDK [kpler.sdk 1.0.64](https://python-sdk.dev.kpler.com/index.html) (`Platform.Liquids` → `https://api.kpler.com/v1`).
Creds: `KPLER_EMAIL` / `KPLER_PASSWORD` in local `.env` (same as `vessel_crossing`). Auth on `/trades/columns` **succeeded**.

REST twin: [Kpler Freight spec](https://developers.kpler.com/spec/freight) (OpenAPI portal). This environment could not render that JS page (corp browser block). The SDK resources below are the freight-relevant surface; use the spec in a normal browser for REST paths/auth.

**Snowflake:** `KPLER.KPLER_POWER` / `KPLER.ONGOING` remain **power generation/load only**. No liquids/fixtures/tonnage tables landed. All tanker work is API.

**Licensed:** do not export vessel/fixture/trade rows. Probe CSVs under `sql/discovery/_runs/07_kpler_*.csv` are counts/column ids only.

## Entitlements (small live calls)

Runner: `sql/discovery/run_step5_kpler.py`. All probed endpoints returned **HTTP-success**, including `with_freight_view=True` (docs: Freight subscription only).

Paired **identical** calls, `with_freight_view` False vs True:

| Call | Off | On |
|---|---|---|
| Ton-miles monthly Total, 13 months | 13×2, same numeric total | same |
| Ballast count daily Total, 15 days | 15×2, same numeric total | same |

So: Freight flag is **accepted** (not 403). On this account it did **not** change global totals — cargo Liquids coverage already matches, or the flag is a no-op for those splits. Still use `with_freight_view=True` on freight tools so we do not silently drop unsubscribed cargo.

`vessel_crossing` already uses Trades / Vessels / STS / PortCalls. **Not used there yet:** Fixtures, TonnageSupply, FreightMetrics, FleetUtilization, Congestion, BallastCapacity.

## Endpoints for tanker freight

| SDK class | What it is | Grain / history | Probe |
|---|---|---|---|
| `TonnageSupplySeries` | Vessels that can reach a zone in N days at given speed (count / dwt / capacity) | **Daily series with history** (Houston VLCC 90d live; **2024-10-01–2024-11-01** also returned 32 days) | 91 rows to 2026-10-06 |
| `TonnageSupplyVessels` | Same matcher, **vessel list** | Window **≤ 6 days**; can stitch history in chunks | 117 rows / 33 cols (6d Houston VLCC) |
| `Fixtures` | Reported fixtures (laycan, origin/dest, charterer, **`rateValue`**) | Filter by `reportedDate`; `size` cap default 1000 | columns 16; VLCC `size=5` ok |
| `FreightMetricsSeries` | Ton-miles, ton-days, avg speed/distance | Monthly/quarterly/annual; 12m VLCC ok; `with_freight_view` | 13 months to 2026-10 |
| `FleetUtilizationSeries` | Loaded vs ballast vs maintenance counts | Daily history (90d VLCC) | 91 days |
| `BallastCapacitySeries` | Ballast capacity/count by type | Daily history | 31d VLCC |
| `CongestionSeries` | Waiting-zone counts/duration | Weekly/monthly; `with_freight_view` | China VLCC 90d |
| `Trades` / `Vessels` / `PortCalls` / `STS` | Cargo/fleet facts (desk already) | Live + history on trades | 536 crude trades last 7d (count only) |
| `TradesSnapshot` | **Point-in-time** trades as of `snapshot_date` | Confirmed: snapshot ~30d ago, crude→China, **196** rows | PIT **yes** for cargoes |

Tonnage **vessel** endpoint is a short window; tonnage **series** is the as-of daily history (not only current state). TradesSnapshot is the cargo PIT. No separate “tonnage snapshot” resource — reconstruct from series or 6-day vessel chunks.

## Fixture columns (ids)

`reportedDate`, `vesselName`, `vesselImo`, `productQuantityInTons`, `vesselDeadweight`, `productName`, `charterer`, `vesselOwner`, `layCanStart`, `layCanEnd`, `origin`, `destination`, `rateValue`, `status`, `vesselTypeCpp`, `vesselTypeOil`.

Statuses include on-subs / in-progress / fully fixed / finished / failed / cancelled. Rates are Kpler’s `$ price` — **not** Baltic WS and not ICE $/t; treat as a third print, compare carefully.

## Freight REST spec vs Python SDK

Source: `docs/kpler/API Spec _ Developer Portal_feight.pdf` (portal export 2026-10-06, 20 pages). That file is **Fleet Development + Voyage (BETA) only** — not fixtures, tonnage supply, or freight-metrics (those stay on Liquids SDK `api.kpler.com/v1`).

Same-host probe with Liquids basic auth: `GET /fleet-development/limits/dates`, `POST /fleet-development/summary`, `POST /voyage/legs`, `POST /voyage/legs/series` all **404** on `https://api.kpler.com/v1`. The REST Freight product is a **different API** (portal lists APIs / Cloud DB / Excel / MCP). Do not assume SDK credentials hit these paths until we have a Freight REST base URL + token.

| REST | In SDK 1.0.64? | Desk relevance |
|---|---|---|
| `POST /fleet-development/series` | Yes (`FleetDevelopmentSeries`) | Structural supply: available / deliveries. REST metrics named `orders`/`removals`; SDK uses `contracting`/`scrapping`. REST `projection=predictive` ≈ SDK `with_orderbook`. REST **splitBy** adds coating / scrubber / engine / fuel (SDK is vessel-type + complianceMethod). |
| `POST /fleet-development/vessels` | Yes (`FleetDevelopmentVessels`) | IMO-level orderbook / in-service / dead. REST statuses finer (On Order, In Build, Laid Up, …). |
| `POST /fleet-development/summary` | **No** | Current vs previous vs last-year KPI. Nice for a dashboard tile; not required for tools A–H. |
| `GET /fleet-development/limits/dates` | **No** | Query bounds (max **5 years** forward from today). Operational only. |
| `POST /voyage/legs` **BETA** | **No** | **Highest interest.** Per-leg object (`legId`, open/closed, cargo on board, from/to zones). Opt-in `expand=port_calls,tonnage_metrics` → **per-leg** ton-miles, ton-days, distance, duration, median speed. Grain below `FreightMetricsSeries`. |
| `POST /voyage/legs/series` **BETA** | **No** | History from **2017-01-01**. Bucket by start or end; count legs / voyages / vessels; split ballast vs laden, open vs closed, **fromZone / toZone**. Directly useful for E/F at corridor level (e.g. MEG→China VLCC ballast legs), not just global VLCC. |

Portal left-nav also lists **Next Destination, Routes, Arbitrage** — see below.

## Next Destination, Routes, Arbitrage (v2 REST)

PDFs in `docs/kpler/`: `…_next_d.pdf`, `…_routes.pdf`, `…_arbitrage.pdf`. **Not in the Python SDK.** Host is `https://api.kpler.com/v2/…`.

**Auth (verified):** portal snippet is `Authorization: Basic [MY API KEY]` with the **raw** key, not Base64 and not Bearer. Liquids email/password still only work on v1. Env var today: `API_KEY` (rename to `KPLER_V2_API_KEY` when convenient).

**Entitlement probe 2026-10-06** (regenerated key):

| Call | HTTP | Meaning |
|---|---|---|
| `GET /v2/fleet-development/limits/dates` | **200** | min 2017-01-01, max ~today+5y |
| `POST /v2/fleet-development/summary` | **200** | current / previous / lastYear |
| `POST /v2/fleet-development/series` | **200** | monthly splits from 2020 |
| `POST /v2/voyage/legs` and `/voyage/legs/series` | **403** | needs `freight:voyages:legs:read` |
| `GET /v2/maritime/next-destination` | **403** | key has no permission |
| `GET /v2/maritime/routes` | **403** | key has no permission |
| `GET /v2/arbitrage/{combinations,products,regions,benchmarks}` | **403** | “User does not have permission” |

So: **Freight fleet-development v2 is on the account.** Next Destination, Routes, Arbitrage, and Voyage-legs are **not**. Ask Kpler to attach those products if we want them; the key itself is valid.

Liquids coverage matrix (portal screenshot): fixtures / congestion / fleet util / freight metrics / ballast / vessel matcher = **v1 only** (SDK we already use). Fleet development = **v2** (this key). Trades/flows/inventories also have v2 docs — not probed here.

| Product | Paths | What it is | vs SDK v1 | Access now |
|---|---|---|---|---|
| Next Destination | `GET /v2/maritime/next-destination` | AIS or schedule next port, Kpler ETA, remaining NM, ECA/HRA, canals | Complements TonnageSupply (“could reach” vs “is going”) | **403** — not on this key |
| Routes | `GET /v2/maritime/routes` | Distance / ECA / HRA / canals / ETA / geometry | Voyage calculator, not WS | **403** |
| Arbitrage | `/v2/arbitrage/combinations` + timeseries | Kpler landed-value arb board | Overlaps Sparta / our G | **403** |
| Fleet development | `/v2/fleet-development/*` | Available / deliveries / orders / removals; summary vs last year | SDK has v1 series/vessels; v2 summary is extra | **200** |
| Voyage legs | `/v2/voyage/legs` **BETA** | Per-leg ton-miles, ballast vs laden, from/to zone | Finer than FreightMetricsSeries | **403** `freight:voyages:legs:read` |

## Traps

- Python SDK **3.9–3.13**; we are on 3.13 in `Coding/.venv`.
- `TonnageSupplyVessels` `end_date` cannot exceed `start_date` by more than 6 days.
- `with_freight_view` default **False** — whole-fleet vs cargo-subscribed fleet.
- v2 REST: `Authorization: Basic <raw API_KEY>` (not Base64, not Bearer). Missing product → **403**, bad scheme → **401**.
- Freight REST spec ≠ a fifth `Platform` enum (only LNG/LPG/Dry/Liquids). Freight is Liquids + flag / Freight REST product.
- Do not land Kpler fixture/trade extracts in git.
