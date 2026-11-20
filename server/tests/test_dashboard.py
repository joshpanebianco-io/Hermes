"""
The Dashboard's words and its page, worked with Friday 6 November 2026's real figures.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from newsterminal import dashboard as d

FRI = date(2026, 11, 6)


def regime(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"band": "stressed", "bias": "long",
                            "vix": {"last": 25.64, "shape": "backwardation"},
                            "conviction": {"bias": "long", "score": 100, "grade": "moderate",
                                           "live": 2, "total": 11, "max_conviction": 4},
                            "event": None}
    base.update(kw)
    return base


TECH = [{"key": "XLK", "label": "Technology"}]
MINERS = [{"key": "WGMI", "label": "Bitcoin Miners"}]
WIDE = {"advancers": 968, "decliners": 1034}


def test_fridays_read_in_words() -> None:
    assert d.read_lines(regime(), TECH, MINERS, WIDE, "closed", FRI) == [
        "Tape leans long, but VIX 25.6 is stressed and the curve is inverted: cut size or sit out.",
        "Technology and Bitcoin Miners led Friday; breadth is split (968 up, 1,034 down). "
        "Stay selective.",
    ]


@pytest.mark.parametrize(
    ("band", "shape", "words", "caution"),
    [("stressed", "backwardation",
      "VIX 30.0 is stressed and the curve is inverted: cut size or sit out", True),
     ("stressed", "contango", "VIX 30.0 is stressed: cut size or sit out", True),
     ("elevated", "contango",
      "VIX 30.0 is elevated: moves extend then whip back, so size down", True),
     ("normal", "contango", "VIX 30.0 is normal", False),
     ("grind", "contango", "VIX 30.0 is low: small ranges, so a breakout needs proof", False)],
)
def test_what_each_band_says(band: str, shape: str, words: str, caution: bool) -> None:
    assert d.weather_words(30.0, band, shape) == (words, caution)


def test_no_vix_is_said_rather_than_guessed() -> None:
    assert d.weather_words(None, None, None) == ("the VIX has not been read yet", False)


@pytest.mark.parametrize(
    ("adv", "dec", "word"),
    [(968, 1034, "split"), (1500, 1000, "broad"), (1499, 1000, "split"), (600, 900, "weak"),
     (0, 0, "split"), (3, 0, "broad")],
)
def test_breadth_in_a_word(adv: int, dec: int, word: str) -> None:
    assert d.breadth_word(adv, dec) == word


def test_the_tense_follows_the_session() -> None:
    rth = d.read_lines(regime(), TECH, MINERS, WIDE, "rth", date(2026, 11, 9))[1]
    post = d.read_lines(regime(), TECH, [], WIDE, "post", date(2026, 11, 9))[1]
    pre = d.read_lines(regime(), TECH, [], WIDE, "pre", FRI)[1]
    assert rth.startswith("Technology and Bitcoin Miners are leading today;")
    assert post.startswith("Technology led today;")
    assert pre.startswith("Technology led Friday;")
    assert d.read_lines(regime(), [], [], {}, "rth", FRI)[1] == "Nothing beat SPY today."


def test_stay_selective_only_when_breadth_will_not_carry_the_lean() -> None:
    broad = {"advancers": 2000, "decliners": 500}
    weak = {"advancers": 500, "decliners": 2000}
    short = regime(conviction={"bias": "short"})
    assert "Stay selective" not in d.read_lines(regime(), TECH, [], broad, "rth", FRI)[1]
    assert "Stay selective" in d.read_lines(regime(), TECH, [], weak, "rth", FRI)[1]
    assert "Stay selective" in d.read_lines(short, TECH, [], broad, "rth", FRI)[1]
    assert "Stay selective" not in d.read_lines(short, TECH, [], weak, "rth", FRI)[1]


def test_no_lean_says_so() -> None:
    calm = regime(conviction={"bias": None}, bias=None, band="normal",
                  vix={"last": 17.2, "shape": "contango"})
    assert d.read_lines(calm, [], [], {}, "closed", FRI)[0] == (
        "No lean from the tape; VIX 17.2 is normal.")


def row(sym: str, total: int = 0, side: str | None = None, chg: float = 1.0,
        **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"sym": sym, "ok": True, "score": {"total": total, "side": side,
                                                              "parts": [{"key": "heavy"}]},
                            "chg_pct": chg, "last": 10.0, "ext_pct": None, "levels": {},
                            "broken": {}, "setup": {}, "news": ["heavy"]}
    base.update(kw)
    return base


def sector(key: str, label: str, day: float | None, rs: float | None) -> dict[str, Any]:
    return {"key": key, "label": label, "day_pct": day, "rs_day": rs}


def page(**kw: Any) -> dict[str, Any]:
    scan: dict[str, Any] = {
        "session": "closed", "trading_day": "2026-11-09", "regime": regime(),
        "rows": [row("SPCX", 40, "long", 8.62), row("COIN", 27, "short", -1.51),
                 row("HOOD", 26, "short", 3.21, ok=False), row("AAPL", 0, None, -0.52),
                 row("ADD", 12, "long", 4.0, promoted={"symbol": "ADD"})],
        "pinned": ["AAPL", "SPCX", "GONE"],
    }
    scan.update(kw.pop("scan", {}))
    snap: dict[str, Any] = {
        "sectors": [sector("SPY", "S&P 500", 0.31, 0.0), sector("RSP", "Equal", 0.5, 0.19),
                    sector("XLK", "Technology", 1.45, 1.14),
                    sector("XLC", "Communication", 0.43, 0.12),
                    sector("XLE", "Energy", None, None), sector("XLP", "Staples", -1.28, -1.59)],
        "themes": [sector("SPY", "S&P 500", 0.31, 0.0),
                   sector("WGMI", "Bitcoin Miners", 10.49, 10.18),
                   sector("XHB", "Homebuilders", -1.5, -1.81)],
        "breadth_all": {"advancers": 968, "decliners": 1034, "names": 2002, "basis": "last",
                        "floor": 2e9, "buckets": [],
                        "leaders": {"XLK": {"up": [{"sym": "FROG", "chg": 35.3}], "down": []}}},
        "earnings": [{"symbol": "OXY", "date": "2026-11-09", "when": "after", "market_cap": 5e10},
                     {"symbol": "B", "date": "2026-11-09", "when": "pre", "market_cap": 3e10},
                     {"symbol": "KKR", "date": "2026-11-09", "when": "pre", "market_cap": 1e11},
                     {"symbol": "PBR", "date": "2026-11-10", "when": "after", "market_cap": 9e10}],
        "status": {"stock_news": {"ok": True}},
    }
    snap.update(kw.pop("snap", {}))
    brk = {"stats": {"pdh": 41, "pdl": 34}}
    d23 = {"chips": {"all": 32, "day1": 11, "day2": 21, "day3": 2}}
    return d.build(scan, snap, brk, d23, [{"syms": ["IRTC"], "title": "x"}], session_day=FRI,
                   pre_day=kw.pop("pre_day", None))


MON = "2026-11-16"


def pre(pct: float, day: str = MON) -> dict[str, Any]:
    return {"kind": "pre", "day": day, "pct": pct, "at": 1, "bars": 5}


EXT = {"SPY": pre(-0.65), "XLP": pre(0.60), "XLK": pre(-1.76), "XLE": pre(-0.23),
       "XHB": pre(0.10), "WGMI": pre(-4.38), "XLC": pre(0.5, "2026-11-13")}


def test_before_the_bell_the_focus_and_the_rotation_are_the_pre_markets() -> None:
    # Owner, 2026-11-16: "is todays game plan on the dash board up to date? or is it
    # suffering the problem we fixed earlier with sectors" — it was: Friday's leaders.
    p = page(snap={"sector_ext": EXT}, pre_day=MON)
    assert p["sectors_basis"] == "pre"
    # Ahead of SPY's -0.65% before the bell, best first; XLC's read is Friday's, not today's.
    assert [f["key"] for f in p["plan"]["focus"]] == ["XLP", "XLE"]
    assert p["plan"]["focus"][0]["pct"] == 0.60 and round(p["plan"]["focus"][0]["rs"], 2) == 1.25
    assert [f["key"] for f in p["plan"]["themes"]] == ["XHB"]
    # The rotation row ranks by the pre-market move, a fund with no trade yet last.
    assert [s["key"] for s in p["rotation"]] == ["XLP", "XLE", "XLK", "XLC"]
    assert p["read"]["lines"][1].startswith("Staples and Homebuilders lead the pre-market")


def test_in_and_after_the_session_the_sectors_are_the_sessions() -> None:
    p = page(snap={"sector_ext": EXT})
    assert p["sectors_basis"] == "session"
    assert [f["key"] for f in p["plan"]["focus"]] == ["XLK", "XLC"]


def test_without_the_scanner_list_the_top_setups_are_the_engines_order_of_what_scored() -> None:
    p = page()
    # HOOD did not build, so it is not in the list.
    assert p["ok"] and [r["sym"] for r in p["top"]] == ["SPCX", "COIN", "ADD"]
    assert p["top"][0]["score"] == {"total": 40, "side": "long", "kind": None}  # no parts, no news
    assert "news" not in p["top"][0]


def test_the_top_setups_are_the_scanner_lists_first_ten() -> None:
    # Owner, 2026-11-19: "top setups ... show mag7 and the indicies, not the top 10". At
    # 05:58 ET the engine held only the benchmarks and the MAG 7 while the Scanner led
    # with PANW, GOOG and BABA; the card is the list's first ten, in the list's order.
    listed = [row(s, 51 - i, "short" if s == "BABA" else "long",
                  score={"total": 51 - i, "side": "short" if s == "BABA" else "long",
                         "kind": "inplay", "parts": []})
              for i, s in enumerate(["PANW", "GOOG", "GOOGL", "BABA", "SKHY", "ASML", "FTNT",
                                     "OKTA", "NXPI", "AMZN", "CRWD", "SNDK"])]
    p = d.build({"session": "pre", "trading_day": "2026-11-19", "regime": regime(),
                 "rows": [row("META", 81, "long"), row("NVDA", 71, "long")]},
                {}, {}, {}, [], session_day=date(2026, 11, 18), listed=listed)
    assert [r["sym"] for r in p["top"]] == ["PANW", "GOOG", "GOOGL", "BABA", "SKHY", "ASML",
                                            "FTNT", "OKTA", "NXPI", "AMZN"]
    assert p["top"][3]["score"] == {"total": 48, "side": "short", "kind": "inplay"}
    # The read's count is still the engine's: two active setups.
    assert p["read"]["foot"].startswith("2 active setups")


def test_in_play_is_the_pools_rank_with_the_engines_verdict() -> None:
    ranked = [{"symbol": "SPY", "score": 9.0, "reason": "moved 1 ATR"},
              {"symbol": "SE", "name": "Sea", "score": 20.0, "through": "PDL", "day": None,
               "reason": "gap 1.66 ATR · pre-market 8.1% of ADV · reports today · through PDL"},
              {"symbol": "ASX", "name": "ASE", "score": 14.5, "through": "PDH", "day": 4,
               "reason": "gap 0.90 ATR · through PDH · day 4 of a -21% move"}]
    view = {"ok": True, "qualified": 282, "screened": 2030, "basis": "pre",
            "promoted": [{"symbol": "SE"}], "marks_done": ["08:00"], "next_mark": "09:00",
            "slots": 7, "on": True}
    got = d.in_play(ranked, view,
                    verdict=lambda s: {"state": "promoted" if s == "SE" else "inplay",
                                       "mark": "08:00" if s == "SE" else None},
                    price=lambda s: 74.0 if s == "SE" else None)
    # The benchmarks never; the rest in the pool's order with price and verdict joined.
    assert [r["sym"] for r in got["rows"]] == ["SE", "ASX"]
    assert got["rows"][0]["last"] == 74.0 and got["rows"][0]["verdict"]["state"] == "promoted"
    assert got["rows"][1]["last"] is None and got["rows"][1]["day"] == 4
    assert (got["qualified"], got["promoted"], got["next_mark"]) == (282, 1, "09:00")
    assert d.in_play(ranked, view, verdict=lambda _s: None, price=lambda _s: None,
                     limit=1)["rows"][0]["sym"] == "SE"
    # The page carries the card, and My list is gone.
    p = page()
    assert p["inplay"] is None and "list" not in p and "adds" not in p
    assert d.build({}, {}, {}, {}, [], session_day=FRI, inplay=got)["inplay"] is got


def test_the_plan_counts_continuations_not_day_ones() -> None:
    by = {s["key"]: s for s in page()["plan"]["setups"]}
    assert by["day23"]["n"] == 23
    assert (by["pdh"]["n"], by["pdl"]["n"], by["pdh"]["chip"]) == (41, 34, "through")


def test_focus_is_what_beat_spy_best_first() -> None:
    plan = page()["plan"]
    assert [f["key"] for f in plan["focus"]] == ["XLK", "XLC"]          # not SPY, RSP or a laggard
    assert [f["key"] for f in plan["themes"]] == ["WGMI"]
    # The card passes the tape's read through as it is given, `thin` included: this fixture
    # predates it (2 reads of 11 at +100 is what the engine now calls thin and weak).
    assert plan["bias"] == {"side": "long", "score": 100, "grade": "moderate", "live": 2,
                            "total": 11, "cap": 4, "thin": None}


def test_reports_are_the_sessions_own_before_the_open_first_biggest_first() -> None:
    assert page()["read"]["reports"] == [{"sym": "KKR", "when": "pre"}, {"sym": "B", "when": "pre"},
                                         {"sym": "OXY", "when": "after"}]


def test_the_foot_counts_setups_and_movers() -> None:
    # HOOD did not build, so neither it nor its 3.21% counts; 8.62 and 4.0 are the two 4%+.
    assert page()["read"]["foot"] == "3 active setups · 2 names moving 4%+"


def test_the_sectors_rank_with_a_missing_figure_last_and_carry_their_leaders() -> None:
    rot = page()["rotation"]
    assert [s["key"] for s in rot] == ["XLK", "XLC", "XLP", "XLE"]
    assert rot[0]["leaders"] == ["FROG"] and rot[1]["leaders"] == []


def test_a_page_with_nothing_loaded_says_not_ok_and_does_not_raise() -> None:
    p = d.build({}, {}, {}, {}, [], session_day=FRI)
    assert not p["ok"] and p["top"] == [] and p["breadth"] is None and p["rotation"] == []
    assert p["read"]["title"] == "Market closed"


# The collector's ages at 19:31 ET on Thursday 19 November 2026 (snapshot `age_min`).
AGES = {"scanner": 0.08, "scan_live": 412.0, "sectors": 0.74, "sector_ext": 0.72,
        "breadth_all": 0.74, "wire": 3.34, "stock_news": 0.73, "calendar": 5.81}


def test_each_card_is_as_old_as_the_oldest_block_it_is_drawn_from() -> None:
    assert d.card_ages(AGES, pre=False) == {
        # The live pass last ran at the close; the bar pass a few seconds ago.
        "plan": 0.74, "breadth": 0.74, "top": 0.08,
        # The calendar's six minutes do not date the card: the wire's headlines do.
        "impact": 3.34, "stories": 0.73, "rotation": 0.74}


def test_before_the_bell_the_sector_cards_are_as_old_as_the_pre_market_read() -> None:
    ages = d.card_ages({**AGES, "sector_ext": 7.5}, pre=True)
    assert ages["plan"] == 7.5 and ages["rotation"] == 7.5


def test_in_the_session_the_live_pass_dates_the_engines_rows() -> None:
    assert d.card_ages({**AGES, "scanner": 1.6, "scan_live": 0.05}, pre=False)["top"] == 0.05


def test_a_block_never_read_has_no_age() -> None:
    assert d.card_ages({}, pre=False) == dict.fromkeys(
        ("plan", "breadth", "top", "impact", "stories", "rotation"))
    built = d.build({}, {"age_min": {"wire": 2.0}}, {}, {}, [], session_day=FRI)
    assert built["ages"]["impact"] == 2.0
