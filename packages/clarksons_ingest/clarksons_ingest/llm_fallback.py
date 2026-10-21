"""
Optional third tier: send lines the regex parser could not handle to Claude and get
structured JSON back. Results are written with parse_method='llm' so they can be
reviewed before being trusted. Use for the long tail of odd lines, not as the main path.
"""
import json
import os

import anthropic

SCHEMA_HINT = """Return only a JSON object with these keys (null when absent):
vessel, qty_kt, load, discharge, laycan_start (YYYY-MM-DD), laycan_end, rate_type
('WS'|'LUMPSUM'|'RNR'), ws_low, ws_high, lumpsum_usd, charterer,
status ('ON_SUBS'|'FULLY_FIXED'|'FAILED'|'ON_HOLD'|null), relet_by, open_port, open_date."""


def parse_line(raw_line: str, section: str, report_type: str, report_date: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=500,
        system=("You parse single lines from Clarksons tanker fixture reports. "
                "Abbreviations: W = Worldscale, RNR = rate not reported, S = on subs, "
                "RPTD = reported, O/O = or other vessel, FUJ = Fujairah, COGH = Cape of Good Hope. "
                "Laycans have no year; use the year nearest the report date. " + SCHEMA_HINT),
        messages=[{"role": "user", "content":
                   f"Report: {report_type} dated {report_date}\nSection: {section}\nLine: {raw_line}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    out = json.loads(text.removeprefix("```json").removesuffix("```").strip())
    out.update(raw_line=raw_line, parse_method="llm")
    return out
