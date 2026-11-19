"""
The pre-market record (owner, 2026-11-18: "the purpose of the scoring is to show potential
strong stocks where the break and retest will hold and continue trending (both bearish or
bullish) with momentum" → "yes do what you recommend"). LOW that morning is the worked
example: gap down 1.04 ATR on its report, below PDL, the model reading its story as mixed.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from newsterminal import premarket_record as pr
from newsterminal import scan, today

_spec = importlib.util.spec_from_file_location(
    "fit_score", Path(__file__).resolve().parent.parent / "tools" / "fit_score.py")
assert _spec is not None and _spec.loader is not None
fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit)

DAY = date(2026, 11, 18)


def _low_row() -> dict[str, Any]:
    return {"sym": "LOW", "rank": 2, "score": 16.9, "lean": "short", "chg": -2.81,
            "gap_atr": 1.04, "vol_pct": 1.0, "last": 214.26, "tracked": True,
            "levels": {"pdh": 226.28, "pdl": 220.13, "pmh": 229.24, "pml": 212.34},
            "story": {"title": "Lowe's Companies Earnings Up In Q3; Raises FY26 Outlook",
                      "tag": "Guidance", "major": True},
            "report": "reported this morning"}


def test_the_four_figures_of_a_pre_market_row() -> None:
    read = {"size": "big", "direction": "mixed", "text": True,
            "line": "LOW Q3 sales up 9.3%, EPS $3.10; outlook raised, margin guidance trimmed"}
    c = pr.pre_context(_low_row(), spy_gap=0.12, sector_pct=-0.4, rvol=3.2, rvol_est=False,
                       read=read)
    # The gap signed by the move, less SPY's (the app's RS, before the bell).
    assert c["gap"] == -1.04 and c["spy"] == 0.12 and c["own"] == -1.16
    assert c["rvol"] == 3.2 and not c["rvol_est"] and c["sector_pct"] == -0.4
    assert c["catalyst"]["direction"] == "mixed" and c["catalyst"]["report"]
    # 214.26 in a 212.34-229.24 pre-market range, toward the low of a gap down.
    assert c["hold"] == 0.89 and c["hold_word"].startswith("Holding near its pre-market low")
    assert pr.hold_word(0.5, True).startswith("Pulled back from its pre-market high")
    assert pr.hold_word(0.2, False).startswith("Fading")
    assert pr.hold_of(10.0, None, 9.0, True) is None and pr.hold_of(10.0, 9.0, 9.0, True) is None
    # Without SPY or a direction, no own move; nothing raises.
    bare = pr.pre_context({"sym": "X"}, spy_gap=None, sector_pct=None, rvol=None,
                          rvol_est=True, read=None)
    assert bare["own"] is None and bare["hold"] is None and bare["catalyst"]["size"] is None


def test_the_list_line_keeps_the_ranked_names_and_their_figures() -> None:
    row = {**_low_row(), "pre_ctx": pr.pre_context(_low_row(), spy_gap=0.12, sector_pct=None,
                                                   rvol=3.2, rvol_est=False, read=None)}
    under = {"sym": "AAPL", "listed": True}
    line = pr.list_line("2026-11-18", "09:25", [row, under])
    assert line["kind"] == "list" and [r["sym"] for r in line["rows"]] == ["LOW"]
    assert line["rows"][0]["own"] == -1.16 and line["rows"][0]["hold"] == 0.89


def _bar(hm: str, o: float, h: float, lo: float, c: float) -> scan.Bar:
    hh, mm = (int(x) for x in hm.split(":"))
    t = int(datetime(DAY.year, DAY.month, DAY.day, hh, mm, tzinfo=scan.ET).timestamp())
    return scan.Bar(t, o, h, lo, c, 1000.0)


def test_a_retest_that_holds_and_trends_into_the_close() -> None:
    # A short (L) at 10:00 on 214, stop 216: +1R at 212, +2R at 210, the close at 207.
    bars = [_bar("09:30", 214.0, 215.0, 213.0, 214.5), _bar("09:35", 214.5, 215.0, 213.5, 214.0)]
    px = 214.0
    for i in range(76):   # to the 15:55 bar: the day is settled only on bars that reach the bell
        h, m = divmod(9 * 60 + 40 + 5 * i, 60)
        nxt = px - 0.1
        bars.append(_bar(f"{h:02d}:{m:02d}", px, px + 0.2, nxt - 0.2, nxt))
        px = nxt
    t10 = int(datetime(2026, 11, 18, 10, 0, tzinfo=scan.ET).timestamp())
    signals = [{"kind": "L", "side": "short", "t": t10, "price": 214.0, "stop": 216.0,
                "level": "PDL", "note": "retest of PDL"},
               {"kind": "L", "side": "short", "t": t10 + 3600, "price": 211.0, "stop": 212.0,
                "level": "PDL", "note": "a second retest"}]
    daily = [scan.DayBar(date(2026, 11, 17), 220.0, 226.0, 220.0, 222.0, 1e6)]
    after = datetime(2026, 11, 18, 21, 30, tzinfo=UTC).timestamp()   # read at 16:30 ET
    got = pr.day_result("LOW", DAY, signals, bars, after, daily, after)
    rt = got["retest"]
    assert rt["side"] == "short" and rt["at_et"] == "10:00" and rt["retests"] == 2
    assert rt["hit_1r"] and rt["hit_2r"] and not rt["stopped"] and rt["final"]
    assert rt["held_r"] > 2.0
    # High 215, low 206.2 on a 6.00 daily ATR; the close 206.4, at the bottom of the range.
    assert got["trend_day"] and got["close_pos"] >= pr.TREND_CLOSE and got["range_atr"] == 1.47
    # No retest: the day is still read.
    none = pr.day_result("LOW", DAY, [], bars, after, daily, after)
    assert none["retest"] is None and none["bars"] == len(bars)


def test_a_finished_day_is_owed_once_and_only_after_its_bell() -> None:
    lines = [{"kind": "list", "day": "2026-11-18", "rows": [{"sym": "LOW"}, {"sym": "TGT"}]}]
    at_noon = datetime(2026, 11, 18, 17, 0, tzinfo=UTC).timestamp()   # 12:00 ET
    after = datetime(2026, 11, 18, 21, 30, tzinfo=UTC).timestamp()    # 16:30 ET
    assert pr.owed(lines, DAY, at_noon) == {}
    assert pr.owed(lines, DAY, after) == {"2026-11-18": ["LOW", "TGT"]}
    done = [*lines, {"kind": "outcome", "day": "2026-11-18", "rows": {}}]
    assert pr.owed(done, DAY, after) == {}
    # Past the bars' reach it is left alone.
    assert pr.owed(lines, date(2026, 12, 1), after) == {}


def test_the_record_round_trips(tmp_path: Any) -> None:
    path = str(tmp_path / "rec.jsonl")
    pr.append({"kind": "list", "day": "2026-11-18", "rows": []}, path)
    pr.append({"kind": "outcome", "day": "2026-11-18", "rows": {}}, path)
    assert [e["kind"] for e in pr.read(path)] == ["list", "outcome"]
    assert pr.read(str(tmp_path / "none.jsonl")) == []


def test_the_scanner_row_carries_the_figures_before_the_bell_only() -> None:
    t = {**_low_row(), "pre_ctx": {"own": -1.16}, "move": "pre", "plan": {}, "why": []}
    eng = {"sym": "LOW", "ok": True, "score": {"total": 40, "side": "short", "parts": []},
           "setup": {"state": "forming"}, "lvl_state": -1, "levels": {}, "catalyst": None}
    assert today.scan_row(t, eng, "pre", None)["pre_ctx"] == {"own": -1.16}
    assert today.scan_row(t, None, "pre", {})["pre_ctx"] == {"own": -1.16}
    assert today.scan_row(t, eng, "session", None)["pre_ctx"] is None


def _rec_day(day: str, n: int, *, long_ok: bool) -> list[dict[str, Any]]:
    rows, out = [], {}
    for i in range(n):
        sym = f"S{i}"
        side = "long" if i % 2 == 0 else "short"
        ok = long_ok if side == "long" else not long_ok
        rows.append({"sym": sym, "gap": 1.0 if side == "long" else -1.0, "own": 0.8 if ok else 0.0,
                     "rvol": 3.0, "rvol_est": False, "hold": 0.9,
                     "catalyst": {"direction": "bullish" if side == "long" else "bearish",
                                  "size": "big"}})
        out[sym] = {"retest": {"side": side, "final": True, "hit_1r": ok, "hit_2r": ok,
                               "held_r": 2.5 if ok else -1.0}, "trend_day": ok}
    return [{"kind": "list", "day": day, "rows": rows},
            {"kind": "outcome", "day": day, "rows": out}]


def test_the_review_reads_the_record_by_side_with_days_equal() -> None:
    lines = _rec_day("2026-11-18", 8, long_ok=True) + _rec_day("2026-11-19", 8, long_ok=False)
    text = "\n".join(fit.premarket_lines(lines))
    assert "2 days, 16 names listed at 09:25, 16 gave an (L) retest" in text
    # One day all longs held and the next all shorts did: each side, days equal, is 50%.
    every = next(x for x in fit.premarket_lines(lines) if "every retest" in x)
    assert "long" in every and "50.0%" in every
    # Own move with the side: every one that held (by construction), on both sides.
    own = next(x for x in fit.premarket_lines(lines) if "own move with the side" in x)
    assert "100.0%" in own
    assert "no day with its outcome" in fit.premarket_lines([])[0]
