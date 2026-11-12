"""
The earnings list's second source (sources/earnings.py): TradingView's screener,
read when Nasdaq is not delivering.

The fixture is twenty rows of the two replies read on 11 Nov 2026 for the window
around Tue 10 Nov: the reports just gone (a preferred line, two ADR lines of one
company, a name under the panel's $50bn, CoreWeave from the owner's list) and
the ones ahead (after the close, before the open, and two whose company has not
said). Every figure asserted here was read off that file first.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

import pytest

from newsterminal.http import FetchResult
from newsterminal.sources import earnings as earn

HERE = os.path.dirname(__file__)
TODAY = date(2026, 11, 10)
LO, HI = date(2026, 11, 8), date(2026, 11, 14)
WATCH = frozenset({"CRWV", "NBIS"})


def fixture() -> dict[str, Any]:
    with open(os.path.join(HERE, "fixtures", "tv_earnings_trim.json"), encoding="utf-8") as f:
        doc: dict[str, Any] = json.load(f)
    return doc


def by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["symbol"]: r for r in rows}


def test_the_reports_just_gone_carry_the_result_and_when_it_landed() -> None:
    rows = by_symbol(earn.parse_tradingview(fixture()["last"], earn.TV_LAST, LO, HI))
    # A preferred line reports nothing of its own; a name under $50bn is not the panel's.
    assert "KKR/PD" not in rows and "TTWO" not in rows and "CRWV" not in rows
    ceg = rows["CEG"]
    assert (ceg["date"], ceg["when"]) == ("2026-11-09", "pre")
    assert (ceg["eps_actual"], ceg["eps_forecast"]) == ("$5.06", "$3.90")
    assert ceg["surprise_pct"] == 29.84
    assert ceg["name"] == "Constellation Energy Corporation" and ceg["watch_only"] is False
    assert ceg["market_cap"] == pytest.approx(94.87e9, rel=1e-3)
    # Monday after the close: tomorrow's gap, not Monday's.
    assert (rows["OXY"]["date"], rows["OXY"]["when"]) == ("2026-11-09", "after")
    # Both ADR lines of one company are listed, as Nasdaq lists them.
    assert rows["PBR"]["eps_actual"] == rows["PBR.A"]["eps_actual"] == "$1.20"
    assert rows["PBR"]["surprise_pct"] == -9.39


def test_a_name_on_the_list_is_kept_whatever_its_size() -> None:
    rows = by_symbol(earn.parse_tradingview(fixture()["last"], earn.TV_LAST, LO, HI, WATCH))
    crwv = rows["CRWV"]
    assert (crwv["date"], crwv["when"], crwv["watch_only"]) == ("2026-11-10", "after", True)
    # A loss is printed the way Nasdaq prints one, and a smaller loss is a beat.
    assert (crwv["eps_actual"], crwv["eps_forecast"], crwv["surprise_pct"]) == (
        "($0.95)", "($1.27)", 25.58)
    assert "TTWO" not in rows


def test_the_reports_ahead_carry_the_estimate_and_which_side_of_the_bell() -> None:
    rows = by_symbol(earn.parse_tradingview(fixture()["next"], earn.TV_NEXT, LO, HI, WATCH))
    assert set(rows) == {"CSCO", "AMAT", "MUFG", "BN", "NU", "NBIS"}  # FNV and WSM are under $50bn
    csco = rows["CSCO"]
    assert (csco["date"], csco["when"]) == ("2026-11-12", "after")
    assert (csco["eps_forecast"], csco["eps_actual"], csco["surprise_pct"]) == ("$1.33", None, None)
    assert rows["BN"]["when"] == "pre"
    # The company has not said: noon UTC is a placeholder, not a time.
    assert (rows["MUFG"]["date"], rows["MUFG"]["when"]) == ("2026-11-13", "unspecified")
    assert (rows["NBIS"]["when"], rows["NBIS"]["watch_only"]) == ("pre", True)
    assert rows["NBIS"]["eps_forecast"] == "($0.72)"


def test_the_window_is_new_yorks_days_and_a_short_row_is_skipped() -> None:
    doc = fixture()["next"]
    # Thursday's reports are outside a window that ends on Wednesday.
    got = earn.parse_tradingview(doc, earn.TV_NEXT, LO, date(2026, 11, 11), WATCH)
    assert got == []
    short = {"data": [{"s": "NASDAQ:CSCO", "d": ["CSCO", "Cisco"]}, "junk", {"d": None}]}
    assert earn.parse_tradingview(short, earn.TV_NEXT, LO, HI) == []
    assert earn.parse_tradingview({"error": "x"}, earn.TV_NEXT, LO, HI) == []
    assert earn.parse_tradingview(None, earn.TV_NEXT, LO, HI) == []


@pytest.mark.parametrize(
    ("v", "want"),
    [(1.84, "$1.84"), (-0.17, "($0.17)"), (0, "$0.00"), (12.208608, "$12.21"),
     (None, None), (True, None), (float("nan"), None), ("1.84", None)],
)
def test_an_eps_is_printed_the_way_nasdaq_prints_it(v: Any, want: str | None) -> None:
    assert earn._money(v) == want
    if want is not None:
        assert earn._eps(want) == pytest.approx(round(float(v), 2))


@pytest.mark.parametrize(
    ("flag", "hm", "placeholder", "want"),
    [(-1, (16, 5), False, "pre"),          # the flag is the company's word
     (1, (7, 0), False, "after"),
     (0, (16, 5), False, "after"),         # no flag: the instant itself
     (0, (7, 0), False, "pre"),
     (0, (12, 0), False, "unspecified"),
     (None, (7, 0), True, "unspecified"),  # ahead, and a placeholder is no time
     (0, (7, 0), True, "unspecified")],
)
def test_which_side_of_the_bell(flag: Any, hm: tuple[int, int], placeholder: bool,
                                want: str) -> None:
    at = datetime(2026, 11, 10, hm[0], hm[1], tzinfo=earn.ET)
    assert earn._tv_when(flag, at, placeholder) == want


def test_the_request_is_cut_to_the_window_by_the_report_field() -> None:
    q = earn.tv_query(earn.TV_NEXT, 100, 200)
    assert {"left": earn.TV_NEXT, "operation": "in_range", "right": [100, 200]} in q["filter"]
    assert q["columns"] == earn.TV_COLUMNS and q["range"] == [0, earn.TV_RANGE]
    assert earn.tv_body(b'{"totalCount":0,"data":[]}') is None
    assert earn.tv_body(b"<html>") is not None and earn.tv_body(b'{"x":1}') is not None


# --- which feed is read --------------------------------------------------------------


class Feeds:
    """Stands in for `fetch`: Nasdaq's days and the screener's two replies, each made
    to answer, serve the copy on disk, or fail."""

    def __init__(self) -> None:
        self.nasdaq = "live"
        self.tv = "live"
        self.asked: list[str] = []

    def __call__(self, url: str, **kw: Any) -> FetchResult:
        if "nasdaq.com" in url:
            self.asked.append("nasdaq")
            body = json.dumps({"data": {"rows": [
                {"symbol": "CSCO", "name": "Cisco Systems", "marketCap": "$386,000,000,000",
                 "time": "time-after-hours", "epsForecast": "$1.15", "eps": ""}]}}).encode()
            return self._as(self.nasdaq, body, "HTTP 403")
        field = json.loads(kw["data"])["filter"][-1]["left"]
        self.asked.append("last" if field == earn.TV_LAST else "next")
        doc = fixture()["last" if field == earn.TV_LAST else "next"]
        return self._as(self.tv, json.dumps(doc).encode(), "HTTP 502")

    @staticmethod
    def _as(how: str, body: bytes, err: str) -> FetchResult:
        if how == "live":
            return FetchResult(True, body, "live", 0.0, None, 200)
        if how == "stale":
            return FetchResult(True, body, "stale", 870.0, err, None)
        return FetchResult(False, None, "unavailable", None, err, None)


@pytest.fixture
def feeds(monkeypatch: pytest.MonkeyPatch) -> Feeds:
    f = Feeds()
    monkeypatch.setattr(earn, "fetch", f)
    monkeypatch.setattr(earn, "_nasdaq_wait", 0.0)
    monkeypatch.setattr(earn, "_nasdaq_why", "")
    monkeypatch.setattr(earn, "_source", "nasdaq")
    return f


def test_nasdaq_is_the_list_while_it_answers(feeds: Feeds) -> None:
    rows, st = earn.collect(keep=WATCH, today=TODAY)
    assert earn.source() == "nasdaq" and st.ok and st.source == "live"
    assert set(feeds.asked) == {"nasdaq"}
    assert {r["symbol"] for r in rows} == {"CSCO"} and rows[0]["eps_forecast"] == "$1.15"


def test_the_screener_takes_over_when_nasdaq_serves_only_its_copy(
        feeds: Feeds, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1_794_340_000.0]  # Tue 10 Nov 2026, the afternoon
    monkeypatch.setattr(earn.time, "time", lambda: clock[0])
    feeds.nasdaq = "stale"
    rows, st = earn.collect(keep=WATCH, today=TODAY)
    assert earn.source() == "tradingview"
    assert st.ok and st.source == "live" and st.error is None
    assert st.notes == ["TradingView's screener: Nasdaq is not answering (HTTP 403)"]
    got = by_symbol(rows)
    # Last night's result is in, which the copy on disk never had, and Thursday's are ahead.
    assert got["CRWV"]["eps_actual"] == "($0.95)" and got["CSCO"]["when"] == "after"
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
    # Within a day the biggest comes first.
    thu = [r["symbol"] for r in rows if r["date"] == "2026-11-12"]
    assert thu[:2] == ["CSCO", "AMAT"]

    # A host that is refusing is not asked again every tick.
    del feeds.asked[:]
    clock[0] += 600
    earn.collect(keep=WATCH, today=TODAY)
    assert feeds.asked == ["last", "next"]
    # Half an hour on it is asked once more, and when it answers it is the list again.
    del feeds.asked[:]
    clock[0] += earn.NASDAQ_RETRY_SEC
    feeds.nasdaq = "live"
    rows, st = earn.collect(keep=WATCH, today=TODAY)
    assert earn.source() == "nasdaq" and set(feeds.asked) == {"nasdaq"}


def test_with_neither_the_copy_on_disk_is_shown_and_says_how_old(feeds: Feeds) -> None:
    feeds.nasdaq, feeds.tv = "stale", "down"
    rows, st = earn.collect(keep=WATCH, today=TODAY)
    assert earn.source() == "nasdaq" and st.ok and st.source == "stale"
    assert st.error and "showing the copy from" in st.error
    assert {r["symbol"] for r in rows} == {"CSCO"}
