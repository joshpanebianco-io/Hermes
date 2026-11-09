"""
How a headline is graded, what the score pays for it, and which story a row shows.

The examples in the first test are real headlines from Friday 6 Nov 2026's biggest
breakouts and the feeds behind them: the grade has to tell the cause of a move from
the analyst's note written after it.
"""

from __future__ import annotations

from typing import Any

import pytest

from newsterminal import catalysts, scanscore
from newsterminal.sources import pool, tvnews


@pytest.mark.parametrize(
    ("title", "tag", "tier"),
    [("iRhythm plunges after Q3 miss, Zio MCT delay", "Earnings", 1),
     ("Axon sinks to lowest in two years after Q3 miss, sales guidance cut on Dedrone deployment "
      "delays", "Guidance", 1),
     ("Axon Stock Plunges as Delayed Drone Deals Hit Revenue — Barrons.com", "Move", 1),
     ("TransMedics posts record intraday rally on 'solid Q3 print'", "Earnings", 1),
     ("Riot Platforms Reports Third Quarter 2026 Financial Results", "Earnings", 1),
     ("Sanofi says FDA approves its new asthma drug", "FDA", 1),
     ("Organigram to Acquire Aurora and Establish a Global Cannabis Leader", "Deal", 1),
     ("Palantir announces secondary offering of 12m shares", "Offering", 1),
     ("iRhythm Holdings Cut to Neutral From Buy by Citigroup", "Analyst", 2),
     ("Morgan Stanley upgrades AMD to Overweight", "Analyst", 2),
     ("Ardent Health Price Target Raised to $21.00/Share From $13.00 by Stephens & Co.",
      "Target", 3),
     ("Stephens & Co. maintains Ardent Health at Overweight, raises price target to $21 from $13",
      "Target", 3),
     ("What to expect from Grocery Outlet's (GO) Q3 earnings", "Preview", 3),
     ("12 Industrials Stocks Moving In Friday's Intraday Session", "List", 3),
     ("Bulls And Bears: Palantir, IonQ, DraftKings", "List", 3),
     ("PCT Investors Have Opportunity to Join PureCycle Technologies, Inc. Fraud Investigation "
      "with SBS Law", "Notice", 0),
     ("Dan Ives Warns of a Stock Overhang", "News", 3)],
)
def test_grade(title: str, tag: str, tier: int) -> None:
    assert catalysts.grade(title) == (tag, tier)


def _h(title: str, age_min: float = 90.0) -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": "Reuters", "kind": "news"}


def test_the_score_pays_for_what_the_news_is() -> None:
    read = scanscore.catalyst_read
    # The same twelve as a beat, before: now a tweak earns three.
    assert read("long", None, [_h("X price target raised to $50 by Y")], None)["pts"] == 3
    assert read("long", None, [_h("Y upgrades X to Buy")], None)["pts"] == 8
    assert read("long", None, [_h("X beats on revenue and raises full-year guidance")],
                None)["pts"] == 12
    # What used to earn nothing because it does not read like a rating.
    assert read("long", None, [_h("FDA approves X's new drug")], None)["pts"] == 12
    assert read("long", None, [_h("X to be acquired by Y for $4bn")], None)["pts"] == 12
    assert read("short", None, [_h("FDA rejects X's new drug")], None)["pts"] == 12


def test_the_penalty_stays_but_a_minor_note_costs_less() -> None:
    read = scanscore.catalyst_read
    assert read("short", None, [_h("X price target raised to $50 by Y")], None)["pts"] == -3
    assert read("short", None, [_h("Y upgrades X to Buy")], None)["pts"] == -6
    assert read("short", None, [_h("X beats on revenue")], None)["pts"] == -6


def test_a_law_firms_notice_counts_for_nothing() -> None:
    title = "X Investors Have Opportunity to Join Fraud Investigation with SBS Law"
    # `investigat` is a bearish word, and this used to cost a long the full six.
    got = scanscore.catalyst_read("long", None, [_h(title)], None)
    assert got["pts"] == 0 and got["against"] is None


def test_the_strongest_item_decides_not_the_newest() -> None:
    items = [_h("Y raises X price target to $50", 10.0), _h("X misses on revenue", 300.0)]
    got = scanscore.catalyst_read("long", None, items, None)
    assert got["pts"] == -6 and "misses" in got["against"]


def _item(title: str, at: float, syms: list[str]) -> dict[str, Any]:
    return {"id": f"{title[:8]}{at}", "title": title, "published": at, "storyPath": "/news/x",
            "provider": {"name": "Dow Jones"},
            "relatedSymbols": [{"symbol": f"NASDAQ:{s}"} for s in syms]}


NOW = 1_794_000_000.0


def test_the_story_shown_is_the_most_important_of_the_day_not_the_newest() -> None:
    rows = tvnews.parse({"items": [
        _item("iRhythm Holdings Cut to Neutral From Buy by Citigroup", NOW - 600, ["IRTC"]),
        _item("iRhythm plunges after Q3 miss, Zio MCT delay", NOW - 3 * 3600, ["IRTC"]),
        _item("iRhythm price target cut to $110", NOW - 300, ["IRTC"]),
    ]})
    got = tvnews.best(rows, "IRTC", NOW)
    assert got is not None and got["title"].startswith("iRhythm plunges")
    assert got["tag"] == "Earnings"
    # Past the day's window it no longer counts.
    assert tvnews.best(rows, "IRTC", NOW + 40 * 3600) is None


def test_the_window_is_counted_back_from_the_session_on_the_page() -> None:
    store = tvnews.NewsStore(path="nul")
    store.stories, store.by_sym = {}, {}
    fri = NOW
    store._add(tvnews.parse({"items": [_item("IRTC plunges after Q3 miss", fri - 3600, ["IRTC"])]}),
               fri + 2 * 86400)
    sunday = fri + 2 * 86400
    # Two days on, it is out of the last thirty hours measured from now...
    assert store.catalyst("IRTC", sunday) is None
    # ...and the story of the session on the page, measured from that session.
    got = store.catalyst("IRTC", sunday, ref=fri)
    assert got is not None and got["major"] and got["tag"] == "Earnings"
    assert got["age_min"] == pytest.approx((2 * 86400 + 3600) / 60.0)


def test_the_dashboards_feed_tells_one_event_once() -> None:
    store = tvnews.NewsStore(path="nul")
    store.stories, store.by_sym = {}, {}
    store._add(tvnews.parse({"items": [
        _item("Children's Place Files Chapter 11", NOW - 900, ["PLCE"]),
        _item("Children's Place Files Chapter 11, Seeks Sale", NOW - 600, ["PLCE"]),
        _item("Children's Place Q3 earnings miss estimates", NOW - 700, ["PLCE"]),
        _item("iRhythm plunges after Q3 miss", NOW - 800, ["IRTC"]),
    ]}), NOW)
    got = [(s["syms"], s["tag"], s["title"]) for s in store.top(now=NOW)]
    assert got == [(["PLCE"], "Legal", "Children's Place Files Chapter 11, Seeks Sale"),
                   (["PLCE"], "Earnings", "Children's Place Q3 earnings miss estimates"),
                   (["IRTC"], "Earnings", "iRhythm plunges after Q3 miss")]
    assert len(store.top(limit=1, now=NOW)) == 1


def test_a_round_up_is_not_a_names_news_and_noise_is_dropped() -> None:
    rows = tvnews.parse({"items": [
        _item("Q3 earnings winners and losers", NOW, ["A", "B", "C", "D", "E"]),
        _item("A Investors Have Opportunity to Join Fraud Investigation", NOW, ["A"]),
    ]})
    assert len(rows) == 1  # the notice never enters the store
    assert tvnews.best(rows, "A", NOW) is None


def test_only_us_listings_are_tagged() -> None:
    item = {"relatedSymbols": [{"symbol": "NASDAQ:AAPL"}, {"symbol": "TSE:7203"},
                               {"symbol": "NYSE:BRK.B"}, {"symbol": "oops"}, "bad"]}
    assert tvnews.tickers_of(item) == ["AAPL", "BRK.B"]


def test_a_fresh_major_story_is_worth_three_to_the_pool() -> None:
    row = {"symbol": "X", "close": 100.0, "atr": 2.0, "avg_vol": 1e6, "pm_close": 100.8,
           "pm_volume": 0.0}
    td = __import__("datetime").date(2026, 11, 9)
    without = pool.in_play(row, "pre", td)
    with_news = pool.in_play(row, "pre", td, news=lambda _s: "Deal")
    assert with_news["score"] == pytest.approx(without["score"] + pool.W_NEWS)
    assert "deal news" in with_news["reason"]
    # News alone does not put a name in play: the tape has to care.
    still = {"symbol": "X", "close": 100.0, "atr": 2.0, "avg_vol": 1e6, "pm_close": 100.0,
             "pm_volume": 0.0}
    assert pool.in_play(still, "pre", td, news=lambda _s: "Deal")["score"] < pool.MIN_SCORE
    # A report earns its own points, and a story about it is not paid twice.
    rep = {**still, "earn_next": "2026-11-09"}
    assert pool.in_play(rep, "pre", td, news=lambda _s: "Earnings")["score"] == pool.W_REPORT
