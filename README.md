# freight-analytics

Tanker freight and FFA analytics for the desk. Agent-ready: Cursor reads `AGENTS.md`
automatically and the scoped rules in `.cursor/rules/`.

- `AGENTS.md` – always-on agent instructions (mission, workflow, guardrails)
- `.cursor/rules/` – scoped rules: Snowflake querying, freight units, data discovery
- `docs/` – domain primer, **HTML instrument guide** (`docs/freight_instruments.html`), **Kpler signals** (`docs/kpler_signals.html`), ICE FFA map, Platts series, Kpler API map, **Phase 0 synthesis** (`docs/09_phase0_synthesis.md`), plan, sources, data catalog, decisions, open questions
- `prompts/README.md` – kickoff and follow-up prompts, in order
- `packages/clarksons_ingest/` – Clarksons email parser → Snowflake (tested on samples)
- `sql/discovery/` – discovery queries; `src/freight/` – tools; `notebooks/` – exploration only

Start: copy `.env.example` to `.env`, open the folder in Cursor, run prompt 0 from `prompts/README.md`.
