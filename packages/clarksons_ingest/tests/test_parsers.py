"""Regression tests on real reports. Add each new layout you see as a sample file."""
from datetime import date
from pathlib import Path

from clarksons_ingest.parsers import parse_suezmax, parse_vlcc_body, parse_vlcc_pdf_panel

S = Path(__file__).parent.parent / "samples"
RD = date(2026, 10, 5)


def test_vlcc_body():
    r = parse_vlcc_body((S / "vlcc_evening_2026-10-05.txt").read_text(), RD)
    assert len(r.fixtures) == 12 and not r.unparsed
    de = next(f for f in r.fixtures if f["vessel"] == "DUBAI ENERGY")
    assert (de["ws_low"], de["ws_high"], de["laycan_start"], de["status"]) == (780, 830, date(2026, 10, 21), "ON_SUBS")
    hv = next(f for f in r.fixtures if f["vessel"] == "HOUSTON VOYAGER")
    assert hv["status"] == "ON_HOLD" and hv["or_other_vessel"] == "EL SEGUNDO VOYAGER"
    assert next(f for f in r.fixtures if f["vessel"] == "SERIFOS")["rate_type"] == "RNR"


def test_vlcc_pdf_panel():
    pdf = S / "VLCC_Evening_Report_05_10_2026.pdf"
    if not pdf.exists():
        return
    r = parse_vlcc_pdf_panel(str(pdf), RD)
    b = {x["route"]: x for x in r.baltic}
    assert b["TD3C"]["value"] == 1240.63 and b["TD22"]["unit"] == "USD_LUMPSUM"
    ships = {(d["month"], d["decade"]): d["value"] for d in r.decade_counts if d["metric"] == "MEG_SHIPS_EX_SUBS"}
    assert ships[(date(2026, 10, 1), "3rd")] == 93 and ships[(date(2026, 11, 1), "1st")] == 61


def test_suezmax_body_and_pdf_layouts():
    for name in ("suezmax_body_2026-10-05.txt", "suezmax_daily_2026-10-05.txt"):
        r = parse_suezmax((S / name).read_text())
        assert len(r.fixtures) == 16 and len(r.cargoes) == 12 and not r.unparsed
        otis = next(f for f in r.fixtures if f["vessel"] == "OTIS")
        assert otis["relet_by"] == "TRAFIGURA" and otis["ws_low"] == 1000
        sk = next(f for f in r.fixtures if f["vessel"] == "SPYROS K")
        assert sk["status"] == "FAILED" and sk["relet_by"] == "MERCURIA"
        assert next(f for f in r.fixtures if f["vessel"] == "DYNACOM TBN")["lumpsum_usd"] == 22e6
        assert {x["route"] for x in r.baltic} == {"TD6", "TD20", "TD23", "TD27", "TD33"}
        assert r.meta["baltic_date"] == date(2026, 10, 2)
