# Tanker freight and FFAs: domain primer

Condensed for agents. The long-form version with charts is a published page the owner has
(Claude artifact "Tanker freight primer"). This file is the reference agents should use.

## Core model
Freight is the clearing price, per load region and fixing window, between ships that can
physically arrive in time and cargoes that need lifting. Short-run supply is almost fixed,
and demand is consumed as **ship-days**, so the true demand unit is **ton-miles** (or ton-days),
not barrels. Rates are **convex**: flat when lists are long, near-vertical when the list empties.

Causal chain used throughout: arb opens → cargoes fixed → regional list drains → owners gain
pricing power → ships ballast in from other regions → list rebuilds → rates normalise.

## Ships
| Class | DWT | Typical cargo | Notes |
|---|---|---|---|
| VLCC | 200–320k | ~2m bbl crude | Long-haul crude |
| Suezmax | 120–200k | ~1m bbl crude | WAF, Black Sea/CPC, Guyana |
| Aframax / LR2 | 80–120k | 600–750k bbl crude / 75–90kt products | LR2 = coated |
| Panamax / LR1 | 55–80k | ~55–65kt products | |
| MR | 25–55k | ~37kt products | Workhorse of product trade |

Dirty = crude and fuel oil (DPP). Clean = refined products (CPP), coated tanks.
Switching clean→dirty is easy; dirty→clean requires slow, costly tank cleaning.

## Baltic benchmark routes (settlement references for FFAs)
| Route | Ship / size | Voyage |
|---|---|---|
| TD3C | VLCC 270kt | Ras Tanura → Ningbo (MEG–China) |
| TD2 | VLCC 270kt | MEG → Singapore |
| TD15 | VLCC 260kt | WAF → China |
| TD22 | VLCC 270kt | USG → China (quoted as lumpsum $) |
| TD6 | Suezmax 135kt | Black Sea (CPC) → Med |
| TD20 | Suezmax 130kt | WAF → Rotterdam |
| TD23 | Suezmax 140kt | MEG → Med |
| TD25 | Aframax 70kt | USG → Rotterdam |
| TC2 | MR 37kt | Rotterdam → New York |
| TC14 | MR 38kt | Houston → Amsterdam |
| TC7 | MR 30kt | Singapore → East Australia |
| TC12 | MR 35kt | Sikka → Chiba (naphtha) |
| TC1 / TC5 | LR2 75kt / LR1 55kt | MEG → Japan |
Other codes: TD27/TD33 — still verify in Baltic/Clarksons. **TD34** = Gulf of Oman→China VLCC (outside Hormuz); ICE monthly `T34` (listed 2026-10-05).
TC2 and TC14 form an MR triangle; owners price the round trip.

## Fixtures
A fixture is a concluded charter (ship, cargo, laycan, rate, charterer). Lifecycle:
cargo quoted → owners offer → **on subs** (agreed subject to conditions) → **fully fixed** or **failed**
→ load → laden voyage → discharge → **ballast** to next load area.
Position lists show ships by ETA at a reference point with comments: SUBS, HOLD, INSIDE ONLY,
PREFER ATLANTIC, EX D/D (ex dry dock), N/B (newbuild). Raw counts overstate supply: on the
5 Oct 2026 Clarksons MEG list, 38 ships had ETA ≤14 days but only 7 were genuinely open.
Traders (Trafigura, Mercuria, Vitol...) time-charter ships and relet them; they act as owners.

Charter types: voyage charter (per cargo, WS/$/t/lumpsum, owner pays fuel), time charter
(daily hire, charterer pays fuel), COA (series of cargoes).

## Units
- `usd_t = flat_rate * WS / 100`; flat rates published annually by the Worldscale Association, reset 1 Jan.
- `usd_voyage = usd_t * cargo_t`; `usd_bbl = usd_t / bbl_per_t` (crude ~7.33).
- `TCE = (gross freight - bunkers - port costs) / round-voyage days`.
- Normal-year TD3C ≈ WS 50–70 (~$1.5–2/bbl). Oct 2026 TD3C ≈ WS 1,240 (TCE >$1m/day).

## Rate drivers
Demand: export volumes per load region and decade; haul length (ton-miles); arb openness (clean).
Effective supply: ballast positioning (East/West split), laden/ballast ratio, waiting and
congestion, floating storage, dry dock (seasonal), speed, sanctioned/shadow-fleet segmentation,
fleet growth (orderbook), bunker prices, war-risk and owner willingness, seasonality (Q4–Q1 strong for crude).

Clean freight is arb-driven: a product cargo moves only if destination minus origin price
covers freight. When an arb shuts, route demand can vanish within days.

## FFAs
- Cash-settled vs the **monthly average** of the Baltic daily assessment; cleared on ICE, SGX, EEX.
- Front-month paper minus spot = market forecast of the rest of the month.
- `implied_rest = (ffa * N - sum(published)) / (N - n)`.
- Curve shape encodes a regime view (e.g. TC14 Oct-26 WS 320 → Q3-27 WS 161 = market expects arbs to close).
- Confirm per-contract unit, lot size and settlement from exchange data.

## Reference values for sanity checks (5 Oct 2026)
- Baltic: TD3C WS 1,240.63; TD2 WS 1,168.75; TD15 WS 688.75; TD22 $60,444,444 lumpsum.
- Baltic 2 Oct: TD6 WS 920.56 (TCE $739,566/d); TD20 WS 878.89 ($500,149/d); TD23 WS 931.11.
- Bunkers VLSFO $/t: Fujairah 957, Singapore 881.5, Rotterdam 680, Houston 726.5.
- WTI 90.31, Brent 101.22 (VLCC evening report).
- MEG VLCC cargoes: Sep decades 35/45/44; ships ex-subs Oct 3rd decade 93, Nov 1st 61, Nov 2nd 52.

## Glossary
Ballast (sailing empty) · Laycan (loading window) · Decade (10-day block of a month) ·
On subs · Fully fixed · Failed · Hold · Relet · RNR (rate not reported) · RPTD (reported, unconfirmed) ·
O/O (or other vessel) · PPT (prompt) · STS (ship-to-ship) · TCE · Ton-miles · Flat rate · WS ·
Non-restricted fleet (excludes sanctioned and dark-fleet ships) · FFA · BDTI/BCTI (Baltic dirty/clean indices).
