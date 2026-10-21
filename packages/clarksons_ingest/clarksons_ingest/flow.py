"""
Prefect flow: fetch Clarksons emails -> parse -> load to Snowflake.

Deploy on a cron after the evening reports land (they arrive ~17:30 London), with a
morning re-run to catch late emails. Re-runs are safe: loads are idempotent per report.

    prefect deploy clarksons_ingest/flow.py:clarksons_ingest -n daily \
        --cron "45 18 * * 1-5" --timezone Europe/London
"""
from prefect import flow, get_run_logger, task

from .fetch_graph import fetch_reports
from .pipeline import load, parse_email, snowflake_conn


@task(retries=3, retry_delay_seconds=120)
def fetch(lookback_days: int):
    return fetch_reports(lookback_days=lookback_days)


@task
def parse_and_load(email, conn):
    header, frames = parse_email(email)
    load(header, frames, conn)
    return header


@flow(name="clarksons-ingest")
def clarksons_ingest(lookback_days: int = 3):
    log = get_run_logger()
    emails = fetch(lookback_days)
    log.info("Fetched %d Clarksons report emails", len(emails))
    conn = snowflake_conn()
    try:
        for e in emails:
            h = parse_and_load(e, conn)
            msg = "%s %s: %d fixtures, %d cargoes, %d unparsed"
            args = (h["report_type"], h["report_date"], h["n_fixtures"], h["n_cargoes"], h["n_unparsed"])
            (log.warning if h["n_unparsed"] or not h["n_fixtures"] else log.info)(msg, *args)
    finally:
        conn.close()


if __name__ == "__main__":
    clarksons_ingest()
