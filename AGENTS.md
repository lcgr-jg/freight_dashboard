# Freight analytics: agent instructions

## Mission
Build analytics, tools and reports that support trading tanker freight futures (FFAs)
and understanding tanker supply/demand, for an oil research and trading desk.
The owner (Luis Carlos) is an experienced oil analyst and data engineer (Python, Snowflake,
Prefect, Dash) who is **new to freight**. Explain freight-specific reasoning briefly when
you make a modelling choice; do not over-explain Python or SQL.

## Read before working
- `docs/01_domain_primer.md` – how tanker freight and FFAs work. Read before any modelling.
- `docs/freight_instruments.html` – newcomer HTML: Baltic vs DFN vs TDL vs TDM, crude analogy, worked examples.
- `docs/kpler_signals.html` – what each Kpler API is, the signal, economic meaning, how to defend it.
- `docs/02_project_plan.md` – what we are building and in what order.
- `docs/03_known_sources.md` – data we know or suspect exists.
- `docs/04_data_catalog.md` – what has actually been verified in Snowflake. **Source of truth for data.**
- `docs/platts_series.md` – Platts freight / bunker / arb-leg symbols (step 4).
- `docs/kpler_api_map.md` – Kpler Liquids/Freight SDK entitlements (step 5).
- `docs/06_decisions.md` and `docs/07_open_questions.md` – prior decisions and unresolved items.
- `docs/08_market_context_2026-10.md` – market state when the project started (dated; will go stale).
- `docs/09_phase0_synthesis.md` – Phase 0 exit: best sources, gaps, proposed Phase 1 scope.
- `docs/10_tonnage_supply_app.md` – Dash tonnage-supply spike (filters, map, shuttle/OFAC overlays).

## How to work
1. **Discover before building.** Never assume a table, column, unit or contract code exists.
   Verify in Snowflake, then record it in `docs/04_data_catalog.md`.
2. **Plan, then build.** For any task larger than a single function, write a short plan
   (goal, data used, approach, validation) and wait for approval.
3. **Validate against known numbers.** Use the reference values in `docs/01_domain_primer.md`
   and the Clarksons samples in `packages/clarksons_ingest/samples/` as sanity checks.
4. **Write it down.** When you learn something durable (a table's grain, a unit quirk,
   a dead end), update the catalog, decisions or open-questions doc in the same change.
   Future sessions depend on these files, not on chat history.
5. **Prefer small, testable modules** in `src/freight/`, with tests, over large notebooks.
   Notebooks are for exploration only; anything reused moves into `src/`.

## Guardrails
- **Snowflake is read-only for you**, except the sandbox schema named in `.env`
  (`SNOWFLAKE_SANDBOX_SCHEMA`). Never CREATE/ALTER/DROP/INSERT/DELETE elsewhere.
- Follow `.cursor/rules/snowflake-sql.mdc` for query cost and sampling.
- Never print, log or commit credentials. Config comes from `.env` (see `.env.example`).
- **Licensed data:** Clarksons, Platts, ICE and Baltic data are licensed. Do not send raw
  licensed data to external services or the internet, and do not publish it outside this repo.
  Flag any use of broker report data in trading signals as needing compliance sign-off.
- If a result looks surprising (rates, spreads, P&L), check units first:
  Worldscale vs $/t vs lumpsum vs TCE, flat-rate year, and $/bbl conversions.

## Stack and conventions
- Python 3.11+, pandas, snowflake-connector-python, Prefect for scheduling, Dash for apps
  (match the owner's existing Dash apps where possible), pytest.
- SQL views and discovery queries live in `sql/`; keep them idempotent.
- Dates: store UTC timestamps; report dates in Europe/London.
- Name freight routes by Baltic code (TD3C, TC14...). Keep units in column names
  (`ws`, `usd_t`, `usd_day`, `usd_bbl`).
