"""
The calendar's second source (sources/calendar.py): TradingView's economic
calendar, read when Nasdaq is not delivering.

The fixture is 46 events cut from TradingView's reply on 11 Nov 2026, chosen for
the edges: Tuesday 10 Nov's CPI (eight rows, the two anyone prices among them),
Thursday's claims, Friday's PPI, one auction's four rows, two of a WASDE report's
twenty, the MBA's tables, the final German CPI, the UK's monthly and quarterly
GDP in one minute, and two figures with a currency and a scale. That CPI is the
reason this exists: Nasdaq refused from 05:49 ET that morning, so the copy the
desk held never got the 08:30 print.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import pytest

from newsterminal import releases
from newsterminal.http import FetchResult
from newsterminal.sources import calendar as cal

HERE = os.path.dirname(__file__)
LO, HI = date(2026, 11, 9), date(2026, 11, 13)


def fixture() -> dict[str, Any]:
    with open(os.path.join(HERE, "fixtures", "tv_calendar_trim.json"), encoding="utf-8") as f:
        doc: dict[str, Any] = json.load(f)
    return doc


def rows() -> list[dict[str, Any]]:
    return cal._finish(cal.parse_tradingview(fixture(), LO, HI))


def named(rs: list[dict[str, Any]], event: str, country: str = "United States") -> dict[str, Any]:
    got = [r for r in rs if r["event"] == event and r["country"] == country]
    assert len(got) == 1, (event, [r["event"] for r in rs if r["country"] == country])
    return got[0]


def groups(rs: list[dict[str, Any]]) -> list[releases.Release[dict[str, Any]]]:
    return releases.group(
        rs, event=lambda r: r["event"], when=lambda r: r["utc"], country=lambda r: r["country"],
        score=lambda r: r["score"],
        figures=lambda r: (r["actual_raw"], r["consensus_raw"], r["previous_raw"]))


# --- the names -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "unit", "want"),
    [("Core Inflation Rate MoM", "%", ("Core CPI m/m", None)),
     ("Inflation Rate YoY Final", "%", ("CPI y/y", "Final")),
     ("Harmonised Inflation Rate MoM Final", "%", ("HICP m/m", "Final")),
     ("Inflation Rate MoM NSA", "%", ("CPI m/m NSA", None)),
     # A bare price index is its level, and is named so it folds away.
     ("CPI", None, ("CPI Index", None)),
     ("PPI", None, ("PPI Index", None)),
     ("Consumer Price Index Final", None, ("CPI Index", "Final")),
     ("Core Consumer Prices", None, ("Core CPI Index", None)),
     ("CPI seasonally adjusted", None, ("CPI Index, s.a", None)),
     ("Non Farm Payrolls", None, ("Nonfarm Payrolls", None)),
     ("Nonfarm Payrolls Private", None, ("Private Nonfarm Payrolls", None)),
     ("GDP Growth Rate QoQ Prel", "%", ("GDP q/q", "Prel")),
     ("GDP Growth Annualized Prel", "%", ("GDP Annualized", "Prel")),
     ("Balance of Trade", "€", ("Trade Balance", None)),
     ("EIA Crude Oil Stocks Change", None, ("Crude Oil Inventories", None)),
     ("API Crude Oil Stock Change", None, ("API Weekly Crude Oil Stock", None)),
     ("PPI Ex Food Energy and Trade Services MoM", "%",
      ("PPI ex. Food/Energy/Transport m/m", None)),
     ("Michigan Consumer Sentiment Final", None, ("Michigan Consumer Sentiment", "Final")),
     ("Fed Waller Speech", None, ("Fed Waller Speaks", None)),
     # Not the Michigan survey: under its short name the tiers leave it alone.
     ("LSEG/Ipsos Primary Consumer Sentiment Index", None, ("LSEG/Ipsos PCSI", None)),
     # The feed's raw key, when a row has no title of its own.
     ("United States-NY Fed Consumer Expectation-NY Fed Inflation Expectation 1yr *", "%",
      ("NY Fed Inflation Expectation 1yr", None)),
     ("United States-Imports/Exports-Export Prices YY", "%", ("Export Prices y/y", None)),
     # Left alone: it already is Nasdaq's name.
     ("Initial Jobless Claims", None, ("Initial Jobless Claims", None)),
     ("ISM Manufacturing PMI", None, ("ISM Manufacturing PMI", None))],
)
def test_a_title_is_put_in_the_words_the_desk_already_reads(title: str, unit: str | None,
                                                            want: tuple[str, str | None]) -> None:
    assert cal.tv_event(title, unit) == want


def test_the_translated_names_are_ones_the_tiers_and_families_know() -> None:
    # The whole point of translating: the scorer, the themes and the release families
    # read the NAME, and none of them knows "Inflation Rate".
    assert cal.score("United States", "Inflation Rate MoM") == 2
    name, _ = cal.tv_event("Inflation Rate MoM", "%")
    assert cal.score("United States", name) == 5 and "inflation" in cal.themes_of(name)
    assert releases.family(cal.tv_event("Core Inflation Rate YoY", "%")[0]) == "cpi"
    assert releases.family(cal.tv_event("Harmonised Inflation Rate MoM Final", "%")[0]) == "cpi"
    third = cal.tv_event("PPI Ex Food Energy and Trade Services YoY", "%")[0]
    assert releases.family(third) == "ppi"
    assert cal.TIER2.search(cal.tv_event("EIA Crude Oil Stocks Change")[0])
    assert cal.TIER2.search(cal.tv_event("Balance of Trade")[0])


# --- the figures ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("v", "unit", "scale", "want"),
    [(0.3, "%", None, (0.3, "0.3%")),
     (-0.4, "%", None, (-0.4, "-0.4%")),
     (0, "%", None, (0.0, "0%")),
     (195, None, "K", (195_000.0, "195K")),           # as `_num` reads Nasdaq's "195K"
     (8.968, None, "M", (8_968_000.0, "8.968M")),
     (15.6, "€", "B", (15.6, "€15.6B")),
     (-27, "$", "B", (-27.0, "-$27B")),
     (2372.3, "¥", "B", (2372.3, "¥2,372.3B")),
     (337.511, None, None, (337.511, "337.511")),
     (19750, None, None, (19750.0, "19,750")),
     (None, "%", None, (None, None)),
     (True, "%", None, (None, None)),                 # a flag is not a figure
     (float("nan"), "%", None, (None, None)),
     ("0.3", "%", None, (None, None))],
)
def test_a_figure_carries_its_unit_and_scale(v: Any, unit: str | None, scale: str | None,
                                             want: tuple[float | None, str | None]) -> None:
    got = cal._tv_fig(v, unit, scale)
    assert got[1] == want[1]
    assert got[0] == (pytest.approx(want[0]) if want[0] is not None else None)


# --- the rows ------------------------------------------------------------------------


def test_the_cpi_the_desk_never_got_reads_hot() -> None:
    rs = rows()
    core = named(rs, "Core CPI m/m")
    assert (core["date"], core["et"]) == ("2026-11-10", "08:30")
    assert core["utc"] == "2026-11-10T13:30:00+00:00"
    assert (core["actual"], core["consensus"], core["previous"]) == (0.3, 0.2, 0.3)
    assert (core["actual_raw"], core["consensus_raw"]) == ("0.3%", "0.2%")
    assert core["surprise"] == pytest.approx(0.1) and core["released"] is True
    assert (core["read"], core["score"], core["core"]) == ("hot", 5, True)
    assert (core["region"], core["session"]) == ("us", "premkt") and "inflation" in core["themes"]
    assert core["meaning"] and "headwind" in core["meaning"]["NQ"]
    head = named(rs, "CPI m/m")
    assert (head["actual"], head["consensus"], head["read"]) == (0.4, 0.3, "hot")
    # One release, titled by core, with the levels and the unadjusted twin folded away.
    cpi = [g for g in groups(rs) if g.family == "cpi" and g.lead["country"] == "United States"]
    assert len(cpi) == 1
    assert cpi[0].lead["event"] == "Core CPI m/m"
    assert [s["event"] for s in cpi[0].subs] == ["CPI m/m"]
    assert sorted(x["event"] for x in cpi[0].levels) == [
        "CPI Index", "CPI Index, s.a", "CPI m/m NSA", "Core CPI Index"]


def test_the_detail_rows_and_the_bottom_tier_are_left_out() -> None:
    rs = rows()
    names = [r["event"] for r in rs]
    # Four rows an auction: its own (the yield) stays, bottom tier though it is.
    assert [n for n in names if "Auction" in n] == ["10-Year Note Auction"]
    for junk in ("WASDE", "USDA", "CPI-W", "PPI Machinery", "5/1 ARM", "Exp Sls"):
        assert not any(junk in n for n in names), junk
    # Bottom tier and not a name the tiers know: the weekly mortgage applications.
    assert "MBA Mortgage Applications" not in names and "MBA 30-Year Mortgage Rate" in names
    # Bottom tier and one the tiers do know rides with its release.
    claims = [g for g in groups(rs) if g.family == "claims"]
    assert len(claims) == 1 and claims[0].lead["event"] == "Initial Jobless Claims"
    assert sorted(s["event"] for s in claims[0].subs) == [
        "Continuing Jobless Claims", "Jobless Claims 4-week Average"]
    assert (claims[0].lead["consensus"], claims[0].lead["consensus_raw"]) == (195_000.0, "195K")
    ppi = [g for g in groups(rs) if g.family == "ppi"]
    assert len(ppi) == 1 and ppi[0].lead["event"] == "Core PPI m/m"
    assert {"PPI m/m", "PPI y/y", "Core PPI y/y", "PPI ex. Food/Energy/Transport m/m"} <= {
        s["event"] for s in ppi[0].subs}
    assert [x["event"] for x in ppi[0].levels] == ["PPI Index"]


def test_other_countries_keep_their_names_and_their_readings() -> None:
    rs = rows()
    de = named(rs, "CPI m/m", "Germany")
    assert (de["score"], de["region"], de["consensus_raw"]) == (4, "eu", "-0.2%")
    assert de["note"] and de["note"].startswith("Final reading.")
    assert releases.family(named(rs, "HICP m/m", "Germany")["event"]) == "cpi"
    trade = named(rs, "Trade Balance", "Germany")
    assert (trade["actual"], trade["actual_raw"], trade["read"]) == (15.6, "€15.6B", "cold")
    assert named(rs, "Current Account", "Japan")["actual_raw"] == "¥2,372.3B"
    # The UK prints monthly and quarterly GDP in one minute: both arrive as "GDP y/y",
    # and a name that already says which it is is not given a second suffix.
    uk = sorted(r["event"] for r in rs if r["country"] == "United Kingdom")
    assert uk == ["GDP 3-Month Avg", "GDP m/m", "GDP q/q", "GDP y/y", "GDP y/y"]


def test_the_window_is_new_yorks_days_and_unknown_countries_are_passed_over() -> None:
    def ev(at: str, country: str = "US") -> dict[str, Any]:
        return {"title": "Retail Sales MoM", "country": country, "date": at, "importance": 1,
                "actual": None, "forecast": 0.3, "previous": 0.1, "unit": "%"}

    doc = {"status": "ok", "result": [
        ev("2026-11-14T03:00:00.000Z"),          # 22:00 ET on the 13th: inside
        ev("2026-11-09T03:00:00.000Z"),          # 22:00 ET on the 8th: the day before
        ev("2026-11-10T13:30:00.000Z", "BR"),    # not a country this desk files
        ev("not a date"), "junk", {"title": "", "country": "US"},
    ]}
    got = cal.parse_tradingview(doc, LO, HI)
    assert [(r["date"], r["et"]) for r in got] == [("2026-11-13", "22:00")]
    assert cal.parse_tradingview({"status": "error"}, LO, HI) == []
    assert cal.parse_tradingview(None, LO, HI) == []


# --- the Board's speeches ------------------------------------------------------------


#: Rows as sources/fedcal.py makes them: Tue 10 Nov 04:00 and 15:30 ET, Thu 12 Nov
#: 10:00 ET, one with no time, one that is not a speech, one from the week after.
FED = [
    {"kind": "Speech", "title": "Speech - Governor Christopher J. Waller",
     "note": "Economic Outlook", "ts": 1794301200.0},
    {"kind": "Speech", "title": "Speech - Vice Chair for Supervision Michelle W. Bowman",
     "note": None, "ts": 1794342600.0},
    {"kind": "Testimony", "title": "Testimony - Chair Jerome H. Powell",
     "note": "Monetary Policy Report", "ts": 1794495600.0},
    {"kind": "Speech", "title": "Speech - Governor Lisa D. Cook", "ts": None},
    {"kind": "FOMC", "title": "FOMC Minutes", "ts": 1794495600.0},
    {"kind": "Speech", "title": "Speech - Governor Michael S. Barr", "ts": 1795028400.0},
]


def test_the_boards_speeches_are_rows_in_nasdaqs_words() -> None:
    got = cal.fed_speech_rows(FED, LO, HI)
    assert [(r["event"], r["date"], r["et"]) for r in got] == [
        ("FOMC Member Waller Speaks", "2026-11-10", "04:00"),
        ("FOMC Member Bowman Speaks", "2026-11-10", "15:30"),
        ("FOMC Chair Powell Testifies", "2026-11-12", "10:00"),
    ]
    assert all(r["score"] == 5 and r["country"] == "United States" for r in got)
    assert got[0]["note"] == "Economic Outlook" and got[0]["released"] is False
    # A speaker the rows already name at that minute is not listed twice.
    have = [{"utc": "2026-11-10T09:00:00+00:00", "event": "Fed Waller Speaks"}]
    rest = [r["event"] for r in cal.fed_speech_rows(FED, LO, HI, have)]
    assert rest == ["FOMC Member Bowman Speaks", "FOMC Chair Powell Testifies"]


# --- which feed is read --------------------------------------------------------------


class Feeds:
    """Stands in for `fetch`: Nasdaq's days and TradingView's week, each made to
    answer, serve the copy on disk, or fail."""

    def __init__(self) -> None:
        self.nasdaq = "live"
        self.tv = "live"
        self.asked: list[str] = []

    def __call__(self, url: str, **_kw: Any) -> FetchResult:
        if "nasdaq.com" in url:
            self.asked.append("nasdaq")
            body = json.dumps({"data": {"rows": [
                {"country": "United States", "eventName": "Retail Sales", "gmt": "08:30",
                 "actual": "", "consensus": "0.3%", "previous": "0.1%"}]}}).encode()
            return self._as(self.nasdaq, body, "HTTP 403")
        self.asked.append("tradingview")
        return self._as(self.tv, json.dumps(fixture()).encode(), "HTTP 502")

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
    monkeypatch.setattr(cal, "fetch", f)
    monkeypatch.setattr(cal, "_nasdaq_wait", 0.0)
    monkeypatch.setattr(cal, "_nasdaq_why", "")
    monkeypatch.setattr(cal, "_last_shift", None)
    monkeypatch.setattr(cal, "_source", "nasdaq")
    return f


TODAY = date(2026, 11, 10)


def test_nasdaq_is_the_calendar_while_it_answers(feeds: Feeds) -> None:
    rs, st = cal.collect(today=TODAY)
    assert cal.source() == "nasdaq" and st.ok and st.source == "live"
    assert "tradingview" not in feeds.asked
    assert {r["event"] for r in rs} == {"Retail Sales"}
    # And the Board's speeches are not added to a feed that lists them itself.
    assert cal.with_fed_speeches(rs, FED) is rs


def test_tradingview_takes_over_when_nasdaq_serves_only_its_copy(
        feeds: Feeds, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(cal.time, "time", lambda: clock[0])
    feeds.nasdaq = "stale"
    rs, st = cal.collect(today=TODAY)
    assert cal.source() == "tradingview"
    assert st.ok and st.source == "live" and st.error is None
    assert st.notes == ["TradingView's calendar: Nasdaq is not answering (HTTP 403)"]
    assert named(rs, "Core CPI m/m")["read"] == "hot"
    # The speeches TradingView does not list come from the Board's own calendar.
    full = cal.with_fed_speeches(rs, FED)
    assert len(full) == len(rs) + 3
    assert [r["ts"] for r in full] == sorted(r["ts"] for r in full)
    assert named(full, "FOMC Member Waller Speaks")["et"] == "04:00"

    # A host that is refusing is not asked again every ten minutes.
    del feeds.asked[:]
    clock[0] += 600
    cal.collect(today=TODAY)
    assert feeds.asked == ["tradingview"] and cal.source() == "tradingview"
    # Half an hour on it is asked once more, and when it answers it is the calendar again.
    del feeds.asked[:]
    clock[0] += cal.NASDAQ_RETRY_SEC
    feeds.nasdaq = "live"
    rs, st = cal.collect(today=TODAY)
    assert cal.source() == "nasdaq" and "tradingview" not in feeds.asked
    assert {r["event"] for r in rs} == {"Retail Sales"}


def test_with_neither_the_copy_on_disk_is_shown_and_says_how_old(feeds: Feeds) -> None:
    feeds.nasdaq, feeds.tv = "stale", "down"
    rs, st = cal.collect(today=TODAY)
    assert cal.source() == "nasdaq" and st.ok and st.source == "stale"
    assert st.error and "showing the copy from" in st.error
    assert {r["event"] for r in rs} == {"Retail Sales"}
    # And with no copy either, the calendar is down and says so.
    feeds.nasdaq = "down"
    cal._nasdaq_wait = 0.0
    rs, st = cal.collect(today=TODAY)
    assert rs == [] and st.ok is False


def test_one_slow_day_does_not_change_the_feed(feeds: Feeds,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    n = [0]
    real = feeds.__call__

    def one_bad(url: str, **kw: Any) -> FetchResult:
        n[0] += 1
        feeds.nasdaq = "stale" if n[0] == 4 else "live"
        return real(url, **kw)

    monkeypatch.setattr(cal, "fetch", one_bad)
    cal.collect(today=TODAY)
    assert cal.source() == "nasdaq" and "tradingview" not in feeds.asked
