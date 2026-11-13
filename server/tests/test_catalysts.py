"""
How a headline is graded, what the score pays for it, and which story a row shows.

The examples in the first test are real headlines from Friday 6 Nov 2026's biggest
breakouts and the feeds behind them: the grade has to tell the cause of a move from
the analyst's note written after it.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    assert read("long", None, [_h("Y upgrades X to Buy")], None)["pts"] == 12
    assert read("long", None, [_h("X beats on revenue and raises full-year guidance")],
                None)["pts"] == 20
    # What used to earn nothing because it does not read like a rating.
    assert read("long", None, [_h("FDA approves X's new drug")], None)["pts"] == 20
    assert read("long", None, [_h("X to be acquired by Y for $4bn")], None)["pts"] == 20
    assert read("short", None, [_h("FDA rejects X's new drug")], None)["pts"] == 20


def test_major_news_against_costs_ten_a_note_six_and_a_tweak_three() -> None:
    read = scanscore.catalyst_read
    assert read("short", None, [_h("X price target raised to $50 by Y")], None)["pts"] == -3
    assert read("short", None, [_h("Y upgrades X to Buy")], None)["pts"] == -6
    assert read("short", None, [_h("X beats on revenue")], None)["pts"] == -10


def test_a_law_firms_notice_counts_for_nothing() -> None:
    title = "X Investors Have Opportunity to Join Fraud Investigation with SBS Law"
    # `investigat` is a bearish word, and this used to cost a long the full six.
    got = scanscore.catalyst_read("long", None, [_h(title)], None)
    assert got["pts"] == 0 and got["against"] is None


def test_the_strongest_item_decides_not_the_newest() -> None:
    items = [_h("Y raises X price target to $50", 10.0), _h("X misses on revenue", 300.0)]
    got = scanscore.catalyst_read("long", None, items, None)
    assert got["pts"] == -10 and "misses" in got["against"]


def test_a_move_is_major_with_its_reason_and_minor_without() -> None:
    g = catalysts.grade
    assert g("Broadcom Stocks Jump 8.21% as Investors Eye $21.7 Billion AI Revenue Guide"
             ) == ("Move", 1)
    assert g("Micron Rises 6% as Bulls Tout Its Bargain Valuation and Buyback Firepower"
             ) == ("Move", 1)
    assert g("Micron, FormFactor, Amkor, Teradyne, and Nvidia shares skyrocket, what you need to "
             "know") == ("Move", 3)
    # A rally into the report is a preview, and a tanker is not a tanking.
    assert g("CRWV Rallies Ahead Of Quarterly Report: Wells Fargo Calls CoreWeave 'Highest "
             "Quality' Firm") == ("Preview", 3)
    assert g("Saudi Oil Tanker Firm Crossing Hormuz With US Coordination") == ("News", 3)


# Real headlines from the Scanner at 03:20 ET on Tue 10 Nov 2026, the morning the rule
# was built, with the names the table calls each company.
@pytest.mark.parametrize(
    ("sym", "names", "title", "want", "move"),
    [("GOOGL", ["Alphabet", "Google"],
      "AMD Stock Rises On Google Cloud Deal, Wall Street Upgrade", False, None),
     ("AMD", ["AMD", "Advanced Micro"],
      "AMD Stock Rises On Google Cloud Deal, Wall Street Upgrade", True, "bull"),
     ("AMZN", ["Amazon"],
      "Dow Jones Soars 1,132 Points As Amazon, Tesla Rally, But Nvidia Dives; CPI Inflation "
      "Report Next", False, None),
     ("AVGO", ["Broadcom"],
      "Broadcom Stocks Jump 8.21% as Investors Eye $21.7 Billion AI Revenue Guide", True, "bull"),
     ("LITE", ["Lumentum"],
      "Marvell Sinks 36%, Lumentum Drops 31% on $115 Billion Deal: Is the Selloff Overdone?",
      True, "bear"),
     ("NVDA", ["Nvidia"],
      "Micron, FormFactor, Amkor, Teradyne, and Nvidia shares skyrocket, what you need to know",
      False, None),
     ("NVDA", ["Nvidia"], "Nvidia (NVDA) Stock Is Falling Today", True, "bear"),
     ("NVDA", ["Nvidia"], "Anthropic Prepares to Market IPO as Nvidia Scandal Stokes AI Jitters",
      False, None),
     ("META", ["Meta"],
      "Oklo Is Down 86% From Its High. Will Shares Soar When Meta's Reactor Comes Online?",
      False, None),
     ("MU", ["Micron"], "Bank of America upgrades Micron to Buy on HBM demand", True, None),
     ("MU", ["Micron"], "Earnings call transcript: Micron jumps on upbeat outlook", True, "bull"),
     ("AAPL", ["Apple"], "Shares of Apple fall as iPhone demand cools", True, "bear"),
     ("AAPL", ["Apple"], "Apple supplier Foxconn shares jump after record quarter", True, None),
     ("TSLA", ["Tesla"],
      "Overall Tesla China Sales Rise 10%, Sales Inside China Sink To 4-Year Low; Robotaxi "
      "Launches", True, None),
     # A one-letter ticker is only $A or (A); a story that names the company nowhere is None.
     ("A", ["Agilent"], "A new era for chips as Nvidia opens a probe", None, None),
     ("SPCX", ["SpaceX"],
      "RKLB Stock Tumbles Over 8% Overnight as Neutron Delays Overshadow Record Revenue",
      None, None)],
)
def test_whose_story_it_is_and_which_way_it_moved(sym: str, names: list[str], title: str,
                                                  want: bool | None, move: str | None) -> None:
    assert catalysts.about(title, sym, names) is want
    assert catalysts.moved(title, sym, names) == move


def test_the_score_reads_the_names_own_move() -> None:
    read = scanscore.catalyst_read
    jump = _h("Broadcom Stocks Jump 8.21% as Investors Eye $21.7 Billion AI Revenue Guide")
    assert read("long", None, [jump], None, sym="AVGO", names=["Broadcom"])["pts"] == 20
    assert read("short", None, [jump], None, sym="AVGO", names=["Broadcom"])["pts"] == -10
    # Without the name to find, the move has no direction, as before.
    assert read("long", None, [jump], None)["pts"] == 0
    # A bare list of movers is minor: three with the side.
    lst = _h("Micron, Nvidia shares skyrocket, what you need to know")
    assert read("long", None, [lst], None, sym="NVDA", names=["Nvidia"])["pts"] == 3
    # "Stocks rise" is a market wrap until the name is known to lead it (live, AMZN at
    # 04:20 ET on 2026-11-10: it cost a short three as a List, and it is Amazon's move).
    wrap = _h("Amazon Stocks Rise 4.05% as JPMorgan Adds It to Focus List on AWS")
    assert catalysts.grade(wrap["title"]) == ("List", 3)
    assert read("short", None, [wrap], None, sym="AMZN", names=["Amazon"])["pts"] == -10
    assert read("short", None, [wrap], None)["pts"] == 0
    assert read("short", None, [_h("Asian Stocks Rise as Oil Eases")], None, sym="AMZN",
                names=["Amazon"])["pts"] == 0


def test_the_rows_list_drops_another_companys_story() -> None:
    now = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    own = [{"title": "AMD Stock Rises On Google Cloud Deal, Wall Street Upgrade",
            "ts": now.timestamp() - 600, "url": "u1", "publisher": "Yahoo Finance"},
           {"title": "Google Cloud signs AMD for its next AI chips",
            "ts": now.timestamp() - 900, "url": "u2", "publisher": "Reuters"}]
    got = scanscore.news_for("GOOGL", own, [], ["Alphabet", "Google"], now)
    assert [h["title"] for h in got] == ["Google Cloud signs AMD for its next AI chips"]
    # AMD keeps both: it leads the first, and the second names it in its first words.
    assert len(scanscore.news_for("AMD", own, [], ["AMD", "Advanced Micro"], now)) == 2
    assert scanscore.names_of(["Broadcom"], ["Broadcom", "BROADCOM"]) == ["Broadcom", "BROADCOM"]


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
    # Past the day's window it no longer counts: by Tuesday afternoon a Friday-evening
    # story is two sessions old. (On the Sunday between it still counts: it is Monday's
    # news, the session since Friday's close — holidays.news_since, 2026-11-13.)
    assert tvnews.best(rows, "IRTC", NOW + 4 * 86400) is None
    assert tvnews.best(rows, "IRTC", NOW + 40 * 3600) is not None


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


def test_a_story_tagged_with_two_names_is_the_one_it_leads_with() -> None:
    rows = tvnews.parse({"items": [
        _item("AMD Stock Rises On Google Cloud Deal, Wall Street Upgrade", NOW - 600,
              ["AMD", "GOOGL"]),
    ]})
    assert tvnews.best(rows, "AMD", NOW, names=["AMD"]) is not None
    assert tvnews.best(rows, "GOOGL", NOW, names=["Alphabet", "Google"]) is None
    # With no name to go by, the tag stands.
    assert tvnews.best(rows, "GOOGL", NOW) is not None
    store = tvnews.NewsStore(path="nul")
    store.stories, store.by_sym = {}, {}
    store._add(rows, NOW)
    store.names = {"GOOGL": ["Alphabet", "Google"], "AMD": ["AMD"]}.get
    assert store.catalyst("GOOGL", NOW) is None
    assert store.catalyst("AMD", NOW) is not None


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


# ---- the audit of 2026-11-11 -----------------------------------------------------------
# Real headlines from the Scanner on the evening of Tue 10 Nov 2026. Six of the twenty
# rows the catalyst had scored were misread; each case below is one of those, or a
# headline that must still read as it did.


@pytest.mark.parametrize(
    ("title", "tag", "tier"),
    [
     # A preview is talk about a report that has not happened.
     ("Will Broadcom Inc. (AVGO) Beat Estimates Again in Its Next Earnings Report?", "Preview", 3),
     ("Home Depot (HD) Reports Next Week: Wall Street Expects Earnings Growth", "Preview", 3),
     ("HD Q3'26 Earnings: revenue estimate is 42.79B USD", "Preview", 3),
     # An opinion is somebody asking what to do.
     ("ARM Just Dropped 13% After Earnings. Is It Time to Sell, or Load Up?", "Opinion", 3),
     ("Apple Inc. (AAPL) Rallied 15% as Investors Reassessed Its Growth: What’s Next for the "
      "Stock?", "Opinion", 3),
     ("Oklo Is Down 86% From Its High. Will Shares Soar When Meta's Reactor Comes Online?",
      "Opinion", 3),
     ("Can Home Depot Sustain Comparable Sales Growth Amid Uneven Demand?", "Opinion", 3),
     # A digest is nobody's news.
     ("Zacks Industry Outlook Highlights Union Pacific, CSX and Norfolk Southern", "List", 3),
     ("AM Markets Need to Know: Huang faces FBI probe, Anthropic IPO plans, and more", "List", 3),
     ("Here's Why Oracle (ORCL) Fell More Than Broader Market", "List", 3),
     # A move over a week or a month is a recap.
     ("Oklo Soars 14% in a Week on a Narrower Loss and a Deal for 27 Reactors’ Worth of "
      "Forgings", "Recap", 3),
     ("Dell Sinks 12% in a Week on Texas Data Center Fears: “A Moratorium, a Ban”", "Recap", 3),
     ("Why Netflix Stock Plunged 11% in October", "Recap", 3),
     # When is not why.
     ("Why Sandisk Stock Dropped Again on Tuesday", "Move", 3),
     # An upgrade is an analyst's only in an analyst's sentence.
     ("Home Depot brings back viral Christmas tree with major holiday upgrade", "News", 3),
     ("Apple upgrades Siri with Gemini", "News", 3),
     ("Tesla stock jumps after software upgrade rollout", "Move", 1),
     ("AMD Stock Just Got Massive Upgrade From Oppenheimer", "Analyst", 2),
     ("Coinbase upgraded despite earnings miss", "Analyst", 2),
     ("A new chip initiative from Intel", "News", 3),
     ("Goldman initiates coverage on Micron with Buy", "Analyst", 2),
     # And what was right stays right: the day's own moves, with their reasons.
     ("Microsoft Stock Falls On Anthropic Challenge To Office Software", "Move", 1),
     # The event by name since 2026-11-13: a convertible is an offering (major either way,
     # and the stock's own fall still sets its direction).
     ("Dropbox stock falls after pricing $1.1B convertible notes", "Offering", 1),
     ("GE Vernova falls nearly 10% after SoftBank revises AI data center plans", "Move", 1),
     ("Amazon Stock Climbs as Ring Unveils a Security Drone That Flies Around Your Home",
      "Move", 1),
     ("Coinbase Falls 4%, Robinhood Slides 3% as Hot Inflation Data Drags Bitcoin Lower; Webull "
      "Declines 2%", "Move", 1),
     ("Marvell Sinks 36%, Lumentum Drops 31% on $115 Billion Deal: Is the Selloff Overdone?",
      "Move", 1),
     ("Micron jumps as it guides revenue above estimates this quarter", "Move", 1),
     ("CoreWeave beats on revenue and lifts guidance, easing AI slowdown concerns", "Guidance", 1),
     ("Trade Desk Q3 Earnings & Revenues Beat Estimates, Down Y/Y", "Earnings", 1),
    ],
)
def test_grade_on_the_evening_of_10_nov(title: str, tag: str, tier: int) -> None:
    assert catalysts.grade(title) == (tag, tier)


def test_a_full_stop_after_inc_does_not_end_the_lead() -> None:
    title = "Apple Inc. (AAPL) Rallied 15% as Investors Reassessed Its Growth"
    assert catalysts.lead(title, "AAPL", ["Apple"]) == ["Apple Inc. (AAPL) Rallied 15%"]
    assert catalysts.moved(title, "AAPL", ["Apple"]) == "bull"
    # A real sentence break still ends it.
    two = "The AI Trade Looks Like It's Falling Apart. AMD's Earnings Could Save It"
    assert catalysts.about(two, "AMD", ["AMD"]) is False


def test_an_analysts_note_is_about_the_company_it_is_written_on() -> None:
    note = "Cantor Fitzgerald reiterates buy rating on Strategy with $208 target"
    assert catalysts.about(note, "MSTR", ["MicroStrategy", "Strategy"]) is True
    assert catalysts.about("Citi raises price target on Apple to $400", "AAPL", ["Apple"]) is True
    # Not every "on": a deal with the name in it is still the other company's story.
    assert catalysts.about("AMD Stock Rises On Google Cloud Deal, Wall Street Upgrade", "GOOGL",
                           ["Alphabet", "Google"]) is False
    # A short name is matched as written: "Arm" the company, not somebody's arm.
    assert catalysts.about("Arm shares jump on record royalty revenue", "ARM",
                           ["Arm Holdings", "Arm"]) is True
    assert catalysts.about("Blackstone's lending arm raises $2bn", "ARM",
                           ["Arm Holdings", "Arm"]) is None


def test_the_score_on_the_evening_of_10_nov() -> None:
    read = scanscore.catalyst_read

    def pts(side: str, title: str, sym: str, names: list[str]) -> int:
        return int(read(side, None, [_h(title)], None, sym=sym, names=names)["pts"])

    # A preview and an opinion have no direction: twenty and twenty before.
    assert pts("long", "Will Broadcom Inc. (AVGO) Beat Estimates Again in Its Next Earnings "
               "Report?", "AVGO", ["Broadcom"]) == 0
    assert pts("short", "ARM Just Dropped 13% After Earnings. Is It Time to Sell, or Load Up?",
               "ARM", ["Arm Holdings", "Arm"]) == 0
    # The day is not the reason: twenty before, a bare move's three now.
    assert pts("long", "Why AMD shares are rallying on Tuesday?", "AMD", ["AMD"]) == 3
    # A recap of the week is minor: it cost the short ten.
    assert pts("short", "Oklo Soars 14% in a Week on a Narrower Loss and a Deal for 27 "
               "Reactors’ Worth of Forgings", "OKLO", ["Oklo"]) == -3
    # A product's upgrade is not a rating: it cost the short six.
    assert pts("short", "Home Depot brings back viral Christmas tree with major holiday upgrade",
               "HD", ["HOME"]) == 0
    # The bidder is not the target: it cost the short ten.
    assert pts("short", "Australia's IDP Education mulls Blackstone's revised $571 million "
               "takeover offer", "BX", ["Blackstone"]) == 0
    # A story that never names the company is somebody else's: it cost SpaceX ten and
    # paid a Netflix short three.
    assert pts("long", "Huang faces FBI probe as Nvidia board opens investigation", "SPCX",
               ["SpaceX"]) == 0
    assert pts("short", "Trade Desk's Jeff Green Says Growth Still Falls Short", "NFLX",
               ["Netflix"]) == 0
    # A name the table has no words for is still left to its feed.
    assert pts("long", "FDA approves the company's new drug", "ZZZZ", []) == 20
    # And the day's real news pays as it did.
    assert pts("short", "Microsoft Stock Falls On Anthropic Challenge To Office Software",
               "MSFT", ["Microsoft"]) == 20
    assert pts("long", "AMD Stock Just Got Massive Upgrade From Oppenheimer", "AMD", ["AMD"]) == 12
    assert pts("long", "CoreWeave beats on revenue and lifts guidance, easing AI slowdown "
               "concerns", "CRWV", ["CoreWeave"]) == 20
    assert pts("long", "Organigram to be acquired by Aurora", "OGI", ["Organigram"]) == 20
    assert pts("short", "Bernstein maintains Home Depot at Market Perform, raises price target "
               "to $357 from $344", "HD", ["HOME"]) == -3


def test_a_stored_story_is_graded_again_when_it_is_loaded(tmp_path: Any) -> None:
    import json as _json
    import time as _time
    # Stamped now, not NOW: the store drops what is over five days old against the real
    # clock as it loads, and with the fixed stamp this test went red on 11 Nov 2026, the
    # day that date turned five days old.
    now = _time.time()
    path = tmp_path / "news.json"
    path.write_text(_json.dumps({"stories": [
        {"id": "a", "title": "Will Broadcom Inc. (AVGO) Beat Estimates Again in Its Next "
                             "Earnings Report?", "at": now, "syms": ["AVGO"],
         "tag": "Earnings", "tier": 1, "url": "", "provider": ""},
        {"id": "b", "title": "X Investors Have Opportunity to Join Fraud Investigation",
         "at": now, "syms": ["X"], "tag": "Legal", "tier": 1, "url": "", "provider": ""},
    ]}), encoding="utf-8")
    store = tvnews.NewsStore(path=str(path))
    store._reindex(now)
    assert [(s["id"], s["tag"], s["tier"]) for s in store.stories.values()] == [("a", "Preview", 3)]
