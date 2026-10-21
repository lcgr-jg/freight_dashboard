# Platts series (Phase 0 step 4)

Verified: 2026-10-06. Access: `desk_core` `platts_spot` / `JG_GENERAL`.
Tables: `SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA` + `PRICEDATA`.
Runners: `sql/discovery/run_step4_platts.py`, `run_step4_platts_followup.py`.
Raw (gitignored): `sql/discovery/_runs/06_platts_*.csv`.

Licensed: keep values on-box. This file lists **symbols and how to read them**, not a dump of history.

## How to query

- Join `REF_DATA_MARKETDATA` → `PRICEDATA` on `SYMBOL`.
- Grain: `SYMBOL` × `ASSESSDATE` × `BATE`.
- **Do not assume `BATE='c'`.** Product/crude closes are usually `c`. Many tanker route prints (especially older `TDA*` / `PFA*` / `TCA*` codes) are **`BATE='u'`** only. A few newer tanker codes (`TDUCF00`, `TCCSA00`, `TDAUL00`, …) use `c`. Read whatever bate exists for that symbol; `window_trades_report`’s `BATE='c'` filter will miss most dirty/clean routes.
- Daily vs average: `ASSESSMENT_FREQUENCY='Daily (weekday)'` and suffix `00` (spot). `03` = MAvg. Skip `MAvg` / `WAvg` / `cargo size` / `M2M Financial MoNN`.
- Filter: `COMMODITY='Shipping'`, `ACTIVE='Active - Public'`. Drop `Carbon Accounted` / `Carbon Emission` (`MDC` `TDZ`/`TCZ`) unless you explicitly want EU ETS adders.
- Units: `UOM` `WSC` (Worldscale points), `MT` ($/mt), `LSM` (lumpsum $mn). Pair WS + $/mt on the same route when both exist.
- Platts **does not** use Baltic codes as symbols (`TD3C` is not a Platts `SYMBOL`). Map by description / vessel / cargo size. ICE Platts-settled FFAs (WDF, WPC, …) should be compared to the Platts route below, not to Baltic.

`MDV2.FC` has **no** freight-named tables/columns in this pass. eWindow has **bunker** markets, not tanker FFAs (see catalog).

## Freight — recommended daily routes

Prefer **Benchmark** flag when Platts sets it. `$/mt` is the ICE-comparable unit.

| Use (ICE analog) | $/mt | WS / lumpsum | Description (daily) |
|---|---|---|---|
| TD3C / WPC (MEG–China VLCC 270kt) | **AASLC00** (Benchmark) | AASLB00 | Dirty Arab Gulf–China 270kt |
| TD3C-like Far East 270kt | TDAAB00 | PFAOC00 | Dirty Arab Gulf–Far East 270kt |
| TD15 (WAF–Far East VLCC 260kt) | TDACN00 | PFAOM00 | Dirty West Africa–Far East 260kt |
| TD22 (USGC–China VLCC 270kt) | **TDUCA00** (Benchmark) | TDUCB00 lumpsum | Dirty USGC–China VLCC 270kt |
| TD20 / DFH (WAF–UKC Suezmax 130kt) | **TDACR00** (Benchmark) | PFAIC10 | Dirty West Africa–UKC 130kt |
| Platts WAF–UKC VLCC | TDACS00 | PFAON00 | Dirty West Africa–UKC 260kt |
| WDF (USGC–UKC Aframax 70kt) | **TDUCF00** (Benchmark) | TDUCG00 | Dirty USGC–UK Continent Aframax 70kt |
| WHH-like USGC–UKC VLCC | **DTGCB00** (Benchmark) | DTGCA00 lumpsum | Dirty Tanker USGC–UKC VLCC 270kt |
| TD25-ish / Cross-UKC | **TDACD00** (Benchmark) | PFAKD10 | Dirty UKC–UKC 80kt Aframax |
| TD6 (Black Sea–Med 80 / 135kt) | TDADO00 / TDADL00 | TDADT00 / TDADQ00 | Dirty Black Sea–Med |
| TD19 (Ceyhan–Med 80kt) | TDABL00 | PFAJP10 | Dirty Ceyhan–Med 80kt |
| Brazil–China VLCC | TDAUL00 | TDAUK00 | Dirty Brazil–China VLCC 260kt |
| DGU (Guyana–UKC Suezmax) | **DGUMW00** (Benchmark) | DGUMU00 | Dirty Guyana–UK Continent 130kt |
| TVC (Vancouver–China Aframax) | **TVBCB00** (Benchmark) | TVBCA00 lumpsum | Dirty Vancouver–China 80kt |
| TD8-like FO AG–Singapore 80kt | AAPOQ00 / AAPOO00 | — | Dirty AG–Singapore FO 380/180 80kt |
| TC2 / WNE (UKC–USAC MR 37kt) | **TCABX00** (Benchmark) | PFAMA00 | Clean UKC–USAC 37kt MR |
| TC14 / WGC (USGC–UKC MR 38kt) | **TCAFI00** (Benchmark) | TCAFJ00 | Clean USGC–UKC 38kt MR |
| TC5 / WMJ (AG–Japan LR) | **TCAAI00** / **TCAAJ00** (Benchmark) | PFAEY10 / PFAMT00 | Clean AG–Japan 55kt LR1 / 75kt LR2 |
| TC6 / WCX (Med–Med MR 30kt) | **TCAAY00** (Benchmark) | PFADB10 | Clean Med–Med 30kt MR |
| TC7 (Singapore–E Aus MR) | TCCSA00 (35kt) / AAJPV00 (30kt) | TCCSB00 / AAJLP00 | Clean Singapore–Australia |
| TC17 (AG–E Africa MR) | TCAAE00 | PFAMS00 | Clean AG–East Africa 35kt |
| TC18 (USGC–Brazil) | TCAFR00 / TCBRA00 | TCAFQ00 / TCBRB00 | Clean USGC–Brazil 38kt MR / 60kt |
| TC20 (AG–UKC) | TCADB00 / TCADR00 / TCADW00 | lumpsum PFABP10 / PFAFA10 / PFANT00 | Clean AG–UKC 40/65/90kt |

Universe size (active daily, not carbon, UOM WSC/MT/LSM): **477** symbols (`06_platts_tanker_daily_core.csv`). Full dirty/clean inventory including MAvg: **1979**.

Sanity (on-box, 6 Oct 2026 unless noted): AASLC00 **251.56 $/t**, AASLB00 **WS 1,210**. ICE DFN 5 Oct was **250.73 $/t**, Baltic primer WS **1,240.63** — same order of magnitude; **not** proof Platts = Baltic.

## Bunkers — physical delivered (not M2M strips)

Prefer `Marine Fuel 0.5%` (VLSFO) + HSFO 380 + MGO 0.1%. Ignore `QB*`/`FM*` M2M Financial MoNN (hundreds of curve points).

| Grade | Singapore | Rotterdam | Fujairah | Houston |
|---|---|---|---|---|
| VLSFO 0.5% delivered | **MFSPD00** | **MFRDD00** | **MFFJD00** | **MFHOD00** |
| VLSFO 0.5% ex-wharf | MFSPE00 | — | MFFJE00 | MFHOE00 |
| HSFO 380 delivered | PUAFT00 | **PUAFN00** / B3RTM00 | **B3FJR00** / PUAXP00 | **AAGPD00** / B3HOU00 |
| HSFO 380 ex-wharf | AAFER00 / B3SIN00 | — | AAYBF00 | PUAES00 |
| MGO 0.1% delivered | AAXYO00 | (see ARA barge `LGARD00`) | AAXYP00 | LGHOU00 |

FOB cargo / MOPS strips exist (`AMFFA00` Fujairah VLSFO cargo, `AAPJW00` FO 380 MOPS) — use for arb, not vessel TCE bunkers.

eWindow markets with bunker liquidity (not tanker FFAs): `EU Bunker`, `US Bunkers`, `ASIA Bunker SG`, `ASIA Bunker North`, `Asia Bunker AG`.

## Arb legs — crude (cash / front-month markers)

Avoid `Financial MoNN` / M2M / netbacks unless you want a crack board.

| Leg | Symbol | Notes |
|---|---|---|
| Dated Brent | **PCAAS00** | Spot FOB, Benchmark |
| Dubai front month | **PCAAT00** | Dubai Mo01 (NextGen MOC), Forward, Benchmark |
| Oman Blend front month | **PCABS00** | Oman Blend Mo01 (NextGen MOC) |
| Murban | **AMIFA00** | Murban IFAD FOB Fujairah (spot-style) |
| WTI Houston (MEH) | **AAYRG00** | `WTI MEH` spot differential (FIP USGC) |
| Mars | **AAMBR00** / AAQAX00 | Mars Mo01 / Mars 16:30 London Mo01 |
| WTI Midland DES Asia | WTMYA00 / WTMSA00 | Yeosu / Singapore DES — landed crude, not Houston pipe |

Dubai/Oman **cash vs OSP** and `(Dubai+Oman)/2` OSPs are plentiful; do not use OSP for a freight arb without an explicit OSP model.

## Arb legs — products (spot, not swaps)

| Hub | Diesel / gasoil | Gasoline | Naphtha |
|---|---|---|---|
| NWE / ARA | **AAVBG00** ULSD 10ppmS CIF NWE; **AMOPM00** ULSD FOB ARA barge MOPL (desk-standard) | **AAXFQ00** Gasoline 10ppmS CIF NWE | **PAAAL00** Naphtha CIF NWE |
| USGC | **AAXRW00** ULSD USGC Export $/mt; ABTGY00 pipeline $/b | Unl 87 waterborne **ABMFH00** | LSR naphtha DAP barge **AAXQM00** |
| AG | **AAIDT00** Gasoil 10ppm FOB AG; AASGJ00 50ppm | **AAICY00** 95 RON FOB Jebel Ali | **PAAAA00** Naphtha FOB AG |
| Singapore / Japan | 10ppm FOB Singapore cargo **not locked** this pass (names are “Spore”/MOC, not `FOB Singapore`); Japan naphtha **PAAAD00** C+F | **PGACW00** Unl 91-92 C+F Japan | same Japan cargo |

## Traps

- `%freight%` and `MDC ILIKE '%FRE%'` pull bunker mirrors, carbon, and thousands of non-route rows (`Shipping`+`Aframax`+`MT` profile was 9k+ because FRE tags leak).
- `Inactive` contains the substring `Active` — match `ACTIVE = 'Active - Public'` exactly.
- Baltic route codes inside Platts **symbols** are false positives (step 2).
- Platts tanker ≠ Baltic settlement until we overlay histories (open question). Use Platts for Platts-settled ICE FFAs and for G/C/report bunkers+assessments.
