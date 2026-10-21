# ICE wet freight FFAs (Phase 0 step 3)

Sources:
- Exchange list: [ICE Wet Freight](https://www.ice.com/products/Futures-Options/Freight/Wet-Freight)
- Specs sampled: [DFN daily TD3C mini](https://www.ice.com/products/67119990/Daily-TD3C-FFA-Middle-East-Gulf-to-China-Baltic-Mini-Future) (100 t, $/mt), [WHK TC14 monthly](https://www.ice.com/products/83047767/TC14-FFA-USGC-to-Continent-Baltic-Future) (1,000 t, $/mt), [WDF Platts dirty USGC–UKC](https://www.ice.com/products/83047817/Dirty-FFA-USGC-to-UK-Continent-Platts-Future) (1,000 t, $/mt, Platts Tankerwire)
- Snowflake: `ICE.MFT.FUTURES` / `OPTIONS`, tagged `freight-agent:discovery-ice-ffas*`
- Raw: `sql/discovery/_runs/05_ice_*.csv`

Verified: 2026-10-06 (map); TD34 re-check 2026-10-13. Last print in sample: **2026-10-12**.

## Units (locked)

ICE tanker FFAs are **cash-settled in USD per metric tonne**, not Worldscale points. Monthly contracts are typically 1,000 t; daily minis 100 t. Final settlement = average of Baltic (or Platts) **assessments converted to $/mt** over the determination period.

Screen quotes in WS elsewhere on the desk must be converted before comparing to `SETTLEMENT_PRICE`.

Sanity (5 Oct 2026): primer Baltic TD3C **WS 1,240.63**. ICE `TDL` Oct-26 = **$238.294/t**; `DFN` Oct-05-26 daily = **$250.73/t**. Implied flat ≈ $19–20/t — plausible; daily vs remaining-month average will differ.

## How to read `ICE.MFT.FUTURES`

- **Grain:** `TRADE_DATE` × product (`LONG_NAME` / `COMMODITY` code) × `STRIP` × `FILE_FLAG` (and `SOURCE`). Same-day can duplicate Early vs later file; prefer **Final** when present, else Early.
- **Strip:** monthlies `MonYY` (Oct26, Nov26, … out to ~2029/30); minis/balmos are **calendar dates** (`Oct-05-26`).
- **OI:** often null on Early prints; populated on the paired row when both exist.
- **Convenience view:** `COMMOD.ICE_MFT.ICE_MFT_FUTURES` (same prices; extra ingest timestamps).
- **Trap:** `LONG_NAME ILIKE '%FFA%'` **misses** `TDC` (TD20 monthly: `TDC-TD20 West Africa to UK-Continent (Baltic) Future`).

Product codes were recoded around **2024-12-09/31** (EU ETS packaging): `WCN`→`WHK` (TC14), `WNU`→`WNS` (TC2), `WSL`→`WSN` (TC6), `WAC`→`TDC` (TD20).

## Route → live contracts (prints through 2026-10-12; core map from 2026-10-05)

Canonical **monthly** in bold. Dead codes in parentheses.

| Route | Index | Monthly | Balmo | Daily mini | Lot (ICE spec) | Notes |
|---|---|---|---|---|---|---|
| TD3C MEG–China VLCC | Baltic | **TDL** | TDM | DFN | 1,000 / 100 t | Most liquid. Avg-price **options** `TDL` live to 2026-10-02 |
| TD15 WAF–China VLCC | Baltic | **WFW** | — | — | TBD | First listed **2026-10-05** (15 rows) |
| TD22 USG–China VLCC | Baltic | **WF2** | WF3 | WHG | TBD | Baltic quotes lumpsum; ICE still $/t |
| TD20 WAF–UKC Suezmax | Baltic | **TDC** | TDA | DFQ | TBD | TDC name has no “FFA”. Old monthly `WAC` |
| TD25 USG–ARA Aframax | Baltic | **WF5** | — | — | TBD | Med variant of WF5 died 2022 |
| TD7 UKNS–Cont | Baltic | **WNC** | — | DFO | TBD | Thin volume |
| TD8 Kuwait–Singapore | Baltic | **TDK** | TDR | DFP | TBD | Not TD2 |
| TD19 Ceyhan–Lavera | Baltic | **WCL** | — | WDA* | TBD | *WDA daily on ICE list; confirm live |
| TD34 GoO–China | Baltic | **T34** | — | — | 1,000 t? | Listed **2026-10-05**. Gulf of Oman→China (outside Hormuz). No mini/balmo yet. See notebook `03_td34_vs_td3c` |
| TD28 W Canada–China 80kt | Baltic | **FBX** | — | — | TBD | |
| TC2 NWE–USAC MR | Baltic | **WNS** | WNT | DFS | TBD | Old monthly `WNU` |
| TC14 USGC–Cont MR | Baltic | **WHK** | WNW | DFY | 1,000 / 100 t | Old monthly `WCN`. Spec matches ICE site |
| TC6 Skikda–Lavera | Baltic | **WSN** | WNZ | DFU | TBD | Old monthly `WSL` |
| TC7 Spore–E Aus MR | Baltic | **TC7** | TC8 | — | TBD | |
| TC12 WCI–Japan | Baltic | **TCN** | TCK | DFX | 1,000 t | |
| TC15 Med–Far East | Baltic | **TCM** | TCL | — | TBD | |
| TC17 AG–E Africa | Baltic | **JFF** | TCX | — | TBD | |
| TC18 USG–Brazil | Baltic | **WFB** | TCW | — | TBD | |
| TC20 MEG–UKC | Baltic | **WAL** | WAM | — | TBD | |
| TC23 ARA–UKC | Baltic | **WFL** | WFM | — | TBD | |
| TC11 SK–Singapore | Baltic | **WAK** | — | — | TBD | No volume in sample |
| TC5 AG–Japan | Platts | **WMJ** | WNX | DFT | TBD | Clean Platts, not Baltic TC5 |
| Platts dirty USGC–UKC Aframax | Platts | **WDF** | DUR | DFC | 1,000 t | Options `WDF`. Ex-ETS twin **WDE** |
| Platts dirty USGC–China | Platts | — | DUS | DFD | | |
| Platts dirty USGC–UKC VLCC | Platts | **WHH** | — | WHI | | |
| Platts dirty PG–China | Platts | **WPC** | WPB | — | | Featured on ICE list |
| Platts dirty WAF–UKC | Platts | **DFH** | DFZ | — | | |
| Platts dirty Cross-UKC | Platts | **JFG** | WFK | WFJ | | |
| Platts dirty Guyana–UKC | Platts | **DGU** | DGW | — | | New 2026 |
| Platts dirty Vancouver–China | Platts | **TVC** | TVB | — | | |
| Platts dirty Vancouver–USWC Aframax | Platts | **TVA** | — | — | | |
| Platts clean TC2-like UKC–USAC | Platts | **WNE** | WNB | — | | Featured |
| Platts clean TC14-like USGC–UKC | Platts | **WGC** | WGB | — | | Featured |
| Platts clean Cross-Med | Platts | **WCX** | WCY | — | | |
| Platts clean AG–Japan | Platts | **TCY** / **T75** (75kt) | T7B | — | | |

\*Not re-checked as live in the monthly extract.

### Not found as a live ICE FFA
- **TD6** (CPC–Med), **TD2** (MEG–Singapore), **TD3** AG–Japan (`WGJ` died 2017).
- Baltic **spot/index** in `ICE.MFT.MARKERS_AND_INDICES`: no hits. Daily `DFN` (etc.) is a **daily future**, not a free Baltic print — still useful as a $/t proxy for the index day.

## Options
Live: **TDL** and **WDF** average-price options. Historical: WSL, WGJ, WNU. ICE list also shows some LPG options (out of tanker core).

## Liquidity (max daily volume / OI in history, not a 2026 snapshot)
Deepest monthlies: **TDL**, **WDF**, **WHK**, **WSN**, **WNS**, **WMJ**, **WF2**. Many Platts clean/new dirties print with 0 volume.

## Desk defaults (until Phase 1 tidy table)
Use **monthly Baltic** codes: TDL, TDC, WF2, WHK, WNS, WSN, TDK, WNC, WF5, WFW, **T34**. Convert everything to `usd_t`. Drop day-coded historical balmo products (`1A0`…, `15A`…). Filter `FILE_FLAG` once Final vs Early is documented in the tidy loader.

## TD34 note (2026-10-13)
- Product: `T34-TD34 FFA - Gulf of Oman to China (Baltic) Future`.
- Coverage in Snowflake: **2026-10-05 → 2026-10-12** (6 sessions), ~27 monthly strips.
- OI grew ~605 → ~4,737 lots (Final) in the first week; TDL stayed ~35k — **seed liquidity, not a full migration**.
- Volume can exceed TDL on individual days (e.g. 8 Oct: T34 2,157 vs TDL 930).
- Economic read: front TD3C − TD34 in $/t = observable **inside/outside Hormuz** paper gap (Ras Tanura load vs GoO).
