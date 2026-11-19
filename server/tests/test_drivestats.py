"""
The bias's yardsticks (drivestats.py) and its record (bias_record.py), 2026-11-19.

What is pinned: a move is measured in its own usual day from completed bars only; two
markets' days line up by date across a holiday; a co-mover votes on what the book's own
move does not explain; a macro driver votes only while it has been driving; and the
record's marks, sessions and outcomes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import bias_record as br
from newsterminal import drivestats as ds

ET = ZoneInfo("America/New_York")


def _row(key: str, closes: list[float], start: date = date(2026, 8, 3),
         skip: tuple[int, ...] = ()) -> dict[str, Any]:
    """A context row with one close a weekday from `start`, leaving out the indexes in
    `skip` (a holiday that market kept)."""
    days, out, d = [], [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if i not in skip:
            days.append(d.isoformat())
            out.append(c)
        d += timedelta(days=1)
    return {"key": key, "hist": {"days": days, "closes": out}}


def _walk(n: int, steps: list[float], base: float = 100.0) -> list[float]:
    out = [base]
    for i in range(n - 1):
        out.append(out[-1] * (1 + steps[i % len(steps)] / 100.0))
    return out


TODAY = date(2026, 11, 19)


def test_a_usual_day_is_the_mean_size_of_the_last_twenty_completed_days() -> None:
    # Moves of +1% and -1% alternating: the usual day is 1%, and a bar dated today (still
    # forming, here a +50% print) is not one of them.
    row = _row("DXY", _walk(40, [1.0, -1.0]))
    row["hist"]["days"].append(TODAY.isoformat())
    row["hist"]["closes"].append(row["hist"]["closes"][-1] * 1.5)
    u, measured = ds.Stats([row], TODAY).usual("DXY")
    assert measured and u == pytest.approx(1.0, rel=0.02)
    # A yield's day is said in basis points.
    tnx = _row("US10Y", [4.0 + (0.05 if i % 2 else 0.0) for i in range(40)])
    u, _ = ds.Stats([tnx], TODAY).usual("US10Y")
    assert u == pytest.approx(5.0, rel=0.01)


def test_too_little_history_falls_back_to_a_stated_usual_day() -> None:
    u, measured = ds.Stats([_row("VIX", [15.0, 16.0, 15.0])], TODAY).usual("VIX")
    assert (u, measured) == (ds.FALLBACK_USUAL["VIX"], False)


def test_a_move_counts_from_half_a_usual_day_and_in_full_from_one_and_a_half() -> None:
    assert [ds.strength(m) for m in (0.4, 0.5, 1.0, 1.5, 3.0)] == [0.0, 0.0, 0.5, 1.0, 1.0]


def test_a_co_mover_is_read_beyond_the_books_own_move() -> None:
    # The VIX moved -4x the index, every day, plus noise of +-0.5: beta near -4. A day
    # the index is -1% and the VIX up by its beta is the echo; two points of fear more
    # than that is several usual remainders beyond it.
    idx_steps = [1.0, -0.5, 0.8, -1.2, 0.3, -0.7]
    noise = [0.5, -0.5, 0.5, -0.5, -0.5, 0.5]
    idx = _walk(70, idx_steps, 5000.0)
    vix = [20.0]
    for i in range(69):
        vix.append(vix[-1] * (1 + (-4 * idx_steps[i % 6] + noise[i % 6]) / 100.0))
    st = ds.Stats([_row("ES", idx), _row("VIX", vix)], TODAY)
    link = st.link("VIX", "ES")
    assert link is not None and link["beta"] == pytest.approx(-4.0, abs=0.5)
    assert link["corr"] < -0.9
    echo = -link["beta"]
    vote, s, note = ds.surprise(st, "VIX", echo, "ES", -1.0, "the S&P", "short", ("up", "down"))
    assert vote == "neutral" and "echo" in note
    vote, s, _ = ds.surprise(st, "VIX", echo + 2.0, "ES", -1.0, "the S&P", "short",
                             ("up", "down"))
    assert vote == "short" and s == 1.0
    # The mirror: the index up 1% and the VIX down by less than its beta says.
    vote, s, _ = ds.surprise(st, "VIX", -echo + 2.0, "ES", 1.0, "the S&P", "short",
                             ("up", "down"))
    assert vote == "short" and s == 1.0


def test_two_markets_line_up_by_date_across_a_holiday() -> None:
    # The cash market shut on the tenth bar; the future traded. The link is read on the
    # days both have, not by position, so the series do not slip a day out of step.
    steps = [1.0, -1.0, 0.5, -0.5]
    fut = _row("ES", _walk(70, steps))
    cash = _row("HYG", _walk(70, [s * 0.3 for s in steps]), skip=(10,))
    link = ds.Stats([fut, cash], TODAY).link("HYG", "ES")
    assert link is not None and link["corr"] > 0.9


def test_a_macro_driver_votes_only_while_it_has_been_driving() -> None:
    steps = [1.0, -0.6, 0.4, -0.9, 0.7, -0.2]
    idx = _walk(70, steps)
    against = _row("DXY", _walk(70, [-s for s in steps]))
    together = _row("DXY", _walk(70, steps))
    assert ds.driving(ds.Stats([_row("ES", idx), against], TODAY), "DXY", "ES", -1)[0]
    ok, corr = ds.driving(ds.Stats([_row("ES", idx), together], TODAY), "DXY", "ES", -1)
    assert not ok and corr is not None and corr > 0.9
    note = ds.gate_note(ds.Stats([_row("ES", idx), together], TODAY), "DXY", "ES", -1,
                        "the S&P", "The dollar")
    assert note is not None and "not a driver now" in note
    # Unmeasured is taken as driving: it votes as it always did.
    assert ds.driving(ds.Stats(None, TODAY), "DXY", "ES", -1) == (True, None)


def test_breadth_counts_by_how_one_sided_it_is() -> None:
    assert ds.breadth_strength(24, 16) == pytest.approx(1 / 3)
    assert ds.breadth_strength(32, 8) == 1.0 and ds.breadth_strength(0, 0) == 0.0


# ---- the record ------------------------------------------------------------------------


def _et(*a: int) -> datetime:
    return datetime(*a, tzinfo=ET)


@pytest.mark.parametrize(("when", "want"), [
    ((2026, 11, 18, 20, 5), ("2026-11-19", "20:00")),   # Wednesday evening: Thursday's
    ((2026, 11, 19, 3, 31), ("2026-11-19", "03:30")),
    ((2026, 11, 19, 8, 59), ("2026-11-19", "08:45")),
    ((2026, 11, 19, 9, 1), None),                        # past 08:45's slack, before 09:25
    ((2026, 11, 20, 20, 5), None),                       # Friday evening: Globex is shut
    ((2026, 11, 22, 20, 5), ("2026-11-23", "20:00")),   # Sunday evening: Monday's
    ((2026, 11, 21, 10, 30), None),                      # Saturday
    ((2026, 11, 26, 10, 30), None),                      # Thanksgiving
    ((2026, 11, 27, 14, 0), None),                       # the half day has shut at 13:00
    ((2026, 11, 27, 12, 0), ("2026-11-27", "12:00")),
])
def test_a_mark_falls_due_once_for_the_session_it_is_for(when: tuple[int, ...],
                                                         want: tuple[str, str] | None) -> None:
    now = _et(*when)
    assert br.due_mark(now, set()) == want
    if want:
        assert br.due_mark(now, {want}) is None


def test_the_close_is_written_in_its_half_hour_on_a_trading_day() -> None:
    assert br.close_due(_et(2026, 11, 19, 16, 5), set()) == "2026-11-19"
    assert br.close_due(_et(2026, 11, 19, 16, 5), {"2026-11-19"}) is None
    assert br.close_due(_et(2026, 11, 19, 16, 45), set()) is None
    assert br.close_due(_et(2026, 11, 27, 13, 10), set()) == "2026-11-27"   # half day
    assert br.close_due(_et(2026, 11, 21, 16, 5), set()) is None             # Saturday


def test_a_read_is_judged_on_its_sessions_close_in_its_books_usual_days() -> None:
    now = datetime(2026, 11, 19, 1, 5, tzinfo=UTC)   # 20:05 ET the evening before
    r = {"session_key": "asia", "score": 70, "grade": "moderate", "bias": "long",
         "coverage": 100, "conflict": False, "backers": 1,
         "families": [{"key": "structure", "weight": 70, "score": 100, "points": 70.0}],
         "votes": [{"key": "value", "vote": "long", "live": True, "family": "structure"},
                   {"key": "gamma", "vote": "neutral", "live": True, "family": None}]}
    read = br.read_line("2026-11-19", "20:00", now, "NQ", r, 27_500.0, 1.19, 1.25)
    assert read["families"] == {"structure": [70, 100, 70.0]}
    assert set(read["votes"]) == {"value"}            # no family, not logged as a vote
    tape = br.read_line("2026-11-19", "20:00", now, br.TAPE, {**r, "bias": "short"},
                        7_400.0, 0.6, 0.9)
    close = br.close_line("2026-11-19", now, {"NQ": 27_775.0, "ES": 7_363.0, "GC": None})
    got = {o["book"]: o for o in br.outcomes([read, tape, close])}
    assert got["NQ"]["move"] == pytest.approx(1.0) and got["NQ"]["hit"] is True
    assert got["NQ"]["in_usual"] == pytest.approx(0.8)
    # The tape is judged on the S&P future: down 0.5%, its short was right.
    assert got[br.TAPE]["move"] == pytest.approx(-0.5) and got[br.TAPE]["hit"] is True
    assert "GC" not in close["last"]
    marks, closes = br.done_keys([read, close])
    assert marks == {("2026-11-19", "20:00")} and closes == {"2026-11-19"}
