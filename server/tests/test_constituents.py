"""
The index weights' second sources (sources/constituents.py).

iShares' holdings file answered 404 from Thu 12 Nov 2026, its own download link
included, and Index movers had nothing else to read. Invesco's QQQ file stands
behind it for the Nasdaq 100 and State Street's SPY workbook for the S&P 500.
The shapes below are cut from the two files as they were read on 14 Nov 2026.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest

from newsterminal.http import FetchResult, SourceStatus
from newsterminal.sources import constituents as cons

INVESCO = {
    "cusip": "QQQ", "effectiveDate": "2026-11-12", "totalNumberOfHoldings": 106,
    "holdings": [
        {"ticker": "NVDA", "issuerName": "NVIDIA Corp", "percentageOfTotalNetAssets": 6.77,
         "securityTypeName": "Common Stock"},
        {"ticker": "AAPL", "issuerName": "Apple Inc", "percentageOfTotalNetAssets": 8.446411,
         "securityTypeName": "Common Stock"},
        {"ticker": "ASML", "issuerName": "ASML Holding NV", "percentageOfTotalNetAssets": 0.9,
         "securityTypeName": "American Depository Receipt - NY"},
        # Not companies: the fund's cash, its futures, its collateral.
        {"ticker": "USD", "issuerName": "US Dollar", "percentageOfTotalNetAssets": 0.05,
         "securityTypeName": "Currency"},
        {"ticker": "NQZ6", "issuerName": "NASDAQ 100 E-MINI", "percentageOfTotalNetAssets": 0.1,
         "securityTypeName": "Index Future"},
        {"ticker": None, "issuerName": "Cash Collateral", "percentageOfTotalNetAssets": 0.01,
         "securityTypeName": "Currency Collateral"},
        {"ticker": "ZERO", "issuerName": "No Weight Inc", "percentageOfTotalNetAssets": 0,
         "securityTypeName": "Common Stock"},
    ],
}


def _xlsx(rows: list[list[str]]) -> bytes:
    """A workbook as State Street writes one: every text cell a shared string, the
    weights as plain numbers."""
    strings: list[str] = []
    xml_rows = []
    for i, row in enumerate(rows, start=1):
        cells = []
        for j, text in enumerate(row):
            ref = f"{'ABCDEFGH'[j]}{i}"
            try:
                float(text)
                cells.append(f'<c r="{ref}"><v>{text}</v></c>')
            except ValueError:
                if text not in strings:
                    strings.append(text)
                cells.append(f'<c r="{ref}" t="s"><v>{strings.index(text)}</v></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sheet = f"<worksheet {ns}><sheetData>{''.join(xml_rows)}</sheetData></worksheet>"
    shared = f"<sst {ns}>{''.join(f'<si><t>{s}</t></si>' for s in strings)}</sst>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", shared)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


SPDR = _xlsx([
    ["Fund Name:", "State Street SPDR S&amp;P 500 ETF Trust"],
    ["Ticker Symbol:", "SPY"],
    ["Holdings:", "As of 12-Nov-2026"],
    ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"],
    ["NVIDIA CORP", "NVDA", "67066G104", "2379504", "6.137977", "-", "2.9583741E8", "USD"],
    ["APPLE INC", "AAPL", "037833100", "2046251", "7.904389", "-", "1.78410117E8", "USD"],
    ["BERKSHIRE HATHAWAY INC CL B", "BRK.B", "084670702", "2073390", "1.61", "-", "1E7", "USD"],
    ["US DOLLAR", "-", "", "", "0.05", "-", "1", "USD"],
    ["Past performance is not a reliable indicator of future performance."],
])


def test_invescos_file_is_the_funds_shares_heaviest_first() -> None:
    rows, as_of = cons.parse_invesco(json.dumps(INVESCO).encode())
    assert [(r["symbol"], r["weight"]) for r in rows] == [
        ("AAPL", 8.4464), ("NVDA", 6.77), ("ASML", 0.9)]
    assert rows[0]["name"] == "Apple Inc" and as_of == "2026-11-12"
    assert cons.parse_invesco(b"[]") == ([], None)


def test_state_streets_workbook_is_read_without_a_spreadsheet_library() -> None:
    rows, as_of = cons.parse_spdr(SPDR)
    # "BRK.B" is "BRK-B" on the tape the returns come from; the cash line and the
    # footnote are not companies.
    assert [(r["symbol"], r["weight"]) for r in rows] == [
        ("AAPL", 7.9044), ("NVDA", 6.138), ("BRK-B", 1.61)]
    assert rows[0]["name"] == "Apple Inc" and rows[0]["sector"] == ""
    assert as_of == "12-Nov-2026"


def test_the_tabs_are_the_funds_over_the_books() -> None:
    assert cons.FUND == {"NQ": "QQQ", "ES": "SPY"}
    assert [f[0] for f in cons.FUNDS] == list(cons.FUND) == list(cons.SOURCES)


def test_a_body_that_is_not_the_file_is_refused_before_it_is_kept() -> None:
    assert cons._xlsx_body(SPDR) is None
    assert cons._xlsx_body(b"<!DOCTYPE html><html>404") is not None
    assert cons._invesco_body(json.dumps(INVESCO).encode()) is None
    assert cons._invesco_body(b"<!DOCTYPE html>") is not None
    assert cons._invesco_body(b'{"error": "not found"}') is not None


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ("10.Nov.2026", "10 Nov 2026"),      # iShares, German
        ("10.Okt.2026", "10 Oct 2026"),
        ("3.Dez.2026", "3 Dec 2026"),
        ("2026-11-12", "12 Nov 2026"),       # Invesco
        ("12-Nov-2026", "12 Nov 2026"),      # State Street
        ("31.Feb.2026", "31.Feb.2026"),      # not a day: as it came
        ("sometime", "sometime"),
        (None, None),
    ],
)
def test_a_files_date_reads_one_way_whoever_wrote_it(raw: Any, text: str | None) -> None:
    assert cons.as_of_text(raw) == text


def _source(issuer: str, key: str) -> cons._Source:
    return cons._Source(issuer, f"http://{key}", key, lambda b: None,
                        lambda r: ([{"symbol": issuer[:1], "weight": 1.0}], "2026-11-12"))


def _reads(monkeypatch: pytest.MonkeyPatch, by_key: dict[str, FetchResult]) -> list[str]:
    asked: list[str] = []

    def fake(url: str, *, key: str, **kw: Any) -> FetchResult:
        asked.append(key)
        return by_key[key]

    monkeypatch.setattr(cons, "fetch", fake)
    monkeypatch.setattr(cons, "_held", {})
    return asked


LIVE = FetchResult(True, b"x", "live", 0.0, None, 200)
OLD = FetchResult(True, b"x", "stale", 2262.0, "HTTP 404", 404)
OLDER = FetchResult(True, b"x", "stale", 9000.0, "HTTP 500", 500)
DOWN = FetchResult(False, None, "unavailable", None, "HTTP 404", 404)


def test_the_first_source_is_used_while_it_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cons, "SOURCES", {"NQ": [_source("iShares", "a"), _source("Invesco", "b")]})
    asked = _reads(monkeypatch, {"a": LIVE, "b": LIVE})
    st, notes = SourceStatus("Constituents"), []
    got = cons._weights("NQ", st, notes)
    assert got is not None and got[2] == "iShares" and asked == ["a"] and not notes


def test_a_stale_first_source_gives_way_and_the_card_is_not_dated_by_it(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """13 Nov 2026: iShares 38 hours old, the chip red, the weights fine elsewhere."""
    monkeypatch.setattr(cons, "SOURCES", {"NQ": [_source("iShares", "a"), _source("Invesco", "b")]})
    _reads(monkeypatch, {"a": OLD, "b": LIVE})
    st, notes = SourceStatus("Constituents"), []
    got = cons._weights("NQ", st, notes)
    assert got is not None and got[2] == "Invesco"
    assert notes == ["NQ weights, iShares: not answering (HTTP 404)"]
    # Only the read that is used is counted: nothing stale is on the status.
    assert st.stale == 0 and st.fetches == 1


def test_with_every_source_down_the_newest_old_copy_is_shown_and_says_so(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cons, "SOURCES", {"NQ": [_source("iShares", "a"), _source("Invesco", "b")]})
    _reads(monkeypatch, {"a": OLDER, "b": OLD})
    st, notes = SourceStatus("Constituents"), []
    got = cons._weights("NQ", st, notes)
    assert got is not None and got[2] == "Invesco"       # 38 hours old beats 150
    assert st.stale == 1 and st.stale_age_min == 2262.0
    # And with nothing at all there is no basket, and both failures are named.
    _reads(monkeypatch, {"a": DOWN, "b": DOWN})
    notes = []
    assert cons._weights("NQ", SourceStatus("Constituents"), notes) is None
    assert len(notes) == 2


def test_a_source_that_just_failed_is_not_asked_again_for_an_hour(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The dead link was being requested every ninety seconds, for two days."""
    monkeypatch.setattr(cons, "SOURCES", {"NQ": [_source("iShares", "a"), _source("Invesco", "b")]})
    asked = _reads(monkeypatch, {"a": DOWN, "b": LIVE})
    clock = [1000.0]
    monkeypatch.setattr(cons.time, "time", lambda: clock[0])
    for _ in range(3):
        cons._weights("NQ", SourceStatus("Constituents"), [])
    assert asked.count("a") == 1 and asked.count("b") == 3
    clock[0] += cons.RETRY_SEC + 1
    cons._weights("NQ", SourceStatus("Constituents"), [])
    assert asked.count("a") == 2


def test_each_index_has_a_second_issuer_behind_ishares() -> None:
    for key in ("NQ", "ES"):
        issuers = [s.issuer for s in cons.SOURCES[key]]
        assert issuers[0] == "iShares" and len(issuers) == 2
        assert len({s.key for s in cons.SOURCES[key]}) == 2
