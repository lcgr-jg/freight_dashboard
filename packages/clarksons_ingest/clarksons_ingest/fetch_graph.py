"""
Pull Clarksons report emails from Outlook / Exchange Online via Microsoft Graph.

Needs an Entra ID (Azure AD) app registration with the *application* permission
Mail.Read, ideally scoped by IT to your mailbox (or a shared mailbox the reports
are forwarded to) with an Application Access Policy. Credentials come from env vars.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"

# How to recognise each report. Subject first, body as a fallback.
REPORT_RULES = {
    "VLCC_EVENING": {"subject": r"VLCC EVENING REPORT", "body": r"VLCC EVENING REPORT"},
    "SUEZMAX_DAILY": {"subject": r"SUEZMAX", "body": r"CLARKSONS DAILY SUEZMAX REPORT"},
}
SENDER_DOMAINS = ("clarksons.com",)


@dataclass
class ReportEmail:
    message_id: str
    internet_message_id: str
    received_at: datetime
    subject: str
    sender: str
    report_type: str
    body_text: str
    attachments: dict[str, bytes]          # filename -> bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body_text.encode()).hexdigest()


def _token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=os.environ["GRAPH_CLIENT_ID"],
        client_credential=os.environ["GRAPH_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{os.environ['GRAPH_TENANT_ID']}",
    )
    tok = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in tok:
        raise RuntimeError(f"Graph auth failed: {tok.get('error_description')}")
    return tok["access_token"]


def classify(subject: str, body: str) -> str | None:
    for rtype, rule in REPORT_RULES.items():
        if re.search(rule["subject"], subject or "", re.I) or re.search(rule["body"], body or "", re.I):
            return rtype
    return None


def fetch_reports(mailbox: str | None = None, lookback_days: int = 3,
                  with_attachments: bool = True) -> list[ReportEmail]:
    """Return Clarksons report emails received in the lookback window."""
    mailbox = mailbox or os.environ["REPORT_MAILBOX"]
    headers = {
        "Authorization": f"Bearer {_token()}",
        # Ask Graph for a plain-text body: keeps the fixed-width columns intact.
        "Prefer": 'outlook.body-content-type="text"',
    }
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"{GRAPH}/users/{mailbox}/messages"
           f"?$filter=receivedDateTime ge {since}"
           f"&$select=id,internetMessageId,subject,from,receivedDateTime,body,hasAttachments&$top=100")

    out: list[ReportEmail] = []
    while url:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        payload = r.json()
        for m in payload.get("value", []):
            sender = (m.get("from") or {}).get("emailAddress", {}).get("address", "").lower()
            if not sender.endswith(SENDER_DOMAINS):
                continue
            body = (m.get("body") or {}).get("content", "")
            rtype = classify(m.get("subject", ""), body)
            if not rtype:
                continue
            atts = _attachments(mailbox, m["id"], headers) if (with_attachments and m.get("hasAttachments")) else {}
            out.append(ReportEmail(
                message_id=m["id"], internet_message_id=m.get("internetMessageId", m["id"]),
                received_at=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")),
                subject=m.get("subject", ""), sender=sender, report_type=rtype,
                body_text=body, attachments=atts))
        url = payload.get("@odata.nextLink")
    return out


def _attachments(mailbox: str, msg_id: str, headers: dict) -> dict[str, bytes]:
    r = requests.get(f"{GRAPH}/users/{mailbox}/messages/{msg_id}/attachments",
                     headers={"Authorization": headers["Authorization"]}, timeout=60)
    r.raise_for_status()
    files = {}
    for a in r.json().get("value", []):
        if a.get("@odata.type") == "#microsoft.graph.fileAttachment" and a.get("contentBytes"):
            files[a["name"]] = base64.b64decode(a["contentBytes"])
    return files
