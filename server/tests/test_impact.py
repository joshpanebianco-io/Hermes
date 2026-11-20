"""High impact news (impact.py): the Dashboard card's Today rows and headlines, on the shapes the
collector holds. The worked day is Thursday 19 Nov 2026 at 10:45 ET, the morning the card was
approved: jobless claims, two Fed speakers, WMT/BABA/NTES/PDD before the open, INTU and ROST
after, Anthropic's IPO, Japan's CPI that night."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from newsterminal import impact as im
from newsterminal.scan import ET

NOW = datetime(2026, 11, 19, 10, 45, tzinfo=ET)
T = NOW.timestamp()
DAY = "2026-11-19"


def cal(event: str, et: str, *, region: str = "us", country: str = "United States",
        score: int = 3, core: bool = True, released: bool = False, **kw: Any) -> dict[str, Any]:
    return {"event": event, "et": et, "date": DAY, "region": region, "country": country,
            "score": score, "core": core, "released": released, **kw}


CALENDAR = [
    cal("Initial Jobless Claims", "08:30", score=5, released=True, actual=203000.0,
        actual_raw="203K", consensus=197000.0, consensus_raw="197K", read="cold"),
    cal("FOMC Member Jefferson Speaks", "09:25"),
    cal("FOMC Member Barr Speaks", "14:15"),
    # Score 3 and not core: left out.
    cal("Natural Gas Storage", "10:30", core=False, released=True, actual=20.0),
    cal("Existing Home Sales", "10:00", score=4),                                 # due? no: past
    cal("CPI y/y", "18:30", region="apac", country="Japan", score=4),
    cal("Core CPI y/y", "18:30", region="apac", country="Japan", score=4, consensus=2.3),
    cal("CPI ex All Food and Energy m/m", "18:30", region="apac", country="Japan", score=4),
    cal("PPI m/m", "16:00", region="apac", country="Japan", score=3),            # under 4
    {**cal("Retail Sales m/m", "08:30", score=5), "date": "2026-11-20"},          # tomorrow
]

EARNINGS = [
    {"symbol": "WMT", "date": DAY, "when": "pre", "bellwether": True, "market_cap": 1e12,
     "eps_actual": "$0.65", "eps_forecast": "$0.64"},
    {"symbol": "BABA", "date": DAY, "when": "pre", "market_cap": 216e9,
     "eps_actual": "$1.21", "eps_forecast": "$1.62"},
    {"symbol": "PDD", "date": DAY, "when": "pre", "market_cap": 110e9,
     "eps_actual": None, "eps_forecast": "$2.78"},
    {"symbol": "INTU", "date": DAY, "when": "after", "market_cap": 84e9,
     "eps_actual": None, "eps_forecast": "$2.46"},
    {"symbol": "ROST", "date": DAY, "when": "after", "market_cap": 71e9},
    {"symbol": "KEYS", "date": DAY, "when": "after", "market_cap": 49e9},          # under $50bn
    {"symbol": "NVDA", "date": "2026-11-17", "when": "after", "bellwether": True,
     "market_cap": 3.7e12},                                                         # not today
]


def w(title: str, mins_ago: float, impact: str = "medium", category: str = "corp",
      publisher: str = "Reuters") -> dict[str, Any]:
    return {"title": title, "ts": T - mins_ago * 60, "impact": impact, "category": category,
            "publisher": publisher, "url": f"https://x/{abs(hash(title))}"}


WIRE = [
    w("Anthropic Raises $81 Billion in Biggest IPO Ever", 700),
    w("Anthropic’s Record-Breaking IPO: What Comes Next?", 170),
    w("Traders in new market bet on big IPO pop for Anthropic", 22),
    w("China Is Shut Out of Anthropic’s Blockbuster I.P.O.", 17, impact="low",
      category="markets"),
    w("Iran Keeps Up Unrelenting Attacks on Ships in the Strait of Hormuz", 13, "high", "geo",
      "NYT"),
    w("Putin defends his 'Yalta', as 3-way summit draws parallels", 20, "medium", "geo"),
    w("Dollar Has Further Scope to Rally as Fed Could Out-Hike Peers", 21, "medium", "policy",
      "WSJ"),
    w("US Initial Jobless Claims Unexpectedly Rise by 1,000", 70, "high", "macro", "Bloomberg"),
    w("US initial jobless claims unexpectedly rise, again", 65, "high", "macro"),  # same story
    w("Iran Intensifies Hormuz Tanker Attacks Just as Oil Prices Slide", 137, "high", "energy"),
    w("Putin Vows to Retaliate After Crimea Bridge Attacks", 96, "medium", "geo"),
    w("New attack on Crimea bridge: Russian official", 593, "high", "geo"),
    w("Trump Weighs New Strikes on Iran as Israel Presses for Action", 992, "high", "geo"),
    w("Mexican Peso Hits 17-Month Low as Fed Outlook Rattles Markets", 11, "medium", "markets"),
    w("Some company beats", 5, "medium", "corp"),
]


def test_today_in_time_order_with_each_kind() -> None:
    rows, covered = im.today_rows(CALENDAR, EARNINGS, WIRE, NOW)
    got = [(r["t"], r["kind"], r["line"], r["done"]) for r in rows]
    assert got == [
        ("08:30", "US data",
         "Initial Jobless Claims: 203K against 197K expected · reads cold", True),
        ("09:25", "Fed", "Fed's Jefferson spoke", True),
        ("Before", "Earnings", "WMT beat ($0.65 vs $0.64) · BABA missed ($1.21 vs $1.62) · "
                               "PDD (no figure yet)", True),
        ("Today", "IPO", "China Is Shut Out of Anthropic’s Blockbuster I.P.O. · "
                         "4 IPO stories in the last day", True),
        ("10:00", "US data", "Existing Home Sales · due", False),
        ("14:15", "Fed", "Fed's Barr speaks", False),
        ("After", "Earnings", "INTU, ROST report after the close", False),
        ("18:30", "Japan", "CPI, the headline and core", False),
    ]
    # The IPO's stories, the low-impact one too, are the row's and not headlines.
    assert "Traders in new market bet on big IPO pop for Anthropic" in covered


def test_after_the_close_a_report_says_how_it_did() -> None:
    late = [{**e, "eps_actual": "$2.50"} if e["symbol"] == "INTU" else e for e in EARNINGS]
    rows = im._reports(late, DAY)
    assert rows[1]["line"] == "INTU beat ($2.50 vs $2.46) · ROST report after the close"
    assert rows[1]["done"]
    assert im._money("($0.05)") == -0.05 and im._money("-") is None


def test_headlines_high_first_then_the_desks_one_a_story_newest_first() -> None:
    _, covered = im.today_rows(CALENDAR, EARNINGS, WIRE, NOW)
    heads = im.headlines(WIRE, T, skip=covered)
    assert [h["title"][:28] for h in heads] == [
        "Iran Keeps Up Unrelenting At",
        "Putin defends his 'Yalta', a",
        "Dollar Has Further Scope to ",
        "US initial jobless claims un",
        "Putin Vows to Retaliate Afte",
        "Iran Intensifies Hormuz Tank",
        "New attack on Crimea bridge:",
    ]
    # Older than 12 h, a medium market or company story, the older copy of a story, and
    # the IPO's: none of them.
    assert heads[0]["kind"] == "Geopolitics" and heads[0]["high"] and heads[0]["age_min"] == 13
    assert heads[2]["kind"] == "Policy" and not heads[2]["high"]
    assert heads[0]["t"] == "10:32"
    assert len(im.headlines(WIRE, T, limit=3)) == 3


def test_the_card_and_its_quiet_day() -> None:
    card = im.build(WIRE, CALENDAR, EARNINGS, NOW, live=False)
    assert set(card) == {"today", "heads", "live"} and card["live"] is False
    sat = datetime(2026, 11, 21, 11, 0, tzinfo=ET)
    assert im.build([], CALENDAR, EARNINGS, sat) == {"today": [], "heads": [], "live": True}


def test_a_release_in_many_rows_is_named_once() -> None:
    assert im._family(["GDP q/q", "GDP y/y"]) == "GDP"
    assert im._family(["Trade Balance"]) == "Trade Balance"
    assert im._family(["Tankan Index", "Tankan Outlook"]) == "Tankan Index and 1 more"


# The collector's expiry block on Fri 20 Nov 2026, monthly OpEx (expiry.py).
EXPIRY = {"today": "2026-11-20", "opex_week": True, "next": [
    {"key": "opex-2026-11", "date": "2026-11-20", "kind": "monthly", "label": "Monthly OpEx",
     "note": "Monthly options expire; the near book empties and the walls rebuild",
     "days": 0, "is_today": True},
    {"key": "eom-2026-11", "date": "2026-11-30", "kind": "month-end", "label": "Month end",
     "note": "Month-end rebalancing into the close", "days": 10, "is_today": False}]}


def test_an_expiry_is_a_row_on_its_day_and_done_from_the_close() -> None:
    fri = datetime(2026, 11, 20, 9, 40, tzinfo=ET)
    rows = im.expiry_rows(EXPIRY, fri)
    assert rows == [{"t": "Today", "sort": "15:59", "kind": "Expiry", "done": False,
                     "line": "Monthly OpEx: monthly options expire; the near book empties "
                             "and the walls rebuild"}]
    assert im.expiry_rows(EXPIRY, datetime(2026, 11, 20, 16, 5, tzinfo=ET))[0]["done"]
    # Not on its day, nothing: month end is ten days off.
    assert im.expiry_rows({"next": EXPIRY["next"][1:]}, fri) == []
    assert im.expiry_rows(None, fri) == []
    # On the card, in time order and before the reports after the close.
    today = im.build([], [], [], fri, expiry=EXPIRY)["today"]
    assert [r["kind"] for r in today] == ["Expiry"] and "sort" not in today[0]
