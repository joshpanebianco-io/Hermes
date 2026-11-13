"""
Insider trades from Form 4s (sources/insiders.py): which filings are read, what a filing
says, and which trades are news.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from newsterminal.sources import insiders as ins

FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0508</schemaVersion>
  <documentType>4</documentType>
  <aff10b5One>{plan}</aff10b5One>
  <issuer><issuerCik>0000001</issuerCik><issuerName>Acme Corp</issuerName>
    <issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0000002</rptOwnerCik>
      <rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    {lines}
  </nonDerivativeTable>
  <footnotes>{notes}</footnotes>
</ownershipDocument>"""


def line(code: str, shares: float, price: float, day: str = "2026-11-10", note: str = "") -> str:
    ref = f'<footnoteId id="{note}"/>' if note else ""
    ad = "A" if code == "P" else "D"
    return (f"<nonDerivativeTransaction><transactionDate><value>{day}</value></transactionDate>"
            f"<transactionCoding><transactionFormType>4</transactionFormType>"
            f"<transactionCode>{code}</transactionCode>{ref}</transactionCoding>"
            f"<transactionAmounts><transactionShares><value>{shares}</value></transactionShares>"
            f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare>"
            f"<transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>"
            f"</transactionAmounts></nonDerivativeTransaction>")


def doc(lines: str, plan: str = "0", notes: str = "") -> str:
    return FORM4.format(plan=plan, lines=lines, notes=notes)


def test_an_open_market_buy_in_fills_is_one_buy_at_its_average() -> None:
    p = ins.parse_form4(doc(line("P", 20000, 40.0) + line("P", 10000, 43.6) + line("A", 5000, 0.0)))
    assert p is not None and p["who"] == "CEO Doe Jane" and p["symbol"] == "ACME"
    got = ins.notable(p, "2026-11-11", "u")
    assert got == [{"side": "buy", "who": "CEO Doe Jane", "value": 1236000, "shares": 30000,
                    "price": 41.2, "date": "2026-11-10", "filed": "2026-11-11", "url": "u"}]
    assert ins.line_of(got[0]) == "CEO Doe Jane bought $1.2M at $41.20 on 10 Nov"


def test_a_small_buy_and_the_paperwork_are_not_news() -> None:
    p = ins.parse_form4(doc(line("P", 1000, 40.0) + line("M", 50000, 10.0) + line("F", 9000, 50.0)))
    assert p is not None and ins.notable(p, "2026-11-11", "u") == []


def test_a_planned_sale_is_not_news_and_a_discretionary_one_is() -> None:
    # The form's own 10b5-1 box.
    boxed = ins.parse_form4(doc(line("S", 50000, 100.0), plan="1"))
    assert boxed is not None and ins.notable(boxed, "2026-11-11", "u") == []
    # A footnote on the line that says so.
    plan = '<footnote id="F1">Sold pursuant to a Rule 10b5-1 trading plan adopted May 1.</footnote>'
    noted = ins.parse_form4(doc(line("S", 50000, 100.0, note="F1"), notes=plan))
    assert noted is not None and ins.notable(noted, "2026-11-11", "u") == []
    # A footnote that says the sale was NOT under a plan, and one with no footnote at all.
    nope = '<footnote id="F1">These sales were not made pursuant to a Rule 10b5-1 plan.</footnote>'
    free = ins.parse_form4(doc(line("S", 50000, 100.0, note="F1"), notes=nope))
    assert free is not None
    assert [t["side"] for t in ins.notable(free, "2026-11-11", "u")] == ["sell"]
    bare = ins.parse_form4(doc(line("S", 50000, 100.0)))
    got = ins.notable(bare or {}, "2026-11-11", "u")
    assert got[0]["value"] == 5_000_000
    assert ins.line_of(got[0]).startswith("CEO Doe Jane sold $5.0M")
    # Under SELL_MIN a discretionary sale is still not news.
    small = ins.parse_form4(doc(line("S", 5000, 100.0)))
    assert small is not None and ins.notable(small, "2026-11-11", "u") == []


def test_a_document_that_is_not_a_form_4_reads_as_nothing() -> None:
    assert ins.parse_form4("<html>nope</html>") is None
    assert ins.parse_form4("not xml") is None


def test_the_filing_list_gives_each_form_4s_own_xml() -> None:
    sub = {"filings": {"recent": {
        "form": ["4", "8-K", "4", "4"],
        "filingDate": ["2026-11-12", "2026-11-11", "2026-11-01", "2026-09-01"],
        "accessionNumber": ["0001-26-000010", "0001-26-000009", "0001-26-000008", "0001-26-000001"],
        "primaryDocument": ["xslF345X05/wk-form4_1.xml", "a.htm", "xslF345X05/form4.xml", "x.xml"],
    }}}
    refs = ins.form4_refs(sub, 789019, date(2026, 11, 13))
    assert [r["acc"] for r in refs] == ["000126000010", "000126000008"]   # 30 days, Form 4 only
    assert refs[0]["xml"].endswith("/789019/000126000010/wk-form4_1.xml")
    assert refs[0]["url"].endswith("/000126000010/xslF345X05/wk-form4_1.xml")


def test_the_book_reads_each_filing_once_and_keeps_the_month(tmp_path: Any) -> None:
    book = ins.InsiderBook(str(tmp_path / "f4.json"))
    ref = {"acc": "A1", "filed": "2026-11-11", "url": "u", "xml": "x"}
    old = {"acc": "A0", "filed": "2026-10-01", "url": "u", "xml": "x"}
    assert book.wanted([ref]) == [ref]
    assert book.take(ref, doc(line("P", 30000, 41.2)))
    assert book.take(old, doc(line("P", 30000, 41.2, day="2026-10-01")))
    assert book.wanted([ref]) == []
    got = book.trades([ref, old], date(2026, 11, 13))
    assert [t["date"] for t in got] == ["2026-11-10"]   # October's is past the month
    # A document that will not read is tried MAX_TRIES times, then left.
    bad = {"acc": "B", "filed": "2026-11-12", "url": "u", "xml": "x"}
    for _ in range(ins.MAX_TRIES):
        assert not book.take(bad, "<html/>")
    assert book.wanted([bad]) == []
    book.save(date(2026, 11, 13))
    again = ins.InsiderBook(str(tmp_path / "f4.json"))
    # The file keeps KEEP_DAYS (45), longer than the month shown; a bad read is not kept.
    assert set(again.docs) == {"A1", "A0"}
    book.save(date(2026, 11, 30))
    assert set(ins.InsiderBook(str(tmp_path / "f4.json")).docs) == {"A1"}


def test_a_trade_is_shown_under_the_stock_it_was_in_not_the_list_it_came_from(
        tmp_path: Any) -> None:
    """Live, 2026-11-13: HOOD's EDGAR list carried a Form 4 Robinhood filed as a 10% owner
    of another company, and the HOOD row read "10% owner Robinhood Markets, Inc. sold
    $3.1M at $24.77" as an insider sale of HOOD. The issuer on the filing decides."""
    book = ins.InsiderBook(str(tmp_path / "f4.json"))
    other = doc(line("S", 125000, 24.77)).replace(
        "<issuerTradingSymbol>ACME</issuerTradingSymbol>",
        "<issuerTradingSymbol>BRK-B</issuerTradingSymbol>")
    assert book.take({"acc": "H1", "filed": "2026-11-11", "url": "u", "xml": "x"}, other)
    assert book.take({"acc": "A1", "filed": "2026-11-11", "url": "u", "xml": "x"},
                     doc(line("P", 30000, 41.2)))
    today = date(2026, 11, 13)
    assert [t["side"] for t in book.trades_of("ACME", today)] == ["buy"]
    assert book.trades_of("HOOD", today) == []
    # A class share's dash and dot are one stock.
    assert [t["price"] for t in book.trades_of("BRK.B", today)] == [24.77]
    # It survives a restart: the book, not the day's list, holds it.
    book.save(today)
    assert len(ins.InsiderBook(str(tmp_path / "f4.json")).trades_of("ACME", today)) == 1


def test_a_filing_kept_before_its_issuer_was_is_read_again_only_if_it_has_a_trade(
        tmp_path: Any) -> None:
    book = ins.InsiderBook(str(tmp_path / "f4.json"))
    book.docs = {"OLD": {"filed": "2026-11-10", "url": "u", "trades": [{"side": "sell"}]},
                 "NIL": {"filed": "2026-11-10", "url": "u", "trades": []}}
    refs = [{"acc": a, "filed": "2026-11-10", "url": "u", "xml": "x"} for a in ("OLD", "NIL")]
    assert [r["acc"] for r in book.wanted(refs)] == ["OLD"]
    # Until it is read again it is shown under no stock.
    assert book.trades_of("ACME", date(2026, 11, 13)) == []
