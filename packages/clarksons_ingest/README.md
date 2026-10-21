# clarksons_ingest

Turns the Clarksons VLCC Evening and Daily Suezmax emails into Snowflake tables:
fixtures, cargoes, Baltic prints, bunkers, crude/EUA prices and MEG decade counts.

## How it works
1. **Fetch** (`fetch_graph.py`): Microsoft Graph reads the mailbox, keeps emails from
   clarksons.com whose subject/body matches a known report, and downloads attachments.
   It asks Graph for a plain-text body so the fixed-width columns survive.
2. **Parse** (`parsers.py`): regex parsers per report.
   - VLCC: fixtures/cargoes from the email body; Baltic, bunkers, crude and
     decade counts from the PDF side panel (they are not in the body).
   - Suezmax: everything from the body; falls back to the PDF if the body yields no fixtures.
   Lines that match nothing go to `PARSE_EXCEPTIONS`, never silently dropped.
3. **Load** (`pipeline.py`): idempotent per report (delete + insert by `report_id`, in one transaction).
4. **Schedule** (`flow.py`): Prefect flow, weekdays after the evening reports land.
5. **Optional** (`llm_fallback.py`): send exception lines to Claude for structured parsing, flagged for review.

## Setup
```
pip install -r requirements.txt          # pdftotext (poppler-utils) also needed for the Suezmax PDF fallback
snowsql -f sql/ddl.sql                   # or run in a worksheet
python tests/test_parsers.py             # or: pytest tests
```
Environment variables:
`GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, REPORT_MAILBOX,
SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE,
SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA` plus `SNOWFLAKE_PASSWORD` or `SNOWFLAKE_PRIVATE_KEY_FILE`.

Backfill history once: `clarksons_ingest(lookback_days=365)`.

## The Graph permission (ask IT)
An Entra ID app registration with application permission **Mail.Read**, restricted by an
Exchange **Application Access Policy** to one mailbox. Cleanest is a shared mailbox
(e.g. freight-reports@) with an Outlook rule forwarding Clarksons emails into it, so the
app never touches your personal inbox.

If app permissions are not possible: a Power Automate flow ("When a new email arrives",
from clarksons.com) that saves the body as .txt and the PDF to SharePoint or S3, then
point the parser at those files instead of `fetch_graph.py`.

## Maintenance
- Watch `PARSE_EXCEPTIONS` and the flow's warnings. A sudden jump means Clarksons
  changed a layout: save that email body into `samples/`, add a test, fix the regex.
- `RAW_EMAILS.BODY_TEXT` keeps every original, so you can re-parse all history after a fix.
- Vessel names are free text. Join to Kpler `Vessels` for IMO before linking to AIS data.

## Views (sql/ddl.sql)
`V_BALTIC_DAILY`, `V_FIXTURE_LIFECYCLE` (first seen, latest status, days on subs),
`V_FAIL_RATE_WEEKLY`, `V_MEG_SHIPS_PER_CARGO`, `V_BUNKER_SPREADS`.
