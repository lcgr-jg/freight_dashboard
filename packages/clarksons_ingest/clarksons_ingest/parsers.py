"""
Parsers for Clarksons tanker emails.

Two report types are handled:
  - VLCC Evening Report:  fixtures/cargoes from the email body (fixed-width text)
                          + side panel (bunkers, Baltic, crude, decade counts) from the PDF
  - Daily Suezmax Report: everything is in the body (or the PDF, same layout)

Design: deterministic regex parsing first. Any line inside a fixtures/cargoes
section that matches no pattern is returned in `unparsed` rather than dropped,
so it can be reviewed or sent to an LLM fallback (see llm_fallback.py).
Every parsed row keeps `raw_line` so you can always audit back to the source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), start=1)}

DASH = r"[-\u2013\u2014]"            # hyphen, en dash, em dash all appear in these reports
SPLIT = re.compile(r"\s{2,}|\t")      # fields in fixed-width lines are separated by 2+ spaces


# ----------------------------------------------------------------------------- helpers
def infer_year(month: int, report_date: date) -> int:
    """Laycans carry no year. Pick the year that puts the month nearest the report date."""
    y = report_date.year
    if month - report_date.month > 6:
        return y - 1
    if report_date.month - month > 6:
        return y + 1
    return y


def parse_laycan(text: str, report_date: date) -> tuple[date | None, date | None]:
    """'21-23 OCT', '31 OCT-01 NOV', '21 OCT', 'ELY NOV', 'END OCT', 'MID NOV'."""
    t = text.strip().upper()
    m = re.fullmatch(rf"(\d{{1,2}})\s*([A-Z]{{3}})?\s*{DASH}\s*(\d{{1,2}})\s*([A-Z]{{3}})", t)
    if m:
        d1, m1, d2, m2 = m.groups()
        m1 = m1 or m2
        mo1, mo2 = MONTHS.get(m1), MONTHS.get(m2)
        if mo1 and mo2:
            return (date(infer_year(mo1, report_date), mo1, int(d1)),
                    date(infer_year(mo2, report_date), mo2, int(d2)))
    m = re.fullmatch(r"(\d{1,2})\s*([A-Z]{3})", t)
    if m and m.group(2) in MONTHS:
        mo = MONTHS[m.group(2)]
        d = date(infer_year(mo, report_date), mo, int(m.group(1)))
        return d, d
    m = re.fullmatch(r"(ELY|EARLY|MID|END|LATE)\s+([A-Z]{3})", t)
    if m and m.group(2) in MONTHS:
        mo = MONTHS[m.group(2)]
        y = infer_year(mo, report_date)
        lo, hi = {"ELY": (1, 10), "EARLY": (1, 10), "MID": (11, 20),
                  "END": (21, 28), "LATE": (21, 28)}[m.group(1)]
        return date(y, mo, lo), date(y, mo, hi)
    return None, None


LAYCAN_RE = re.compile(
    rf"\d{{1,2}}\s*(?:[A-Z]{{3}})?\s*{DASH}\s*\d{{1,2}}\s*[A-Z]{{3}}|\d{{1,2}}\s*[A-Z]{{3}}|(?:ELY|EARLY|MID|END|LATE)\s+[A-Z]{{3}}")


def parse_rate(text: str) -> dict:
    """'W780-W830', 'W665-W685-W695', '<W800', 'W800+', '$22M', '$4.5M', 'RNR'."""
    t = text.strip().upper()
    out = {"rate_raw": text.strip() or None, "rate_type": None, "ws_low": None,
           "ws_high": None, "lumpsum_usd": None, "rate_qualifier": None}
    if not t:
        return out
    if t in ("RNR", "PNR", "OWN PROG", "COA"):
        out["rate_type"] = t
        return out
    m = re.search(r"\$\s*([\d.]+)\s*(M|K)?", t)
    if m:
        mult = {"M": 1e6, "K": 1e3}.get(m.group(2) or "", 1)
        out.update(rate_type="LUMPSUM", lumpsum_usd=float(m.group(1)) * mult)
        return out
    ws = [float(x) for x in re.findall(r"W(?:S)?\s*([\d.]+)", t)]
    if ws:
        out.update(rate_type="WS", ws_low=min(ws), ws_high=max(ws))
        if t.startswith("<"):
            out["rate_qualifier"] = "<"
        elif t.endswith("+"):
            out["rate_qualifier"] = "+"
    return out


STATUS_PATTERNS = [            # order matters: most specific first
    ("FAILED", r"\bFAILED\b|\bFLD\b"),
    ("FULLY_FIXED", r"FULLY FIXED|\bFXD\b|\bFF\b"),
    ("ON_HOLD", r"ON HOLD"),
    ("ON_SUBS", r"ON SUBS|^S\b"),
    ("QUOTED", r"\bQUOTED\b"),
]


def parse_status(text: str) -> dict:
    t = (text or "").upper().strip().lstrip("-").strip()
    status = next((s for s, p in STATUS_PATTERNS if re.search(p, t)), None)
    relet = re.search(r"([A-Z][A-Z&. ]*?)\s+RELET", t)
    alt = re.search(r"O/O\s+([A-Z0-9 .]+?)(?:,|$)", t)
    return {
        "status": status,
        "reported": bool(re.search(r"\bRPTD\b", t)),   # heard in market, not confirmed by the broker
        "relet_by": relet.group(1).strip() if relet else None,
        "or_other_vessel": alt.group(1).strip() if alt else None,
        "status_raw": t or None,
    }


def split_vessel(name: str) -> tuple[str, str | None]:
    """'SERIFOS (09)' -> ('SERIFOS', '09'); build year two-digit."""
    m = re.match(r"^(.*?)\s*\((\d{2})\)\s*$", name.strip())
    return (m.group(1).strip(), m.group(2)) if m else (name.strip(), None)


# 'SILVERSTONE (FUJ 20/10) ON SUBS, RPTD W800+ GOO/EAST'
# 'TENJUN (08 - BRAZIL 28/10) RPTD ON SUBS'
# 'WHITE MOON   (HUELVA 07 OCT)   - ON SUBS, MOEVE RELET'
POSITION_LINE = re.compile(
    r"^(?P<vessel>[A-Z0-9][A-Z0-9 .'/-]*?)\s*\((?:(?P<built>\d{2})\s*-\s*)?"
    r"(?P<pos>[A-Z .'-]+?)\s+(?P<open>\d{1,2}[/ ](?:\d{1,2}|[A-Z]{3}))\)\s*(?P<rest>.*)$")


def parse_open_date(s: str, report_date: date) -> date | None:
    s = s.strip().upper()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        mo = int(m.group(2))
        return date(infer_year(mo, report_date), mo, int(m.group(1)))
    m = re.fullmatch(r"(\d{1,2}) ([A-Z]{3})", s)
    if m and m.group(2) in MONTHS:
        mo = MONTHS[m.group(2)]
        return date(infer_year(mo, report_date), mo, int(m.group(1)))
    return None


@dataclass
class ParseResult:
    meta: dict = field(default_factory=dict)
    fixtures: list[dict] = field(default_factory=list)
    cargoes: list[dict] = field(default_factory=list)
    baltic: list[dict] = field(default_factory=list)
    bunkers: list[dict] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    decade_counts: list[dict] = field(default_factory=list)
    unparsed: list[dict] = field(default_factory=list)

    def frames(self) -> dict[str, pd.DataFrame]:
        """One DataFrame per table, always with the same columns (matches ddl.sql)."""
        out = {}
        for k, cols in COLUMNS.items():
            df = pd.DataFrame(getattr(self, k)).reindex(columns=cols)
            df["report_type"] = self.meta.get("report_type")
            df["report_date"] = self.meta.get("report_date")
            out[k] = df.astype(object).where(df.notna(), None)
        return out


COLUMNS = {
    "fixtures": ["section", "block", "line_no", "format", "vessel", "built_yy", "qty_kt", "cargo_grade",
                 "load", "discharge", "laycan_raw", "laycan_start", "laycan_end",
                 "rate_raw", "rate_type", "ws_low", "ws_high", "lumpsum_usd", "rate_qualifier",
                 "charterer", "status", "reported", "relet_by", "or_other_vessel", "status_raw",
                 "open_port", "open_date", "raw_line"],
    "cargoes": ["section", "line_no", "charterer", "qty_kt", "load", "discharge", "laycan_raw",
                "laycan_start", "laycan_end", "notes", "reported", "replaces_vessel", "raw_line"],
    "baltic": ["route", "assessment_date", "qty_kt", "value", "unit", "change", "tce_usd_day", "raw_line"],
    "bunkers": ["port", "grade", "price_usd_mt", "change", "raw_line"],
    "prices": ["instrument", "value", "change", "unit", "raw_line"],
    "decade_counts": ["metric", "month", "decade", "value", "raw_line"],
    "unparsed": ["section", "block", "line_no", "raw_line"],
}


def _clean_lines(text: str) -> list[str]:
    return [ln.replace("\f", "").rstrip() for ln in text.replace("\r", "").split("\n")]


def _position_row(line, m, report_date, section, block, lineno):
    vessel, built = m.group("vessel").strip(), m.group("built")
    alt = None
    if " O/O " in vessel:                       # 'HOUSTON VOYAGER O/O EL SEGUNDO VOYAGER'
        vessel, alt = [x.strip() for x in vessel.split(" O/O ", 1)]
    st = parse_status(m.group("rest"))
    rate = parse_rate(" ".join(re.findall(r"<?W\d+\+?|\$[\d.]+M", m.group("rest"))))
    return {"section": section, "block": block, "line_no": lineno, "format": "position",
            "vessel": vessel, "built_yy": built, "open_port": m.group("pos").strip(),
            "open_date": parse_open_date(m.group("open"), report_date),
            **rate, **st, "or_other_vessel": alt or st["or_other_vessel"], "raw_line": line.strip()}


# ----------------------------------------------------------------------------- VLCC
VLCC_SECTIONS = {"MEG/WEST-INDIA-RED SEA", "MEG/EAST", "ATLANTIC"}
VLCC_BLOCKS = {"FIXTURES", "FAILED", "CARGOES"}


def parse_vlcc_body(text: str, report_date: date) -> ParseResult:
    """Email body of the VLCC evening report (fixtures, failed, cargoes)."""
    res = ParseResult(meta={"report_type": "VLCC_EVENING", "report_date": report_date})
    block = section = None
    for i, raw in enumerate(_clean_lines(text)):
        line = raw.strip()
        if not line or set(line) <= set("=-") or line.startswith(("CLARKSONS", "LONDON", "VLCC EVENING")):
            continue
        if line in VLCC_BLOCKS:
            block, section = line, None
            continue
        if line in VLCC_SECTIONS:
            section = line
            continue
        if line.startswith("BEST REGARDS"):
            break
        if block is None or section is None or line == "NOTHING FRESH TO REPORT":
            continue

        if block == "CARGOES":
            parts = SPLIT.split(line)
            if len(parts) >= 4:
                lc = next((p for p in parts if LAYCAN_RE.fullmatch(p.strip())), None)
                ls, le = parse_laycan(lc, report_date) if lc else (None, None)
                res.cargoes.append({"section": section, "line_no": i, "charterer": parts[0],
                                    "qty_kt": _num(parts[1]), "load": parts[2] if len(parts) > 2 else None,
                                    "discharge": parts[3] if len(parts) > 3 else None,
                                    "laycan_raw": lc, "laycan_start": ls, "laycan_end": le,
                                    "notes": " ".join(parts[5:]) or None, "raw_line": line})
            else:
                res.unparsed.append({"section": section, "block": block, "line_no": i, "raw_line": line})
            continue

        m = POSITION_LINE.match(line)
        if m:
            row = _position_row(line, m, report_date, section, block, i)
            if block == "FAILED":
                row["status"] = "FAILED"
            res.fixtures.append(row)
            continue

        parts = SPLIT.split(line)
        # VESSEL | QTY | LOAD | DISCHARGE | LAYCAN | RATE | CHARTERER | STATUS
        if len(parts) >= 7 and re.fullmatch(r"\d{2,3}", parts[1]):
            vessel, built = split_vessel(parts[0])
            ls, le = parse_laycan(parts[4], report_date)
            st = parse_status(" ".join(parts[7:]))
            if block == "FAILED":
                st["status"] = "FAILED"
            res.fixtures.append({"section": section, "block": block, "line_no": i, "format": "full",
                                 "vessel": vessel, "built_yy": built, "qty_kt": int(parts[1]),
                                 "load": parts[2], "discharge": parts[3], "laycan_raw": parts[4],
                                 "laycan_start": ls, "laycan_end": le, **parse_rate(parts[5]),
                                 "charterer": parts[6], **st, "raw_line": line})
        else:
            res.unparsed.append({"section": section, "block": block, "line_no": i, "raw_line": line})
    return res


def parse_vlcc_pdf_panel(pdf_path: str, report_date: date) -> ParseResult:
    """Left-hand panel of the VLCC evening PDF: bunkers, Baltic, crude, MEG cargo and ship counts.
    The email body does not contain these, so the PDF attachment is the source."""
    import pdfplumber
    res = ParseResult(meta={"report_type": "VLCC_EVENING", "report_date": report_date})
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        anchor = next(w for w in page.extract_words() if w["text"] == "Fixtures")
        panel = page.crop((0, 0, anchor["x0"] - 1, page.height)).extract_text(layout=False) or ""

    block, cols = None, []
    for ln in _clean_lines(panel):
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("bunker price"):
            block = "bunker"; continue
        if low.startswith("location"):
            cols = s.split()[1:]                      # ['380', 'CST', 'VLSFO'] -> fix below
            cols = ["380 CST", "VLSFO"] if "380" in s else cols
            continue
        if low.startswith("baltic rate"):
            block = "baltic"; continue
        if low.startswith("based on"):
            res.meta["baltic_basis"] = s; continue
        if low.startswith("crude oil"):
            block = "crude"; continue
        if low.startswith(("type", "broker")):
            block = None if low.startswith("broker") else block; continue
        if re.match(r"^MEG\s+[A-Z][a-z]{2}\s+[A-Z][a-z]{2}$", s):
            block, cols = "meg_cargoes", s.split()[1:]; continue
        if low.startswith("ship count"):
            block = "ship_count"; continue
        if block == "ship_count" and re.fullmatch(r"[A-Z][a-z]{2}\s+[A-Z][a-z]{2}", s):
            cols = s.split(); continue

        tok = s.split()
        if block == "bunker" and len(tok) == 3:
            for grade, v in zip(cols, tok[1:]):
                res.bunkers.append({"port": tok[0].upper(), "grade": grade, "price_usd_mt": _num(v),
                                    "change": None, "raw_line": s})
        elif block == "baltic" and len(tok) == 3 and re.match(r"T[DC]\d", tok[0]):
            val = _num(tok[1])
            res.baltic.append({"route": tok[0], "assessment_date": report_date,
                               "value": val, "change": _num(tok[2]),
                               "unit": "USD_LUMPSUM" if val and val > 100000 else "WS",
                               "tce_usd_day": None, "qty_kt": None, "raw_line": s})
        elif block == "crude" and len(tok) == 3:
            res.prices.append({"instrument": tok[0].upper(), "value": _num(tok[1]),
                               "change": _num(tok[2]), "unit": "USD/bbl", "raw_line": s})
        elif block in ("meg_cargoes", "ship_count") and re.match(r"\d(st|nd|rd)", s, re.I):
            decade = s.split()[0].lower()
            for mon, v in zip(cols, tok[-2:]):
                mo = MONTHS[mon.upper()]
                res.decade_counts.append({
                    "metric": "MEG_CARGOES" if block == "meg_cargoes" else "MEG_SHIPS_EX_SUBS",
                    "month": date(infer_year(mo, report_date), mo, 1), "decade": decade,
                    "value": _num(v), "raw_line": s})
    return res


# ----------------------------------------------------------------------------- Suezmax
SUEZ_SECTIONS = {"WAFR", "MED & BLACK SEA", "NORTH SEA", "NORTH", "AMERICAS", "EAST OF SUEZ",
                 "MEG", "BALTIC", "CARIBS", "USG"}


def parse_suezmax(text: str, report_date: date | None = None) -> ParseResult:
    lines = _clean_lines(text)
    if report_date is None:
        m = re.search(r"(\d{1,2})(?:ST|ND|RD|TH)?\s+([A-Z]{3})\s+(\d{4})", text.upper())
        report_date = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").date()
    res = ParseResult(meta={"report_type": "SUEZMAX_DAILY", "report_date": report_date})

    block = section = None
    bunker_grade = None
    pending = None              # header of single-value blocks (BRENT, EUA)
    for i, raw in enumerate(lines):
        line = raw.strip()
        up = line.upper()
        if not line or set(line) <= set("-="):
            continue
        if "headline" not in res.meta and re.match(r"^(TO |THE |A |[A-Z].{30,})", line) \
                and "CLARKSONS" not in up and not re.search(r"\d{4}$", line) and block is None:
            res.meta["headline"] = line
            continue
        if up in ("CARGOES", "FIXTURES"):
            block, section = up, None; continue
        if up.startswith("BALTIC ASSESSMENT"):
            block = "BALTIC"
            m = re.search(r"(\d{2})\.(\d{2})\.(\d{2})", line)
            res.meta["baltic_date"] = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
            continue
        if up.startswith("TURKISH STRAITS"):
            block = "STRAITS"; res.meta["turkish_straits"] = []; continue
        if up.startswith("BUNKER PRICES") or up.startswith("0.5% MARINE FUEL"):
            block, bunker_grade = "BUNKER", line; continue
        if up.startswith(("BRENT", "EUA PRICE")):
            block, pending = "SINGLE", line; continue
        if up.startswith("SOURCE:"):
            continue
        if re.match(r"^[A-Z .-]+$", up) and re.search(r"\b(T:|E:)", lines[i + 1] if i + 1 < len(lines) else ""):
            break                                                 # broker signature block
        if up in SUEZ_SECTIONS and block in ("CARGOES", "FIXTURES"):
            section = up; continue

        if block == "FIXTURES" and section:
            m = POSITION_LINE.match(up)
            if m:
                res.fixtures.append(_position_row(up, m, report_date, section, block, i)); continue
            parts = SPLIT.split(line)
            if len(parts) >= 6 and re.fullmatch(r"\d{2,3}(\s+[A-Z]{2,3})?", parts[1]):
                qty, *grade = parts[1].split()
                load, _, disch = parts[2].partition("/")
                ls, le = parse_laycan(parts[3], report_date)
                status_txt = " ".join(parts[6:]) if len(parts) > 6 else ""
                res.fixtures.append({"section": section, "block": block, "line_no": i, "format": "full",
                                     "vessel": parts[0], "qty_kt": int(qty), "cargo_grade": grade[0] if grade else None,
                                     "load": load.strip(), "discharge": disch.strip() or None,
                                     "laycan_raw": parts[3], "laycan_start": ls, "laycan_end": le,
                                     **parse_rate(parts[4]), "charterer": parts[5],
                                     **parse_status(status_txt), "raw_line": line})
                continue
            if res.fixtures and res.fixtures[-1]["line_no"] == i - 1 and len(parts) <= 2:
                prev = res.fixtures[-1]                      # wrapped status line, e.g. 'SWEET, TRAFIGURA RELET'
                merged = f"{prev.get('status_raw') or ''} {line}".strip()
                prev.update(parse_status(merged)); prev["raw_line"] += " " + line; prev["line_no"] = i
                continue
            res.unparsed.append({"section": section, "block": block, "line_no": i, "raw_line": line})

        elif block == "CARGOES" and section:
            m = re.match(rf"^(?P<chrt>\S+(?: \S+)*?)\s{{2,}}(?P<qty>\d{{2,3}})\s+(?P<route>\S.*?)\s{{2,}}"
                         rf"(?P<lay>{LAYCAN_RE.pattern})\s*(?:{DASH}\s*(?P<notes>.*))?$", line)
            if m:
                load, _, disch = m.group("route").partition("/")
                ls, le = parse_laycan(m.group("lay"), report_date)
                notes = (m.group("notes") or "").strip() or None
                res.cargoes.append({"section": section, "line_no": i, "charterer": m.group("chrt"),
                                    "qty_kt": int(m.group("qty")), "load": load.strip(),
                                    "discharge": disch.strip() or None, "laycan_raw": m.group("lay").strip(),
                                    "laycan_start": ls, "laycan_end": le, "notes": notes,
                                    "reported": bool(notes and "RPTD" in notes),
                                    "replaces_vessel": (re.search(r"RPLC (.+)", notes or "") or [None, None])[1],
                                    "raw_line": line})
            else:
                res.unparsed.append({"section": section, "block": block, "line_no": i, "raw_line": line})

        elif block == "BALTIC":
            m = re.match(r"^(T[DC]\w+)\s+(\d+)KT\s+([\d.,]+)\s+([+-][\d.,]+)\s+\$([\d,]+)\s*PD", up)
            if m:
                res.baltic.append({"route": m.group(1), "assessment_date": res.meta.get("baltic_date"),
                                   "qty_kt": int(m.group(2)), "value": _num(m.group(3)), "unit": "WS",
                                   "change": _num(m.group(4)), "tce_usd_day": _num(m.group(5)), "raw_line": line})

        elif block == "STRAITS":
            res.meta["turkish_straits"].append(line)

        elif block == "BUNKER":
            m = re.match(r"^([A-Z ]+?)\s+([\d.]+)\s+([+-])\s+([\d.]+)$", up)
            if m:
                chg = float(m.group(4)) * (1 if m.group(3) == "+" else -1)
                res.bunkers.append({"port": m.group(1).strip(), "grade": bunker_grade,
                                    "price_usd_mt": float(m.group(2)), "change": chg, "raw_line": line})

        elif block == "SINGLE":
            m = re.match(r"^([\d.]+)\s+([+-])\s+([\d.]+)$", line)
            if m:
                name = "BRENT" if pending.upper().startswith("BRENT") else "EUA"
                res.prices.append({"instrument": name, "value": float(m.group(1)),
                                   "change": float(m.group(3)) * (1 if m.group(2) == "+" else -1),
                                   "unit": "USD/bbl" if name == "BRENT" else "EUR/t", "raw_line": line})
                block = None
    if "turkish_straits" in res.meta:
        res.meta["turkish_straits"] = " | ".join(res.meta["turkish_straits"])
    return res


def _num(s) -> float | None:
    if s is None:
        return None
    s = str(s).replace(",", "").replace("$", "").strip()
    if s.upper() in ("N/A", "NA", "-", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None
