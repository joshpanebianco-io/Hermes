"""
The Today list (today.py): which phase it is, and what each phase ranks by.

The boundary table is the point of the first test: a list that ranks the evening's
movers at 09:31 or the session's setups at 04:00 is the whole page wrong.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from newsterminal import scan, today
from newsterminal.sources import pool
from newsterminal.sources import scanner as scan_src

ET = scan.ET


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# ---- the clock -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "key", "day", "nxt"),
    [
        # Friday 13 Nov 2026
        (et(2026, 11, 13, 3, 59), "overnight", date(2026, 11, 13), "pre"),
        (et(2026, 11, 13, 4, 0), "pre", date(2026, 11, 13), "open"),
        (et(2026, 11, 13, 9, 29), "pre", date(2026, 11, 13), "open"),
        (et(2026, 11, 13, 9, 30), "open", date(2026, 11, 13), "session"),
        (et(2026, 11, 13, 9, 59), "open", date(2026, 11, 13), "session"),
        (et(2026, 11, 13, 10, 0), "session", date(2026, 11, 13), "after"),
        (et(2026, 11, 13, 15, 59), "session", date(2026, 11, 13), "after"),
        # After the close the list is for the next session: Monday.
        (et(2026, 11, 13, 16, 0), "after", date(2026, 11, 16), "overnight"),
        (et(2026, 11, 13, 19, 59), "after", date(2026, 11, 16), "overnight"),
        (et(2026, 11, 13, 20, 0), "overnight", date(2026, 11, 16), "pre"),
        (et(2026, 11, 14, 12, 0), "overnight", date(2026, 11, 16), "pre"),   # Saturday
        (et(2026, 11, 16, 3, 0), "overnight", date(2026, 11, 16), "pre"),    # Monday early
        # Thanksgiving is shut; the half day after it closes at 13:00, late session to 17:00.
        (et(2026, 11, 26, 10, 0), "overnight", date(2026, 11, 27), "pre"),
        (et(2026, 11, 27, 12, 59), "session", date(2026, 11, 27), "after"),
        (et(2026, 11, 27, 13, 0), "after", date(2026, 11, 30), "overnight"),
        (et(2026, 11, 27, 17, 0), "overnight", date(2026, 11, 30), "pre"),
    ],
)
def test_which_phase_it_is(at: datetime, key: str, day: date, nxt: str) -> None:
    p = today.phase_at(at)
    assert (p.key, p.day, p.next_key) == (key, day, nxt)
    assert p.ends > at


def test_a_phase_says_when_the_next_begins() -> None:
    p = today.phase_at(et(2026, 11, 13, 8, 42))
    d = p.as_dict(et(2026, 11, 13, 8, 42))
    assert (d["label"], d["next_label"], d["ends_in_min"]) == ("Pre-market", "The open", 48.0)
    # Friday evening's overnight runs to Monday's 04:00.
    assert today.phase_at(et(2026, 11, 13, 21, 0)).ends == et(2026, 11, 16, 4, 0)


# ---- the two triggers --------------------------------------------------------------


def test_the_plan_is_both_ways_before_a_side_is_decided() -> None:
    # Inside both ranges: the break of the nearer level each way.
    got = today.plan_of(100.0, pdh=104.0, pdl=95.0, pmh=102.0, pml=98.0)
    assert got["long"] == {"level": "PMH", "price": 102.0, "held": False}
    assert got["short"] == {"level": "PML", "price": 98.0, "held": False}
    # Gapped over both highs: the long is the retest of the higher one under it.
    up = today.plan_of(110.0, pdh=104.0, pdl=95.0, pmh=108.0, pml=101.0)
    assert up["long"] == {"level": "PMH", "price": 108.0, "held": True}
    assert up["short"] == {"level": "PML", "price": 101.0, "held": False}
    # No pre-market range yet (the evening): yesterday's levels alone.
    ev = today.plan_of(50.0, pdh=52.0, pdl=47.0, pmh=None, pml=None)
    assert (ev["long"]["level"], ev["short"]["level"]) == ("PDH", "PDL")
    assert today.plan_of(None, 1.0, 1.0, None, None) == {"long": None, "short": None}


# ---- pre-market ------------------------------------------------------------------------


def _fixture() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "tv_pool_trim.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_pre_market_list_is_the_pools_rank_on_live_prices() -> None:
    rows = pool.qualify(pool.parse(_fixture())[0], "pre")
    now = et(2026, 10, 23, 8, 30)
    by = {r["symbol"]: r for r in rows}
    ko = by["KO"]
    # A live pre-market trade on KO well past the screener's (stale) print, and an old one
    # on SNDK that must not be read.
    quotes = {"KO": {"price": ko["close"] * 0.92, "at": now.timestamp() - 30, "session": "pre"},
              "SNDK": {"price": 1.0, "at": now.timestamp() - 3600, "session": "pre"}}
    live = today.live_premarket(rows, quotes.get, now.timestamp())
    lby = {r["symbol"]: r for r in live}
    assert lby["KO"]["live"] and lby["KO"]["pm_close"] == pytest.approx(ko["close"] * 0.92)
    assert not lby["SNDK"].get("live") and lby["SNDK"]["pm_close"] == by["SNDK"]["pm_close"]
    ranked = pool.rank(live, scan.clock_at(now))
    got = today.rank_pre(ranked, lby, levels=lambda s: {"pdh": None, "pdl": None},
                         catalyst=lambda s: None, favs=frozenset({"SNDK"}),
                         tracked=frozenset({"KO"}))
    assert got[0]["sym"] == "KO" and got[0]["lean"] == "short" and got[0]["live"]
    assert got[0]["chg"] == pytest.approx(-8.0)
    assert got[0]["why"][0].startswith("gap ▼")
    assert any(r["fav"] for r in got if r["sym"] == "SNDK")
    # Only names over the pool's bar, and never a benchmark.
    assert all(r["score"] >= pool.MIN_SCORE for r in got)
    assert got[0]["score_kind"] == "in play" and got[0]["score_max"] == pool.SCORE_MAX


# ---- the open ------------------------------------------------------------------------


def _pre(sym: str, score: float, lean: str = "long") -> dict[str, Any]:
    return {"sym": sym, "score": score, "lean": lean, "last": 100.0, "chg": 2.0, "why": []}


def test_the_open_orders_the_pre_markets_names_by_what_the_bell_did() -> None:
    pre = [_pre("A", 20.0), _pre("B", 18.0), _pre("C", 15.0), _pre("D", 12.0), _pre("E", 9.0)]
    engine = {
        "A": {"ok": True, "setup": {"state": "failed", "side": "long"}},
        "B": {"ok": True, "setup": {"state": "approaching", "side": "long"}},
        "C": {"ok": True, "setup": {"state": "retest", "side": "long", "note": "At PMH"}},
        "D": {"ok": True, "setup": {"state": "extended", "side": "long",
                                    "entry": {"dist_atr": 3.0}}},
    }
    wide = {"E": {"pd_state": "above", "pm_state": "inside", "pdc": 98.0}}
    got = today.rank_open(pre, engine=engine, wide=wide.get, price=lambda s: (101.0, True))
    assert [r["sym"] for r in got] == ["C", "D", "E", "B", "A"]
    assert [r["status"] for r in got] == ["entry live", "through a level", "through a level",
                                          "not triggered", "failed"]
    assert got[0]["setup"]["note"] == "At PMH" and got[0]["live"]
    # Near VWAP / the 8 EMA is a live entry; the wrong side of VWAP is not.
    assert today.open_group({"state": "extended", "entry": {"dist_atr": 0.6}}, None, "long") == 0
    assert today.open_group({"state": "retest", "lost_vwap": True}, None, "long") == 3


# ---- the session -------------------------------------------------------------------


def test_the_session_is_the_engines_own_order() -> None:
    def row(sym: str, rank: int, total: int) -> dict[str, Any]:
        return {"sym": sym, "ok": True, "last": 101.0, "levels": {"pdc": 100.0},
                "setup": {"state": "retest", "side": "long", "note": "At PDH"},
                "score": {"total": total, "raw": total, "rank": rank, "side": "long",
                          "parts": [{"key": "location", "label": "Location", "pts": 25,
                                     "note": "at the broken level"},
                                    {"key": "rs", "label": "RS vs SPY", "pts": 5,
                                     "note": "+0.30 ATR vs SPY · capped: no live entry"},
                                    {"key": "fuel", "label": "Range used", "pts": -10,
                                     "note": ""}]}}
    rows = [row("B", 2, 80), row("A", 1, 90), {"sym": "X", "ok": False}]
    got = today.rank_session(rows, favs=frozenset({"B"}), tracked=frozenset({"A", "B"}))
    assert [r["sym"] for r in got] == ["A", "B"]
    assert got[1]["fav"] and got[0]["score_kind"] == "setup" and got[0]["chg"] == pytest.approx(1.0)
    assert got[0]["why"][:2] == ["Location: at the broken level", "RS vs SPY: +0.30 ATR vs SPY"]
    assert got[0]["why"][-1] == "Range used -10"


# ---- the evening -------------------------------------------------------------------


def _wide(sym: str, **kw: Any) -> dict[str, Any]:
    # $1bn a day on average, a 4% ATR.
    base: dict[str, Any] = {"sym": sym, "name": sym, "sector": "XLK", "cap": 5e9,
                            "close": 50.0, "chg": 1.0, "c1": 49.5, "high": 50.5, "low": 49.0,
                            "vol": 2e7, "avg": 2e7, "atr": 2.0,
                            "ah_c": None, "ah_chg": None, "ah_vol": None}
    base.update(kw)
    return base


def test_the_evening_ranks_after_hours_movers_and_the_days_big_ones() -> None:
    rows = [
        # Reported after the close and up 9% after hours on a tenth of a day.
        _wide("EARN", ah_c=54.5, ah_chg=9.0, ah_vol=2e6),
        # A 24% day on 3x volume: tomorrow is its day 2.
        _wide("RUN", close=62.0, c1=50.0, chg=24.0, vol=6e7, high=63.0, low=55.0),
        # A quarter-ATR drift on normal volume and no late trade: 4.2, under the
        # evening's bar though over the pool's.
        _wide("QUIET"),
        # Under $10.
        _wide("TINY", close=8.0, c1=7.0, chg=14.0),
    ]
    reports = {"EARN": {"symbol": "EARN", "date": "2026-11-13", "when": "after",
                        "surprise_pct": 6.2}}
    got = today.rank_evening(
        rows, ah_of=lambda r: ({"last": r["ah_c"], "chg": r["ah_chg"], "vol": r["ah_vol"]}
                               if r["ah_c"] is not None else None),
        catalyst=lambda s: None, stage={}, reports=reports, session_day=date(2026, 11, 13),
        next_day=date(2026, 11, 16), favs=frozenset(), tracked=frozenset())
    syms = [r["sym"] for r in got]
    assert set(syms) == {"EARN", "RUN"}
    earn = next(r for r in got if r["sym"] == "EARN")
    assert earn["move"] == "after" and earn["lean"] == "long"
    assert "reported after the close, EPS +6.2% vs estimate" in earn["why"]
    run = next(r for r in got if r["sym"] == "RUN")
    assert run["stage"] == 2 and "tomorrow is day 2 of a +24% move" in run["why"]
    # Tomorrow's levels are today's range, and the plan reads them both ways.
    assert run["levels"]["pdh"] == 63.0 and run["plan"]["short"]["level"] == "PDL"


def test_a_report_due_before_the_next_open_counts_in_the_evening() -> None:
    words, pts = today.report_words("X", {"X": {"date": "2026-11-16", "when": "pre"}},
                                    date(2026, 11, 13), date(2026, 11, 16))
    assert (words, pts) == ("reports before the open", float(pool.W_REPORT))
    assert today.report_words("X", {}, date(2026, 11, 13), date(2026, 11, 16)) == (None, 0.0)


# ---- the tracked set: favourites -----------------------------------------------------


def test_the_favourites_tracked_are_the_most_in_play_then_the_pinned_order() -> None:
    pinned = ["SPY", "QQQ", "AAA", "BBB", "CCC", "DDD"]
    ranked = [{"symbol": "CCC", "score": 12.0}, {"symbol": "DDD", "score": 3.0}]
    assert pool.choose_favourites(ranked, pinned, n=3) == ["CCC", "DDD", "AAA"]
    # Promotion's room is what the benchmarks and the tracked favourites leave.
    rk = [{"symbol": f"S{i}", "score": 10.0, "gap_atr": 1.0, "reason": ""} for i in range(40)]
    got = pool.promote(rk, pinned, [], "09:25", favs=["CCC", "DDD", "AAA"])
    assert len(got) == 40 - 3 - 3 - pool.POST_OPEN_SLOTS


def test_the_scanner_tracks_the_benchmarks_todays_favourites_and_the_pool(tmp_path: Any) -> None:
    s = scan_src.ScanStore(str(tmp_path / "wl.json"))
    s.set_watchlist(["SPY", "QQQ", "IWM", "AAA", "BBB", "CCC"])
    now = et(2026, 11, 13, 9, 0)
    td = scan.clock_at(now).trading_day
    # Before the day's first mark: every pin.
    s.set_promoted(td, ["NEW"], {}, None)
    assert s.watchlist(now) == ["SPY", "QQQ", "IWM", "AAA", "BBB", "CCC", "NEW"]
    # After it: the benchmarks, the chosen favourites, then the pool's.
    s.set_promoted(td, ["NEW"], {}, ["CCC"])
    assert s.watchlist(now) == ["SPY", "QQQ", "IWM", "CCC", "NEW"]
    # The benchmarks are on the list and are nobody's favourite (2026-11-13).
    assert s.tracked_favourites() == ["CCC"] and s.pinned() == ["AAA", "BBB", "CCC"]


def test_the_mag_7_is_always_on_the_list_and_the_pool_counts_it(tmp_path: Any) -> None:
    """Owner, 2026-11-13: "why is MAG 7 only showing 3... it should be showing the MAG 7".
    With no favourites the MAG7 chip had the three in play that morning; the collector's
    store keeps all seven on the list (scanner.CORE), a starred one takes no favourite's
    slot, and the pool leaves them the room."""
    s = scan_src.ScanStore(str(tmp_path / "wl.json"), core=scan_src.CORE)
    s.set_watchlist([])
    now = et(2026, 11, 13, 9, 0)
    assert s.watchlist(now) == list(scan_src.CORE)
    s.set_watchlist(["NVDA", "AAA"])            # a starred MAG 7 name is listed once
    assert s.pinned() == ["NVDA", "AAA"] and s.watchlist(now) == [*scan_src.CORE, "AAA"]
    assert pool.choose_favourites([], ["NVDA", "AAA"], core=scan_src.CORE) == ["AAA"]
    ranked = [{"symbol": f"S{i:02d}", "score": 10.0 - i * 0.1, "gap_atr": 1.0, "reason": "x"}
              for i in range(40)]
    ranked.insert(0, {"symbol": "TSLA", "score": 20.0, "gap_atr": 2.0, "reason": "x"})
    got = pool.promote(ranked, [], [], "10:00", core=scan_src.CORE)
    assert "TSLA" not in {g["symbol"] for g in got}
    assert len(got) == scan_src.MAX_SYMBOLS - len(scan_src.CORE)


def test_favourites_can_be_cleared_and_the_benchmarks_stay(tmp_path: Any) -> None:
    """Owner, 2026-11-13: "lets reset it so nothing is favourited". An empty list
    clears the favourites (it used to be refused and keep the old list); the
    benchmarks stay on the list, first, and a list of nothing but typos is still
    refused."""
    path = str(tmp_path / "wl.json")
    s = scan_src.ScanStore(path)
    s.set_watchlist(["SPY", "AAA", "BBB"])
    assert s.pinned() == ["AAA", "BBB"]
    assert s.set_watchlist([]) == ([], [])
    assert s.pinned() == []
    now = et(2026, 11, 13, 9, 0)
    assert s.watchlist(now) == ["SPY", "QQQ", "IWM"]
    # It survives a restart as nothing favourited, not as the default list.
    assert scan_src.ScanStore(path).pinned() == []
    # Typos alone keep what was there.
    s.set_watchlist(["CCC"])
    assert s.set_watchlist(["not a ticker!"]) == (["CCC"], ["NOT A TICKER!"])
    assert s.pinned() == ["CCC"]


# ---- the rest of the list ----------------------------------------------------------


def test_the_rest_of_the_tracked_list_goes_under_the_ranking() -> None:
    ranked = [{"sym": "MSFT"}]
    engine = [{"sym": "MSFT", "ok": True, "score": {"rank": 1}},
              {"sym": "AAPL", "ok": True, "score": {"rank": 2, "side": "long"}, "last": 101.0,
               "levels": {"pdc": 100.0}},
              {"sym": "NVDA", "ok": True, "score": {"rank": 3}},
              {"sym": "BAD", "ok": False}]
    inplay = {"NVDA": {"score": 3.1, "reason": "gap 0.30 ATR"}}
    got = today.rest_of_list(ranked, engine, inplay=inplay, favs=frozenset({"AAPL"}))
    # Not the ranked one again, not a row the engine could not read; the more in play first.
    assert [r["sym"] for r in got] == ["NVDA", "AAPL"]
    assert got[0]["why"] == ["gap 0.30 ATR"] and got[1]["why"] == ["not in play yet"]
    assert got[1]["fav"] and got[1]["tracked"] and got[1]["chg"] == pytest.approx(1.0)


# ---- the Setups table's row --------------------------------------------------------


def test_every_today_row_is_drawn_as_the_setups_tables_row() -> None:
    t = {"sym": "MSFT", "rank": 1, "name": "Microsoft", "sector": "XLK", "last": 520.1,
         "chg": -2.7, "move": "pre", "score": 13.6, "score_max": pool.SCORE_MAX,
         "why": ["gap ▼ 0.91 ATR", "below PDL"], "story": {"title": "x"}, "lean": "short",
         "plan": today.plan_of(520.1, 535.0, 521.0, 522.0, 515.0), "levels":
         {"pdh": 535.0, "pdl": 521.0, "pmh": 522.0, "pml": 515.0, "pdc": 534.6},
         "vol_pct": 0.9, "rvol": None, "stage": None, "spark": [1.0, 2.0], "new": False}
    wide = {"chg": 1.2, "pm_vol": 2e5, "avg": 2.4e7, "atr": 9.0, "vol": 3e7}
    row = today.scan_row(t, None, "pre", wide)
    # The shape the table reads, with nothing the engine alone knows invented.
    assert row["ok"] and row["rs"] == {"SPY": None, "QQQ": None} and row["signals"] == []
    assert (row["chg_pct"], row["ext_pct"]) == (1.2, -2.7)   # the last session, then pre
    assert row["broken"]["pdl"] and not row["broken"]["pdh"] and row["lvl_state"] == -1
    assert row["setup"] == {"side": "short", "state": "forming", "level": "PDL", "entry": None,
                            "note": ""}
    assert row["premkt"]["pct_adv"] == 0.9 and not row["levels"]["pm_done"]
    # The score is the in-play read, as its share of the most, with the reasons as its part.
    assert row["score"]["total"] == round(100 * 13.6 / pool.SCORE_MAX)
    assert row["score"]["parts"][0]["note"] == "gap ▼ 0.91 ATR · below PDL"
    # A tracked name is the engine's own row; before 10:00 its score is the phase's.
    eng = {"sym": "MSFT", "ok": True, "score": {"total": 34, "side": "short", "parts": []},
           "setup": {"state": "forming"}, "catalyst": None}
    got = today.scan_row(t, eng, "pre", wide)
    assert got["setup"] == {"state": "forming"} and got["score"]["raw"] == 13.6
    assert today.scan_row(t, eng, "session", wide)["score"]["total"] == 34


# ---- new names and the record ------------------------------------------------------


def test_a_name_new_to_the_top_ten_is_marked_for_a_quarter_hour() -> None:
    seen: dict[str, float] = {}
    t0 = 1_000_000.0
    rows = [{"sym": "A"}, {"sym": "B"}]
    today.mark_new(rows, seen, t0, fresh=True)
    assert not rows[0]["new"] and not rows[1]["new"]   # the first read: nothing is new
    rows = [{"sym": "C"}, {"sym": "A"}]
    today.mark_new(rows, seen, t0 + 60, fresh=False)
    assert rows[0]["new"] and not rows[1]["new"]
    rows = [{"sym": "C"}]
    today.mark_new(rows, seen, t0 + 60 + today.NEW_MIN * 60 + 1, fresh=False)
    assert not rows[0]["new"]
    # A phase whose first read had no rows: its first names are not new either.
    empty: dict[str, float] = {}
    today.mark_new([], empty, t0, fresh=True)
    first = [{"sym": "MSFT"}, {"sym": "BABA"}]
    today.mark_new(first, empty, t0 + 180, fresh=False)
    assert not any(r["new"] for r in first)


def test_a_name_with_no_pre_market_trade_is_not_on_the_pre_market_list() -> None:
    ranked = [{"symbol": "IREN", "score": 5.0, "gap_atr": None, "day": 5},
              {"symbol": "MSFT", "score": 13.7, "gap_atr": 0.97}]
    rows = {"IREN": {"symbol": "IREN", "close": 40.0, "pm_close": None, "pm_stale": True},
            "MSFT": {"symbol": "MSFT", "close": 535.0, "pm_close": 520.0}}
    got = today.rank_pre(ranked, rows, levels=lambda s: {}, catalyst=lambda s: None,
                         favs=frozenset(), tracked=frozenset())
    assert [r["sym"] for r in got] == ["MSFT"]


def test_a_phases_list_is_written_down_with_what_ranked_it(tmp_path: Any) -> None:
    got = {"phase": {"key": "pre", "day": "2026-11-13"},
           "rows": [{"rank": 1, "sym": "KO", "score": 20.1, "why": ["gap ▼ 1.67 ATR"],
                     "lean": "short", "extra": "dropped"}]}
    path = tmp_path / today.MARKS_NAME
    today.log_list(str(path), got, et(2026, 11, 13, 9, 26))
    line = json.loads(path.read_text(encoding="utf-8"))
    assert (line["kind"], line["phase"], line["day"], line["at_et"]) == (
        "today", "pre", "2026-11-13", "2026-11-13 09:26")
    assert line["rows"][0]["sym"] == "KO" and "extra" not in line["rows"][0]
