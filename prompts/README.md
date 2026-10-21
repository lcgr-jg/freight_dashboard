# Prompts for Cursor agent sessions

Use one chat per task. Start discovery in **Plan mode** (or Ask mode) so the agent proposes
before it executes. Paste the prompt, then review its plan before letting it run queries.

---

## 0. Orientation (first session, no queries)
```
Read AGENTS.md and everything in docs/. Then:
1. Summarise in 10 bullets what this project is, what has been built, and what is unknown.
2. List anything in the docs that is inconsistent or unclear.
3. Propose how you will run Phase 0 discovery (docs/05_discovery_plan.md) given the tools
   you actually have in this environment (Snowflake access method, Python env, Kpler SDK).
Do not run any queries yet.
```

## 1. Discovery, steps 1–2 (estate map and keyword search)
```
Run Phase 0 steps 1 and 2 from docs/05_discovery_plan.md, following
.cursor/rules/snowflake-sql.mdc and .cursor/rules/data-discovery.mdc.
Metadata queries first; sample data only to confirm what a table is.
Write docs/estate_map.md, add candidate entries to docs/04_data_catalog.md (mark unverified
fields as TODO), save queries in sql/discovery/. Stop and summarise what you found,
what looks freight-relevant, and what you could not access.
```

## 2. Discovery, ICE FFAs
```
Run step 3 of docs/05_discovery_plan.md. Identify every tanker freight contract in the ICE
data: code, description, route, unit, tenors, coverage. Check whether index/spot values are
present. Cross-check one contract against the reference values in docs/01_domain_primer.md
(e.g. TD3C around WS 1,240 on 2026-10-05 for spot; FFA levels should be plausible relative to it).
Produce a route → contract mapping table in the catalog. Stop and summarise.
```

## 3. Discovery, Platts, Kpler, fundamentals, synthesis
```
Run steps 4–7. Then fill the usefulness matrix and answer the step 7 questions.
Propose concrete edits to docs/02_project_plan.md and update docs/07_open_questions.md.
Do not build anything yet.
```

## 3b. After Phase 0 (synthesis reviewed)
```
Phase 0 is closed in docs/09_phase0_synthesis.md. Do not re-run discovery steps 1–7 unless
I ask. Propose the first Phase 1 week-1 slice (ICE FFA table + Kpler snapshots) and wait
for approval on: (1) spot primary path A/B/C, (2) Clarksons compliance, (3) flat strategy.
```

## 4. Build a tool (template)
```
Implement tool <ID> from docs/02_project_plan.md.
First write a plan: data sources (from the catalog only), method, outputs, tests, and how
you'll validate against known values. Wait for my approval.
After approval: implement in src/freight/<module>.py with tests in tests/, add any SQL views
to sql/, and record decisions in docs/06_decisions.md.
```

## 5. End-of-session hygiene (use whenever a session found something durable)
```
Update docs/04_data_catalog.md, docs/06_decisions.md and docs/07_open_questions.md with
anything durable learned in this session. Keep entries short and factual.
```
