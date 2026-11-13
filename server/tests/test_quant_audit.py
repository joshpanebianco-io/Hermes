"""
The quant audit of 2026-11-13, phase 1: what was wrong, each case kept.

The news grader scored one of twenty-three standard newswire headlines right; the
direction came from anybody's words in the title; the window lost after-close news
before the open and Friday's on a Monday; the pool scored yesterday's pre-market as
today's and called a level taken an outside day; the list ranked on a capped total.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import catalysts, holidays, scanscore
from newsterminal.sources import pool

ET = ZoneInfo("America/New_York")


def _h(title: str, age_min: float = 60.0) -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": "Reuters", "kind": "news"}


def pts(side: str, title: str, sym: str, names: list[str], tape: float | None = None,
        age_min: float = 60.0) -> int:
    """What the score pays the headline, the way the scanner reads it: held under the
    name first (catalysts.story, as news_for does), then the catalyst read."""
    if catalysts.story(title, sym, names, "Reuters", True) is None:
        return 0
    return int(scanscore.catalyst_read(side, None, [_h(title, age_min)], None, sym=sym,
                                       names=names, tape=tape)["pts"])


# ---- the grader on standard headlines ------------------------------------------------


@pytest.mark.parametrize(
    ("sym", "names", "title", "tag", "long_pts"),
    [
        # The name's own stated move is the market's verdict on the event's words.
        ("PLTR", ["Palantir"], "Palantir Stock Falls Despite Earnings Beat", "Earnings", -10),
        ("INTC", ["Intel"], "Intel Jumps After AMD Misses Estimates", "Earnings", 20),
        ("NVDA", ["Nvidia"], "Nvidia Revenue Soars 62% on AI Demand", "Move", 20),
        # A report with talk after it is the report.
        ("NVDA", ["Nvidia"], "Nvidia Beats Estimates, Here's What Wall Street Thinks",
         "Earnings", 20),
        ("PLTR", ["Palantir"], "Palantir Soars 20% After Earnings Beat. Should You Buy Now?",
         "Earnings", 20),
        # Equity raised, however it is written.
        ("ACME", ["Acme"], "Acme Announces $300 Million Public Offering of Common Stock",
         "Offering", -10),
        ("ACME", ["Acme"],
         "Acme Announces Proposed Offering of $500 Million Convertible Senior Notes",
         "Offering", -10),
        # Guidance, however it is written.
        ("ACME", ["Acme"], "Acme Raises 2026 Revenue Forecast", "Guidance", 20),
        ("ACME", ["Acme"], "Acme Cuts Annual Sales Forecast", "Guidance", -10),
        ("ACME", ["Acme"], "Acme Lowers Full-Year Outlook", "Guidance", -10),
        # The guidance came first; the notes followed it.
        ("LLY", ["Eli Lilly", "Lilly"], "Lilly Raises Guidance; Analysts Raise Price Targets",
         "Guidance", 20),
        # A buyer has no direction from the words; its target does.
        ("MRK", ["Merck"], "Merck to Buy Verona Pharma for $10 Billion", "Deal", 0),
        ("VRNA", ["Verona"], "Merck to Acquire Verona Pharma for $107 a Share", "Deal", 20),
        ("ITCI", ["Intra-Cellular"],
         "Johnson & Johnson to Acquire Intra-Cellular for $14.6 Billion", "Deal", 20),
        ("TSLA", ["Tesla"], "Tesla Recalls 2 Million Vehicles Over Autopilot", "Legal", -10),
        ("ACME", ["Acme"], "Acme Phase 3 Trial Meets Primary Endpoint", "FDA", 20),
        ("ACME", ["Acme"], "Acme Announces $5 Billion Share Buyback", "Buyback", 12),
        ("ACME", ["Acme"], "Acme Shares Jump on S&P 500 Inclusion", "Move", 20),
        ("ACME", ["Acme"], "Acme Set to Join S&P 500", "Index", 20),
        ("ACME", ["Acme"], "Acme CEO Steps Down Effective Immediately", "Exec", -6),
        ("ACME", ["Acme"], "Hindenburg Discloses Short Position in Acme", "Short", -10),
        ("MU", ["Micron"], "Bank of America Securities Upgrades Micron to Buy", "Analyst", 12),
        # A press release's figures are not a round-up of companies.
        ("ACME", ["Acme"], "Acme Corp. Reports Third Quarter 2026 Results: Revenue Up 20%, "
         "EPS $1.05, Raises Full-Year Guidance", "Guidance", 20),
        # Not a price move.
        ("INTC", ["Intel"], "Intel Drops Plans for Ohio Fab", "News", 0),
        # What was right stays right.
        ("ACME", ["Acme"], "Acme Beats Estimates and Raises Guidance", "Guidance", 20),
        ("MU", ["Micron"], "Micron Upgraded to Buy at Morgan Stanley", "Analyst", 12),
        ("ACME", ["Acme"], "Acme Plunges 18% After Guidance Cut", "Guidance", -10),
    ],
)
def test_standard_headlines_grade_and_point_the_right_way(
        sym: str, names: list[str], title: str, tag: str, long_pts: int) -> None:
    assert catalysts.grade(title).tag == tag
    assert pts("long", title, sym, names) == long_pts


def test_a_routine_dividend_is_noise_and_a_changed_one_is_news() -> None:
    assert catalysts.grade("Acme Declares Quarterly Dividend").tier == catalysts.NOISE
    assert catalysts.grade("Acme Declares Special Dividend of $2 a Share").tag == "Dividend"
    assert catalysts.grade("Acme Suspends Dividend").tier == catalysts.NOTABLE
    assert pts("long", "Acme Suspends Dividend", "ACME", ["Acme"]) == -6


def test_another_company_named_first_sets_no_direction() -> None:
    # Listed under Apple (it bears on it); not Apple's beat.
    t = "Apple Supplier Foxconn Beats Estimates"
    assert catalysts.about(t, "AAPL", ["Apple"]) is True
    assert pts("long", t, "AAPL", ["Apple"]) == 0


def test_an_analysts_action_after_the_joiner_still_counts() -> None:
    t = "Bernstein maintains Home Depot at Market Perform, raises price target to $357"
    assert pts("short", t, "HD", ["Home Depot"]) == -3


# ---- the tape has the last word -------------------------------------------------------


def test_words_the_tape_contradicts_are_set_aside() -> None:
    t = "Acme Beats Estimates"
    assert pts("long", t, "ACME", ["Acme"], tape=1.0) == 20
    # Down a full ATR against SPY on a "beat": the market has read it the other way.
    r = scanscore.catalyst_read("long", None, [_h(t)], None, sym="ACME", names=["Acme"], tape=-1.0)
    assert r["pts"] == 0 and "set aside, the tape disagrees" in r["note"]
    # Under TAPE_CLEAR the tape has not spoken and the words stand.
    assert pts("long", t, "ACME", ["Acme"], tape=-0.2) == 20


def test_a_story_with_no_direction_takes_the_tapes() -> None:
    t = "Acme Reports Third Quarter Results"
    assert pts("long", t, "ACME", ["Acme"], tape=0.8) == 20
    assert pts("short", t, "ACME", ["Acme"], tape=0.8) == -10
    r = scanscore.catalyst_read("long", None, [_h(t)], None, sym="ACME", names=["Acme"], tape=0.8)
    assert "its direction from the tape" in r["note"]
    # A minor story does not borrow the tape, and a quiet tape lends nothing.
    assert pts("long", t, "ACME", ["Acme"], tape=0.2) == 0


def test_the_report_surprise_is_checked_against_the_tape_too() -> None:
    beat = {"days": -1, "when": "after", "surprise_pct": 4.0}
    assert scanscore.catalyst_read("long", beat, [], None, tape=0.3)["pts"] == 20
    assert scanscore.catalyst_read("long", beat, [], None, tape=-1.2)["pts"] == 0


# ---- the news day ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "since"),
    [
        # Monday, Saturday, Tuesday, Tuesday evening after the roll.
        (datetime(2026, 11, 16, 8, 0, tzinfo=ET), datetime(2026, 11, 13, 15, 30, tzinfo=ET)),
        (datetime(2026, 11, 14, 12, 0, tzinfo=ET), datetime(2026, 11, 13, 15, 30, tzinfo=ET)),
        (datetime(2026, 11, 17, 10, 0, tzinfo=ET), datetime(2026, 11, 16, 15, 30, tzinfo=ET)),
        (datetime(2026, 11, 17, 21, 0, tzinfo=ET), datetime(2026, 11, 17, 15, 30, tzinfo=ET)),
        # Thanksgiving: the Friday after reads from Wednesday; the Monday after from the
        # half day's 13:00 close.
        (datetime(2026, 11, 27, 9, 0, tzinfo=ET), datetime(2026, 11, 25, 15, 30, tzinfo=ET)),
        (datetime(2026, 11, 30, 9, 0, tzinfo=ET), datetime(2026, 11, 27, 12, 30, tzinfo=ET)),
    ],
)
def test_the_news_day_starts_at_the_previous_close(now: datetime, since: datetime) -> None:
    assert holidays.news_since(now) == since


def test_the_window_reaches_back_to_the_previous_close() -> None:
    t = "Acme Raises Full-Year Outlook"
    old = 1000.0  # minutes: a 16:05 story read at 08:45 the next morning
    assert scanscore.catalyst_read("long", None, [_h(t, old)], None, sym="ACME",
                                   names=["Acme"])["pts"] == 0  # the old sixteen hours
    assert scanscore.catalyst_read("long", None, [_h(t, old)], None, sym="ACME", names=["Acme"],
                                   fresh_min=1035.0)["pts"] == 20


def test_mondays_last_night_is_fridays_evening() -> None:
    rows = [{"symbol": "ACME", "date": "2026-11-13", "when": "after", "surprise_pct": 6.0}]
    e = scanscore.earnings_for("ACME", rows, date(2026, 11, 16))
    assert e is not None and e["last_night"] and e["days"] == -3
    assert scanscore.catalyst_read("long", e, [], None)["pts"] == 20
    # And it outranks next week's report as the one that matters.
    rows.append({"symbol": "ACME", "date": "2026-11-18", "when": "pre"})
    assert scanscore.earnings_for("ACME", rows, date(2026, 11, 16))["date"] == "2026-11-13"


# ---- the pool ---------------------------------------------------------------------


def _row(sym: str = "X", **kw: Any) -> dict[str, Any]:
    base = {"symbol": sym, "close": 50.0, "change": 0.0, "volume": 1e6, "avg_vol": 1e6,
            "atr": 2.0, "cap": 3e9, "pm_change": 0.0, "pm_volume": 0.0, "pm_close": 50.0,
            "earn_next": None, "earn_last": None, "earn_last_when": None,
            "high": 51.0, "low": 49.0, "h1": 51.0, "l1": 49.0, "dollar_vol": 5e7,
            "atr_pct": 4.0, "delayed": True}
    return {**base, **kw}


def test_yesterdays_pre_market_is_not_todays() -> None:
    stale = _row("OLD", pm_close=55.0, pm_volume=2e6, pm_change=10.0)
    live = _row("NEW", pm_close=55.0, pm_volume=2e6, pm_change=10.0)
    seen = {"OLD": False, "NEW": True}
    rows = pool.fresh_premarket([stale, live], "pre", lambda s, c, v: seen[s])
    assert rows[0]["pm_close"] is None and rows[0]["pm_stale"]
    assert rows[1]["pm_close"] == 55.0
    ip = pool.in_play(rows[0], "pre", date(2026, 11, 16))
    assert ip["score"] == 0.0 and "no pre-market trade yet" in ip["reason"]
    # After the bell the pre-market is not read, so nothing is taken out.
    assert pool.fresh_premarket([stale], "day", lambda s, c, v: False)[0]["pm_close"] == 55.0


def test_an_unusual_move_passes_the_atr_gate_and_a_megacaps_usual_day_does_not() -> None:
    # A 1.2% ATR large cap, $600m traded today: up 6% on its report is in play...
    mover = _row("BIG", atr_pct=1.2, close=200.0, volume=3e6, change=6.0, dollar_vol=4e8)
    # ...and the same turnover on a quiet day is just its usual day.
    quiet = _row("BRK", atr_pct=1.0, close=200.0, volume=3e6, change=0.4, dollar_vol=6e8)
    assert [r["symbol"] for r in pool.qualify([mover, quiet], "day")] == ["BIG"]


def test_an_outside_day_is_both_ranges_after_the_open() -> None:
    both = _row("O", close=53.0, h1=51.0, l1=49.0, pm_high=52.0, pm_low=50.0)
    pd_only = _row("P", close=53.0, h1=51.0, l1=49.0, pm_high=54.0, pm_low=50.0)
    a = pool.in_play(both, "day", date(2026, 11, 16))
    b = pool.in_play(pd_only, "day", date(2026, 11, 16))
    assert a["outside"] and "outside day" in a["reason"]
    assert not b["outside"] and "through PDH" in b["reason"]
    assert round(a["score"] - b["score"], 1) == pool.W_OUTSIDE - pool.W_THROUGH
    # Before the bell the previous day's level alone decides.
    pre = pool.in_play(_row("Q", pm_close=53.0, high=51.0, low=49.0), "pre", date(2026, 11, 16))
    assert pre["outside"]


# ---- the rank ---------------------------------------------------------------------


def test_the_list_is_ranked_on_the_uncapped_score() -> None:
    def row(sym: str, raw: int) -> dict[str, Any]:
        return {"sym": sym, "ok": True, "score": {"total": min(100, raw), "raw": raw},
                "setup": {"entry": {"dist_atr": 0.5}}, "rs": {"SPY": 1.0}}

    # Both read 100; the one without the penalty eats it on the raw sum.
    rows = sorted([row("PENALISED", 101), row("CLEAN", 111)], key=scanscore.rank_key)
    assert [r["sym"] for r in rows] == ["CLEAN", "PENALISED"]


# ---- phase 3: the record ------------------------------------------------------------


def test_the_signal_log_keeps_what_the_catalyst_read() -> None:
    from newsterminal import scanlog

    cat = scanscore.catalyst_read("long", None, [_h("Acme Raises Full-Year Outlook")], None,
                                  sym="ACME", names=["Acme"], tape=0.9)
    sc = scanscore.score_row(
        {"lvl_state": 2, "rs": {"SPY": 0.9}, "rvol": 1.6, "range_used": 0.5,
         "setup": {"side": "long", "state": "retest", "level": "PMH", "lost_vwap": False,
                   "entry": {"kind": "PMH", "price": 1.0, "dist_atr": 0.1}}},
        {"bias": "long", "confirm": "confirm"}, None, None, None, catalyst=cat)
    news = scanlog.news_ctx(sc)
    assert news is not None
    assert (news["pts"], news["tag"], news["dir"], news["with"], news["src"]) == \
        (20, "Guidance", "bull", True, "words")
    assert news["fresh"] == 1 and news["set_aside"] == 0
    assert scanlog.news_ctx({"parts": []}) is None


def test_the_pool_writes_each_mark_and_the_days_outcome_once(tmp_path: Any) -> None:
    import json

    from newsterminal import scan

    store = pool.PoolStore(str(tmp_path / "pool.json"))
    store.day = "2026-11-16"
    store.basis = "pre"
    store.ranked = [{"symbol": "AAA", "score": 9.0, "gap_atr": 1.2},
                    {"symbol": "BBB", "score": 5.0}]
    store.promoted = [{"symbol": "AAA"}]
    store._log_mark("09:25", datetime(2026, 11, 16, 9, 25, tzinfo=ET))
    clock = scan.clock_at(datetime(2026, 11, 16, 21, 0, tzinfo=ET))
    rows = [{"symbol": "AAA", "close": 110.0, "change": 10.0, "high": 112.0, "low": 100.0,
             "atr": 4.0, "volume": 1e6, "avg_vol": 1e6}]
    store._log_outcome(clock, rows)
    store._log_outcome(clock, rows)  # once a day
    lines = [json.loads(x) for x in (tmp_path / "pool_marks.jsonl").read_text().splitlines()]
    assert [x["kind"] for x in lines] == ["mark", "outcome"]
    assert lines[0]["rows"][0] == {**lines[0]["rows"][0], "sym": "AAA", "promoted": True}
    assert lines[0]["rows"][1]["promoted"] is False
    assert lines[1]["day"] == "2026-11-16" and set(lines[1]["rows"]) == {"AAA"}


def test_a_place_in_a_ranking_is_not_a_price_move() -> None:
    # Live, 2026-11-13: this cost Apple's short ten as a major move "on" a reason.
    t = "Apple rises 26 places on the Roundtable 100"
    assert catalysts.moved(t, "AAPL", ["Apple"]) is None
    assert pts("short", t, "AAPL", ["Apple"]) == 0
    # A price move with a figure is still one.
    assert catalysts.moved("Apple rises 4% on iPhone demand", "AAPL", ["Apple"]) == "bull"
