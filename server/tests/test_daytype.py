"""The session-type pieces (daytype.py): the label, the night's windows, the
features at 09:00, the base-rate tables, the live card and the record it is kept in."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from typing import Any

from newsterminal import daytype as d
from newsterminal.daytype import ET, at


def test_the_label_is_the_ladders_rule() -> None:
    assert d.label(100, 230, 95, 225, 100)["type"] == "trend"
    assert d.label(100, 230, 95, 225, 100)["dir"] == "up"
    assert d.label(100, 125, 0, 5, 100)["dir"] == "down"
    assert d.label(100, 150, 90, 120, 100)["type"] == "range"
    assert d.label(100, 210, 90, 150, 100)["type"] == "normal"
    # Inside sits inside yesterday whatever else it is; unknown without yesterday.
    assert d.label(100, 150, 90, 120, 100, prev_h=160, prev_l=80)["inside"] is True
    assert d.label(100, 150, 90, 120, 100, prev_h=140, prev_l=80)["inside"] is False
    assert d.label(100, 150, 90, 120, 100)["inside"] is None
    # No ATR, no type worth the name.
    assert d.label(100, 150, 90, 120, None)["type"] == "normal"
    lab = d.label(100, 230, 95, 225, 100)
    assert (lab["range_atr"], lab["close_pos"], lab["efficiency"]) == (1.35, 0.963, 0.926)


def test_the_atr_is_of_the_fourteen_sessions_before_the_day() -> None:
    days = [(date(2026, 1, i + 1), 100.0, 110.0, 90.0, 100.0) for i in range(16)]
    out = d.atr_series(days)
    assert date(2026, 1, 14) not in out
    assert out[date(2026, 1, 15)] == 20.0 and out[date(2026, 1, 16)] == 20.0


def _bars(day: date, hours: list[tuple[int, float, float, float, float]]) -> list[d.Bar]:
    return [(int(at(day, time(h, 0)).timestamp()), o, hi, lo, c) for h, o, hi, lo, c in hours]


def test_a_window_reads_the_bars_that_start_inside_it() -> None:
    nov9 = date(2026, 11, 9)
    bars = _bars(nov9, [(18, 10, 12, 9, 11), (19, 11, 15, 10, 14), (20, 14, 16, 13, 15)])
    assert d.window(bars, at(nov9, time(18, 0)), at(nov9, time(20, 0))) == (10, 15, 9, 14)
    assert d.window(bars, at(nov9, time(21, 0)), at(date(2026, 11, 10), time(0, 0))) is None


def test_mondays_night_starts_on_friday() -> None:
    w = d.night_windows(date(2026, 11, 9), date(2026, 11, 6))  # Monday, Friday
    assert w["overnight"] == (at(date(2026, 11, 6), time(18, 0)), at(date(2026, 11, 9), time(9, 0)))
    assert w["asia"] == (at(date(2026, 11, 8), time(20, 0)), at(date(2026, 11, 9), time(0, 0)))
    assert w["london"] == (at(date(2026, 11, 9), time(2, 0)), at(date(2026, 11, 9), time(5, 0)))
    t = d.night_windows(date(2026, 11, 10), date(2026, 11, 9))  # Tuesday, Monday
    assert t["asia"] == (at(date(2026, 11, 9), time(20, 0)), at(date(2026, 11, 10), time(0, 0)))


def test_features_read_the_night_in_the_days_own_atr() -> None:
    mon, tue = date(2026, 11, 9), date(2026, 11, 10)
    # Monday 15:00 bar closes 27,000; the night runs 26,900–27,300 and 09:00 prints 27,250.
    fut = (_bars(mon, [(15, 26950, 27010, 26940, 27000), (18, 27000, 27050, 26980, 27020),
                       (20, 27020, 27100, 26900, 27090), (23, 27090, 27120, 27080, 27100)])
           + _bars(tue, [(2, 27100, 27300, 27090, 27280), (4, 27280, 27290, 27200, 27250),
                         (8, 27250, 27260, 27240, 27250)]))
    prev = {"day": mon, "type": "trend", "dir": "up", "inside": False, "close_pos": 0.9,
            "range_atr": 1.4, "high": 660.0, "low": 650.0, "ratio": 41.0}
    f = d.features(tue, prev, None, fut, atr_pct=1.0, prev_close_fut=27000.0, vix=19.5,
                   vix_ratio=0.96)
    # The night ran 400 points on a 27,000 base: 1.48% against a 1% ATR; Asia 220, London 210.
    assert f["overnight_atr"] == 1.481 and f["asia_atr"] == 0.815 and f["london_atr"] == 0.778
    assert f["gap_atr"] == 0.926 and f["inventory"] == 0.875
    # 27,250 against yesterday's 650–660 × 41 = 26,650–27,060: above.
    assert f["open_vs_prev"] == "above" and f["prev_type"] == "trend" and f["weekday"] == "Tue"
    bare = d.features(tue, None, None, [], None, None, None, None)
    assert bare["overnight_atr"] is None and bare["gap_atr"] is None
    assert bare["open_vs_prev"] is None


def _row(kind: str, prev: str, night: float, inside: bool = False) -> dict[str, Any]:
    return {"type": kind, "inside": inside, "prev_type": prev, "overnight_atr": night,
            "weekday": "Tue"}


def test_base_rates_carry_their_counts_and_the_else_side() -> None:
    rows = [_row("trend", "range", 0.2), _row("trend", "range", 0.3), _row("range", "trend", 1.0),
            _row("normal", "trend", 0.9), _row("range", "normal", 0.5)]
    lines = d.base_rates(rows)
    assert lines[0]["condition"] == "every session" and lines[0]["n"] == 5
    assert lines[0]["trend"] == 0.4
    after_range = next(ln for ln in lines if ln["condition"] == "yesterday was a range day")
    assert after_range["n"] == 2 and after_range["trend"] == 1.0 and after_range["else"]["n"] == 3
    quiet = next(ln for ln in lines if ln["condition"].startswith("quiet night"))
    assert quiet["n"] == 2 and quiet["trend"] == 1.0 and quiet["else"]["n"] == 3
    text = d.table(lines)
    assert "every session" in text and "*" in text  # small counts are marked


def test_the_cards_readers_take_the_terminals_own_blocks() -> None:
    nov10 = date(2026, 11, 10)
    vt = {"points": [{"key": "VIX9D", "value": 18.1}, {"key": "VIX", "value": 19.9}],
          "ratio": 0.9612}
    assert d.vix_of(vt) == (19.9, 0.9612) and d.vix_of(None) == (None, None)
    gex = {"ok": True, "regime": "POS", "levels": [{"key": "call_1", "price": 28200.0},
                                                   {"key": "flip", "price": 27890.0}]}
    assert d.gamma_of(gex) == {"regime": "POS", "flip": 27890.0}
    assert d.gamma_of({"ok": False, "error": "GEXYGEN down"}) is None
    ts = lambda h, m: at(nov10, time(h, m)).timestamp()  # noqa: E731
    cal = [
        {"event": "ISM Services PMI", "score": 4, "ts": ts(10, 0)},
        # The calendar lists CPI as a family of rows; the card names it once, with
        # the read its rows agree on.
        {"event": "Core CPI m/m", "score": 5, "ts": ts(8, 30), "read": "hot"},
        {"event": "CPI Index, n.s.a.", "score": 5, "ts": ts(8, 30)},
        {"event": "CPI y/y", "score": 5, "ts": ts(8, 30), "read": "hot"},
        {"event": "Retail Sales m/m", "score": 5, "ts": ts(8, 30), "read": "hot"},
        {"event": "Core Retail Sales m/m", "score": 5, "ts": ts(8, 30), "read": "cold"},
        {"event": "Redbook", "score": 1, "ts": ts(8, 55)},  # not worth the card
        {"event": "Fed's Waller speaks", "score": 4, "ts": ts(13, 0)},  # the afternoon
        {"event": "Core CPI m/m", "score": 5,
         "ts": at(date(2026, 11, 11), time(8, 30)).timestamp()},  # tomorrow's
        {"event": "untimed", "score": 5, "ts": None},
    ]
    assert d.prints_of(cal, nov10) == ["CPI (hot)", "Retail Sales (mixed)", "ISM Services PMI"]
    assert d.print_family("Core PCE Price Index m/m") == "PCE"
    assert d.print_family("Nonfarm Payrolls") == "Nonfarm Payrolls"


_SESSIONS = [
    {"key": "overnight", "ok": True, "open": 27930.0, "high": 28050.0, "low": 27870.0,
     "close": 27940.0},
    {"key": "asia", "ok": True, "high": 28048.0, "low": 27869.0},
    {"key": "london", "ok": True, "high": 28044.0, "low": 27870.0},
    {"key": "premkt", "ok": True, "high": 28022.0, "low": 27870.0},
    # Yesterday's New York, still the "ny" row before the bell.
    {"key": "ny", "ok": True, "status": "complete", "prior_day": True,
     "open": 28100.0, "high": 28129.0, "low": 27316.0, "close": 27400.0},
]


def _card(now: datetime) -> dict[str, Any]:
    yesterday = {"shape": "trend day down", "close_pos": 0.1, "range_atr": 1.3, "gap_atr": 0.0}
    return d.card_from_live("NQ", date(2026, 11, 10), _SESSIONS, 300.0, yesterday=yesterday,
                            fuel={"atr_pct": 26}, vix=19.9, vix_ratio=0.96,
                            gamma={"regime": "POS", "flip": 27890.0}, em=450.0,
                            prints=["Core CPI m/m (hot)"], now=now)


def test_the_live_card_and_its_label() -> None:
    card = _card(datetime(2026, 11, 10, 9, 25, tzinfo=ET))
    assert (card["prev_type"], card["prev_dir"], card["overnight_atr"]) == ("trend", "down", 0.6)
    assert card["pre_atr"] == 0.507 and card["prev_high"] == 28129.0 and card["prev_low"] == 27316.0
    assert card["inventory"] == 0.389 and card["flip_sigma"] == 0.111 and card["type"] is None
    assert card["fuel_pct"] == 26
    assert card["prints"] == ["Core CPI m/m (hot)"] and card["at"] == "09:25"
    assert card["late"] is False and card["half_day"] is False and card["atr"] == 300.0
    # A card written after the open says so.
    assert _card(datetime(2026, 11, 10, 10, 35, tzinfo=ET))["late"] is True
    ny = {"key": "ny", "ok": True, "status": "complete", "prior_day": False,
          "start_ts": at(date(2026, 11, 10), time(9, 30)).timestamp(),
          "open": 27940.0, "high": 28400.0, "low": 27900.0, "close": 28380.0}
    close = datetime(2026, 11, 10, 16, 10, tzinfo=ET)
    done = d.label_from_live(card, [*_SESSIONS[:4], ny], None, close)
    assert done["type"] == "trend" and done["dir"] == "up" and done["inside"] is False
    assert done["labelled_at"] == "16:10" and done["prev_type"] == "trend"
    assert done["ny"] == {"open": 27940.0, "high": 28400.0, "low": 27900.0, "close": 28380.0}
    # The next session, read in-session: the ranges hold today's New York row only,
    # so yesterday comes from the labelled card — its shape, its high and low, the gap.
    tomorrow = [*_SESSIONS[:4], {**ny, "prior_day": False, "status": "live"}]
    nxt = d.card_from_live("NQ", date(2026, 11, 11), tomorrow, 300.0, yesterday=None, fuel=None,
                           vix=None, vix_ratio=None, gamma=None, em=None, prints=[],
                           now=datetime(2026, 11, 11, 10, 0, tzinfo=ET), prev_card=done)
    assert (nxt["prev_type"], nxt["prev_dir"], nxt["prev_range_atr"]) == ("trend", "up", 1.667)
    assert nxt["prev_high"] == 28400.0 and nxt["prev_low"] == 27900.0
    assert nxt["gap_atr"] == -1.5  # 27930 at the reopen against a 28380 close, in a 300 ATR
    assert nxt["late"] is True
    # The edge condition shows where price sits in the night, not the night's size.
    assert d._shown("09:00 at an edge of the night's range (outer 15%)",
                    {"inventory": 0.13, "overnight_atr": 1.24}) == "13% up the night's range"
    # The next morning the row is a prior day's, but it is dated: still the card's.
    morning = datetime(2026, 11, 11, 8, 0, tzinfo=ET)
    assert d.label_from_live(card, [{**ny, "prior_day": True}], None, morning)["type"] == "trend"
    # Not finished yet, another day's row, or nothing to measure by: the card as it was.
    assert d.label_from_live(card, [{**ny, "status": "live"}], 300.0, close)["type"] is None
    next_day = {**ny, "start_ts": at(date(2026, 11, 11), time(9, 30)).timestamp()}
    assert d.label_from_live(card, [next_day], 300.0, close)["type"] is None
    bare = {**card, "atr": None}
    assert d.label_from_live(bare, [ny], None, close)["type"] is None
    assert d.label_from_live(bare, [ny], 300.0, close)["type"] == "trend"
    # A row without a date is taken only when it is not a prior day's.
    undated = {k: v for k, v in ny.items() if k != "start_ts"}
    assert d.label_from_live(card, [undated], None, close)["type"] == "trend"
    assert d.label_from_live(card, [{**undated, "prior_day": True}], None, close)["type"] is None


def test_the_record_keeps_one_line_per_day_and_book(tmp_path: Any) -> None:
    path = os.path.join(str(tmp_path), "session_types.jsonl")
    log = d.SessionLog(path)
    card = _card(datetime(2026, 11, 10, 9, 25, tzinfo=ET))
    log.put(card)
    log.put({**card, "book": "ES"})
    assert log.get("2026-11-10", "NQ") == card and log.get("2026-11-10", "GC") is None
    # The label replaces the card's line rather than adding one.
    log.put({**card, "type": "trend", "dir": "up"})
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]
    assert [(ln["book"], ln["type"]) for ln in lines] == [("ES", None), ("NQ", "trend")]
    # A restart reads it back, and a bad line is skipped rather than fatal.
    with open(path, "a", encoding="utf-8") as f:
        f.write("not json\n")
    again = d.SessionLog(path)
    assert again.get("2026-11-10", "NQ")["type"] == "trend" and len(again.rows()) == 2
    assert [c["book"] for c in again.labelled("NQ")] == ["NQ"] and again.labelled("ES") == []
    assert again.labelled("NQ", after="2026-11-10") == []


def _record() -> list[dict[str, Any]]:
    """Two kinds of day: 200 quiet nights after range days that mostly ranged, and
    200 big nights after normal days that trended three times as often."""
    quiet = ([_row("range", "range", 0.3)] * 180 + [_row("trend", "range", 0.3)] * 4
             + [_row("normal", "range", 0.3)] * 16)
    big = ([_row("range", "normal", 0.9)] * 80 + [_row("trend", "normal", 0.9)] * 60
           + [_row("normal", "normal", 0.9)] * 60)
    return [*quiet, *big]


def test_the_lean_is_the_records_counts_for_a_day_like_today() -> None:
    table = d.rate_table(_record())
    base = table["every session"]
    assert (base["n"], base["trend_n"], base["range_n"]) == (400, 64, 260)
    quiet = {"overnight_atr": 0.31, "night_done": False, "prev_type": "range", "weekday": "Tue"}
    ln = d.lean(quiet, table)
    assert ln["call"] == "range" and ln["word"] == "Range day likely"
    by = {h["condition"]: h for h in ln["holds"]}
    assert by["yesterday was a range day"]["vote"] == "range"
    assert by["quiet night (under 0.4 ATR)"]["shown"] == "0.31 ATR so far"
    assert "quiet night (0.31 ATR so far): 4 trend days in 200, 180 range" in ln["why"]
    assert ln["base"] == {"n": 400, "trend": 64, "range": 260}
    assert d.words("NQ", ln).startswith("NQ: Range day likely — ")
    assert d.words("NQ", ln).endswith("· base 64 trend days in 400, 260 range")
    big = {"overnight_atr": 0.9, "night_done": True, "prev_type": "normal", "weekday": "Tue"}
    ln = d.lean(big, table)
    assert ln["call"] == "trend" and ln["word"] == "Trend day more possible"
    assert {h["condition"] for h in ln["holds"] if h["vote"] == "trend"} >= {
        "yesterday was a normal day", "big night (0.8 ATR or more)"}
    # A quiet night after a normal day: the record pulls both ways.
    mixed = d.lean({"overnight_atr": 0.31, "night_done": True, "prev_type": "normal"}, table)
    assert mixed["call"] == "mixed"
    # Nothing holds, or no record: it says so rather than calling.
    plain = {"overnight_atr": 0.6, "night_done": True, "prev_type": "trend"}
    assert d.lean(plain, table)["call"] == "none"
    none = d.lean(quiet, {})
    assert none["call"] == "none" and none["why"].startswith("no record yet")


def test_the_backfills_rows_are_read_back_full_sessions_only(tmp_path: Any) -> None:
    path = os.path.join(str(tmp_path), "daytype_backfill.json")
    rows = [{"day": "2026-11-06", "type": "range", "prev_type": "normal", "half_day": False},
            {"day": "2026-11-27", "type": "range", "prev_type": "range", "half_day": True},
            {"day": "2026-11-09", "type": None, "prev_type": "range", "half_day": False}]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"rows": {"NQ": rows}}, f)
    got = d.load_backfill(path)
    assert [r["day"] for r in got["NQ"]] == ["2026-11-06"]
    assert d.load_backfill(os.path.join(str(tmp_path), "missing.json")) == {}


def test_the_dashboard_carries_no_session_type() -> None:
    """The lean is a read on the futures books, and the Futures tab's: the Dashboard's
    plan does not repeat it, whatever the record holds (owner, 2026-11-12)."""
    from newsterminal.dashboard import build

    lean = {"call": "range", "word": "Range day likely", "why": "quiet night (0.31 ATR so far)…",
            "night": {"atr": 0.31, "done": False}, "base": {"n": 569, "trend": 39, "range": 347}}
    snap = {"daytype": {"books": {"NQ": {"lean": lean, "label": None},
                                  "ES": {"lean": lean, "label": None}}}}
    page = build({}, snap, {}, {}, [], session_day=date(2026, 11, 12))
    assert "session_type" not in page["plan"]
    assert "NQ" not in json.dumps(page)
