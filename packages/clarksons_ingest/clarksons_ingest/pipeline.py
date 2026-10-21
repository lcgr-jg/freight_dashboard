"""
Email -> parsed DataFrames -> Snowflake.

Loading is idempotent: each email gets a deterministic report_id, and rows for that
report_id are deleted before insert, so re-running a day (or re-parsing history after
a parser fix) never duplicates data.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from .parsers import ParseResult, parse_suezmax, parse_vlcc_body, parse_vlcc_pdf_panel

PARSER_VERSION = "0.1.0"
LONDON = ZoneInfo("Europe/London")

TABLES = {                      # DataFrame key -> Snowflake table
    "fixtures": "FIXTURES",
    "cargoes": "CARGOES",
    "baltic": "BALTIC_ASSESSMENTS",
    "bunkers": "BUNKER_PRICES",
    "prices": "MARKET_PRICES",
    "decade_counts": "DECADE_COUNTS",
    "unparsed": "PARSE_EXCEPTIONS",
}


def report_id(report_type: str, report_date: date, internet_message_id: str) -> str:
    return hashlib.sha1(f"{report_type}|{report_date}|{internet_message_id}".encode()).hexdigest()[:16]


def parse_email(email) -> tuple[dict, dict[str, pd.DataFrame]]:
    """Accepts a fetch_graph.ReportEmail (or anything with the same attributes)."""
    rdate = email.received_at.astimezone(LONDON).date()

    if email.report_type == "VLCC_EVENING":
        res = parse_vlcc_body(email.body_text, rdate)
        pdf = next((b for n, b in email.attachments.items() if n.lower().endswith(".pdf")), None)
        if pdf:
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(pdf); f.flush()
                panel = parse_vlcc_pdf_panel(f.name, rdate)
            _merge(res, panel)
    elif email.report_type == "SUEZMAX_DAILY":
        res = parse_suezmax(email.body_text)
        if not res.fixtures and email.attachments:         # body unreadable -> try the PDF
            res = _suezmax_from_pdf(email.attachments) or res
        rdate = res.meta["report_date"]
    else:
        raise ValueError(email.report_type)

    rid = report_id(email.report_type, rdate, email.internet_message_id)
    res.meta.update(report_id=rid, report_date=rdate)
    frames = res.frames()
    for df in frames.values():
        df["report_id"] = rid
        df["parser_version"] = PARSER_VERSION

    header = {
        "report_id": rid, "report_type": email.report_type, "report_date": rdate,
        "received_at": email.received_at, "subject": email.subject, "sender": email.sender,
        "internet_message_id": email.internet_message_id, "body_sha256": email.sha256,
        "body_text": email.body_text, "attachment_names": ",".join(email.attachments),
        "headline": res.meta.get("headline"), "turkish_straits": res.meta.get("turkish_straits"),
        "baltic_date": res.meta.get("baltic_date"), "parser_version": PARSER_VERSION,
        "n_fixtures": len(res.fixtures), "n_cargoes": len(res.cargoes), "n_unparsed": len(res.unparsed),
    }
    return header, frames


def _merge(a: ParseResult, b: ParseResult) -> None:
    for k in ("baltic", "bunkers", "prices", "decade_counts", "unparsed"):
        getattr(a, k).extend(getattr(b, k))
    a.meta.update({k: v for k, v in b.meta.items() if k not in a.meta})


def _suezmax_from_pdf(attachments: dict[str, bytes]) -> ParseResult | None:
    import subprocess
    pdf = next((b for n, b in attachments.items() if n.lower().endswith(".pdf")), None)
    if not pdf:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf); f.flush()
        txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    return parse_suezmax(txt)


# ----------------------------------------------------------------------------- Snowflake
def snowflake_conn():
    import snowflake.connector
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR", "snowflake"),
        password=os.environ.get("SNOWFLAKE_PASSWORD"),
        private_key_file=os.environ.get("SNOWFLAKE_PRIVATE_KEY_FILE"),
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"], role=os.environ.get("SNOWFLAKE_ROLE"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "RESEARCH"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "FREIGHT"),
    )


def load(header: dict, frames: dict[str, pd.DataFrame], conn) -> None:
    from snowflake.connector.pandas_tools import write_pandas
    rid = header["report_id"]
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        for table in ["RAW_EMAILS", *TABLES.values()]:
            cur.execute(f"DELETE FROM {table} WHERE REPORT_ID = %s", (rid,))
        write_pandas(conn, pd.DataFrame([header]).rename(columns=str.upper), "RAW_EMAILS",
                     auto_create_table=False, quote_identifiers=False)
        for key, table in TABLES.items():
            df = frames[key]
            if len(df):
                write_pandas(conn, df.rename(columns=str.upper), table,
                             auto_create_table=False, quote_identifiers=False)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.close()
