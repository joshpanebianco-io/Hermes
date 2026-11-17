"""
The weighed bias (bias.py): the sums, the grade's edges, the session each instant
reads, and the board and the tape read through it.

The worked example is ES at 06:15 ET on 5 November 2026, the read the owner saw
before asking for this: "Long, 5 of 16, moderate" under the old count.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import bias, drivers, marketctx, report

ET = ZoneInfo("America/New_York")


def _v(key: str, vote: str = "neutral", live: bool = True, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": key, "value": "v", "vote": vote, "note": "n", "live": live,
            **extra}


# ES at 06:15 ET, London's weights: seven reads shut, event risk not counted. The
# morning had three trend reads too (the daily frame flat, the 200-day and the
# ten-minute 200 EMA long); the board has not built them since 2026-11-15.
ES_0615 = [
    _v("yields", live=False), _v("dollar"), _v("credit", live=False), _v("vix_dir", live=False),
    _v("vix_curve", "long"), _v("prints", live=False), _v("gamma", "long"),
    _v("value"), _v("session", "long"),
    _v("sectors", live=False), _v("leaders", live=False),
    _v("hw_prints", live=False), _v("event_risk", damper=True),
]
TREND = [_v("frame", "long"), _v("daily200", "long"), _v("trend10m", "long")]


def test_the_worked_example_reads_as_the_owner_saw_it() -> None:
    r = bias.board_read("ES", ES_0615, "london", regime="POS", ny_open=False, events=5)
    # +48 on 85% until 2026-11-12, when gamma's long vote (spot above the flip) was one of
    # the reads. It is in no family now: the same morning read +45 on seven reads, over
    # the 84% of the weight that was live. Over the whole weight (2026-11-15) it was +38,
    # and with the trend reads out of the score the same day it is +28: structure is the
    # profile (flat) and the session's range (long), half of London's 44, and the VIX
    # curve all of risk's 6. The catalysts, 19 of the hundred, could not vote.
    assert (r["bias"], r["score"], r["grade"], r["coverage"]) == ("long", 28, "weak", 81)
    assert r["basis"] == "whole"
    assert (r["live"], r["cannot_vote"], r["total"]) == (4, 7, 11)
    assert r["weight_label"] == "London's weight"
    assert {f["short"]: f["score"] for f in r["families"] if f["score"] is not None} == {
        "Structure": 50, "Rates & dollar": 0, "Risk": 100}
    assert not {"positioning", "daily"} & {f["key"] for f in r["families"]}
    assert next(v for v in r["votes"] if v["key"] == "gamma")["family"] is None
    # Heaviest first, as the strip prints them.
    assert [f["short"] for f in r["families"]][:2] == ["Structure", "Rates & dollar"]
    # Weak's ceiling, a notch lower for the event on the tape.
    assert r["event_risk"] is True and r["max_conviction"] == 2
    assert "Event risk since the close (5)" in r["treatment"]
    assert r["treatment"].startswith("Lean long ES, weak (score +28, 4 of 11 reads live): ")


def test_a_trend_read_is_never_a_side() -> None:
    # Handed the three trend reads anyway (a stored board from before, or a caller that
    # still builds them), the score does not move and they are in no family.
    base = bias.board_read("ES", ES_0615, "london", regime="POS", ny_open=False)
    for side in ("long", "short"):
        trend = [dict(v, vote=side) for v in TREND]
        r = bias.board_read("ES", [*ES_0615, *trend], "london", regime="POS", ny_open=False)
        assert (r["score"], r["coverage"], r["live"], r["total"]) == (
            base["score"], base["coverage"], base["live"], base["total"])
        assert all(v["family"] is None for v in r["votes"]
                   if v["key"] in ("frame", "daily200", "trend10m"))
    assert not {"frame", "daily200", "trend10m"} & set(bias.BOARD_FAMILY)
    assert all("daily" not in w for w in bias.BOARD_WEIGHTS.values())
    assert all("daily" not in fams for fams in bias.BOOK_FAMILIES.values())


def test_gamma_is_never_a_side() -> None:
    # The same reads with spot above the flip, below it, and with no gamma at all: one score.
    rest = [_v("value", "long"), _v("session"), _v("credit", "short"), _v("yields", "short")]
    scores = {
        bias.board_read("NQ", [*rest, *extra], "ny_live", regime=regime, ny_open=True)["score"]
        for extra, regime in (([_v("gamma", "long")], "POS"), ([_v("gamma", "short")], "NEG"),
                              ([_v("gamma")], "POS"), ([], None))
    }
    assert len(scores) == 1
    # The regime still shapes how the score is treated, in either direction.
    pos = bias.board_read("NQ", rest, "ny_live", regime="POS", ny_open=True)
    neg = bias.board_read("NQ", rest, "ny_live", regime="NEG", ny_open=True)
    assert "ranges hold" in pos["treatment"] and "breaks run" in neg["treatment"]


def test_a_read_that_cannot_vote_is_on_neither_side_and_its_weight_still_counts() -> None:
    weights = {"a": 50, "b": 50}
    fam = {"x": "a", "y": "a", "z": "b"}
    # One long and one shut in a family: the shut one does not dilute its own family,
    # which is +100. The other family has nothing live, so half the weight says nothing
    # and the score is half way out, not all the way.
    shut = bias.read([_v("x", "long"), _v("y", live=False)], fam, weights, "session")
    assert shut["score"] == 50 and shut["coverage"] == 50
    assert next(f for f in shut["families"] if f["key"] == "a")["score"] == 100
    # Two reads, one long and one flat: a flat read is evidence of no lean.
    flat = bias.read([_v("x", "long"), _v("y")], fam, weights, "session")
    assert flat["score"] == 25 and flat["neutral"] == 1 and flat["cannot_vote"] == 0
    # A family with nothing live adds nothing to the sum and nothing to the coverage,
    # and a shut read's side is never read: this one says short and the score is long.
    two = bias.read([_v("x", "long"), _v("z", "short", live=False)], fam, weights, "session")
    assert two["score"] == 50 and two["coverage"] == 50
    assert next(f for f in two["families"] if f["key"] == "b")["score"] is None
    # The same family live and flat is the same score: no lean from it either way.
    level = bias.read([_v("x", "long"), _v("z")], fam, weights, "session")
    assert level["score"] == 50 and level["coverage"] == 100


def test_a_score_is_the_live_reads_agreement_times_the_weight_that_is_live() -> None:
    # Saturday 14 Nov 2026, 17:39 ET, the night the owner asked why the stocks mark was
    # a black circle. NQ on Asia's weights: the profile accepted higher, the session's
    # range flat, the VIX curve flat, the rest shut. (That night it read -21: the
    # ten-minute EMA cancelled the profile and the daily trend was the whole of the
    # lean. Neither is a read since 2026-11-15.)
    nq = [_v("value", "long"), _v("session"), _v("vix_curve"),
          *[_v(k, live=False) for k in ("yields", "dollar", "credit", "vix_dir", "prints",
                                        "hw_prints", "sectors", "leaders")]]
    r = bias.board_read("NQ", nq, "asia", regime="NEG", ny_open=False)
    # Structure half long on 53 of the hundred, risk flat on 7: +26 of the whole hundred,
    # where over the 60% that is live alone it would have read +44, moderate.
    assert (r["bias"], r["score"], r["coverage"], r["grade"]) == ("long", 26, 60, "weak")
    assert (r["live"], r["total"]) == (3, 11)
    # The shut reads live and flat instead: the same score, since shut and flat are both
    # no lean, and only the coverage says which it was.
    flat = bias.board_read("NQ", [dict(v, live=True) for v in nq], "asia", regime="NEG",
                           ny_open=False)
    assert (flat["score"], flat["coverage"]) == (26, 100)


def test_one_idea_has_one_voice() -> None:
    # Three reads of risk against one read of rates, equally weighted: the three do
    # not outvote the one, which is what a count let them do.
    votes = [_v("vix_dir", "long"), _v("vix_curve", "long"), _v("credit", "long"),
             _v("yields", "short")]
    r = bias.read(votes, bias.BOARD_FAMILY, {"risk": 50, "rates": 50}, "session")
    assert r["score"] == 0 and r["bias"] is None
    assert (r["agree"], r["against"]) == (3, 1)


def test_every_read_on_one_side_reaches_the_top_of_the_scale() -> None:
    votes = [_v(k, "short") for k in bias.BOARD_FAMILY]
    r = bias.read(votes, bias.BOARD_FAMILY, bias.BOARD_WEIGHTS["ny_live"], "ny_live")
    assert (r["score"], r["grade"], r["coverage"], r["max_conviction"]) == (-100, "strong", 100, 5)


@pytest.mark.parametrize(
    ("agree", "reads", "coverage", "score", "bias_word", "grade", "cap"),
    [(5, 6, 60, 50, "long", "strong", 5),        # five of six on 60% of the weight
     (49, 60, 60, 49, "long", "moderate", 4),
     (50, 59, 59, 50, "long", "moderate", 4),    # under 60% of the weight live: never strong
     (30, 100, 100, 30, "long", "moderate", 4), (29, 100, 100, 29, "long", "weak", 3),
     (10, 100, 100, 10, "long", "weak", 3), (9, 100, 100, 9, None, "none", 2),
     (-10, 100, 100, -10, "short", "weak", 3), (-9, 100, 100, -9, None, "none", 2),
     (-50, 100, 100, -50, "short", "strong", 5),
     # Every live read agrees, on a third of the weight: a third of the way out.
     (100, 100, 35, 35, "long", "moderate", 4), (100, 100, 9, 9, None, "none", 2),
     (0, 0, 0, 0, None, "none", 2)],
)
def test_the_grades_edges(agree: int, reads: int, coverage: int, score: int,
                          bias_word: str | None, grade: str, cap: int) -> None:
    # One live family of `reads`, `agree` of them on a side (negative: short), carrying
    # `coverage` of the weight; the rest of the weight is a family that cannot vote.
    n = abs(agree)
    side = "long" if agree >= 0 else "short"
    votes = [_v(f"r{i}", side if i < n else "neutral") for i in range(reads)]
    fam = {f"r{i}": "a" for i in range(reads)}
    fam["shut"] = "b"
    votes.append(_v("shut", live=False))
    weights = {"a": coverage, "b": 100 - coverage}
    r = bias.read(votes, fam, weights, "session")
    assert (r["score"], r["coverage"]) == (score, coverage)
    assert (r["bias"], r["grade"], r["max_conviction"]) == (bias_word, grade, cap)


def _conflicted() -> list[dict[str, Any]]:
    return [_v("yields", "short"), _v("dollar", "short"), _v("value", "long"),
            _v("session", "long")]


def test_a_conflict_takes_a_notch_off_the_grade_and_the_ceiling() -> None:
    r = bias.board_read("NQ", _conflicted(), "asia", regime="NEG", ny_open=False)
    assert r["conflict"] is True
    assert (r["macro_lean"], r["structure_lean"]) == ("short", "long")
    # Structure's 53 long against rates' 20 short: +33 of the whole weight would be
    # moderate; the conflict takes it to weak, and its ceiling with it.
    assert r["score"] == 33 and r["grade"] == "weak" and r["max_conviction"] == 3
    assert r["treatment"].startswith("Macro leans short on NQ but structure accepts long")
    # A small disagreement is not a conflict: a faint macro lean long against structure
    # half short. Both sides have to be at least 25 from flat.
    faint = [_v("vix_dir", "short"), _v("vix_curve"), _v("credit"), _v("yields", "long"),
             _v("dollar"), _v("value", "short"), _v("session")]
    read = bias.board_read("NQ", faint, "asia", regime=None, ny_open=False)
    assert (read["macro_lean"], read["structure_lean"]) == ("long", "short")
    assert read["conflict"] is False


def test_event_risk_takes_a_notch_off_the_ceiling_and_never_a_side() -> None:
    votes = [_v(k, "long") for k in ("value", "session")]
    quiet = bias.board_read("NQ", votes, "asia", regime=None, ny_open=False)
    risky = bias.board_read("NQ", [*votes, _v("event_risk", damper=True)], "asia", regime=None,
                            ny_open=False, events=2)
    assert quiet["score"] == risky["score"] and quiet["total"] == risky["total"]
    assert risky["max_conviction"] == quiet["max_conviction"] - 1
    assert "Event risk since the close (2)" in risky["treatment"]
    assert "Event risk" not in quiet["treatment"]


# ---- which weights each instant reads, boundaries included ---------------------------


@pytest.mark.parametrize(
    ("when", "key"),
    [
        # A Thursday in November, when London is five hours ahead of New York.
        ((2026, 11, 5, 1, 59), "asia"),
        ((2026, 11, 5, 2, 0), "london"),
        ((2026, 11, 5, 7, 29), "london"),
        ((2026, 11, 5, 7, 30), "ny_pre"),     # New York takes over two hours before its bell
        ((2026, 11, 5, 9, 29), "ny_pre"),
        ((2026, 11, 5, 9, 30), "ny_live"),
        ((2026, 11, 5, 15, 59), "ny_live"),
        ((2026, 11, 5, 16, 0), "asia"),       # the close: Asia opens next
        ((2026, 11, 5, 17, 59), "asia"),
        ((2026, 11, 5, 18, 0), "asia"),
        # The weekend reads the session that opens next, which is Asia on Sunday.
        ((2026, 11, 6, 15, 59), "ny_live"),
        ((2026, 11, 7, 12, 0), "asia"),
        ((2026, 11, 8, 17, 59), "asia"),
    ],
)
def test_the_weights_follow_the_clock(when: tuple[int, int, int, int, int], key: str) -> None:
    assert drivers.weights_for(datetime(*when, tzinfo=ET)) == key


def test_every_session_weighs_to_a_hundred_and_names_every_family() -> None:
    for table, family_of in ((bias.BOARD_WEIGHTS, bias.BOARD_FAMILY),
                             (bias.TAPE_WEIGHTS, bias.TAPE_FAMILY)):
        for name, weights in table.items():
            assert sum(weights.values()) == 100, name
            assert set(weights) == set(family_of.values()), name
            assert name in bias.WEIGHT_LABEL


# ---- the board and the tape read through it --------------------------------------------


def test_the_board_says_which_reads_cannot_vote_at_this_hour() -> None:
    night = datetime(2026, 11, 5, 6, 15, tzinfo=ET)
    quotes = [{"key": "NQ", "last": 28000.0, "pct": -0.5, "chg": -100.0, "feed": "delayed"},
              {"key": "US10Y", "last": 4.89, "pct": 0.0, "chg": -0.058, "feed": "closed"},
              {"key": "HYG", "last": 77.0, "pct": 0.7, "chg": 0.5, "feed": "closed"},
              {"key": "DXY", "last": 101.5, "pct": -0.06, "chg": -0.1, "feed": "live"}]
    board = drivers.build({"quotes": quotes}, "pre", night)
    assert board["weights"] == "london"
    nq = board["books"]["NQ"]
    votes = {v["key"]: v for v in nq["votes"]}
    assert votes["yields"]["live"] is False and votes["credit"]["live"] is False
    assert votes["sectors"]["live"] is False and votes["leaders"]["live"] is False
    assert votes["dollar"]["live"] is True      # inside its band: flat, not absent
    assert nq["live"] == 1 and nq["total"] == 11
    assert nq["weight_label"] == "London's weight"
    # A dollar that has stopped printing cannot vote either.
    stopped = [dict(q, feed="closed") if q["key"] == "DXY" else q for q in quotes]
    gone = drivers.build({"quotes": stopped}, "closed", night)["books"]["NQ"]
    assert {v["key"]: v for v in gone["votes"]}["dollar"]["live"] is False


def test_gold_never_counts_the_equity_vol_reads() -> None:
    quotes = [{"key": "GC", "last": 4000.0, "pct": 1.0, "feed": "delayed"},
              {"key": "VIX", "last": 16.0, "pct": -5.0, "feed": "live"},
              {"key": "VIX3M", "last": 19.0, "pct": -1.0, "feed": "live"}]
    gc = drivers.build({"quotes": quotes}, "rth", datetime(2026, 11, 5, 10, 30, tzinfo=ET))
    votes = {v["key"]: v for v in gc["books"]["GC"]["votes"]}
    assert votes["vix_dir"]["live"] is False and votes["vix_curve"]["live"] is False


def test_the_tape_weighs_by_its_own_hour() -> None:
    assert bias.tape_key("pre") == bias.tape_key("closed") == "before_open"
    assert bias.tape_key("rth") == bias.tape_key("post") == "session"
    levels = [_v("spy_levels", "long"), _v("qqq_levels", "long")]
    rest = [_v(k) for k in ("yields", "dollar", "vix_dir", "vix_curve", "credit")]
    shut = [_v(k, live=False) for k in ("sectors", "equal_weight", "index_volume", "participation")]
    pre = marketctx.conviction([*levels, *rest, *shut], "pre")
    assert (pre["score"], pre["coverage"], pre["grade"]) == (35, 100, "moderate")
    assert (pre["live"], pre["cannot_vote"]) == (7, 4)
    assert pre["weight_label"] == "the pre-open's weight"
    # The same reads in the session, with participation live and flat.
    live = [*levels, *rest, *[_v(k) for k in ("sectors", "equal_weight", "index_volume",
                                              "participation")]]
    rth = marketctx.conviction(live, "rth")
    assert (rth["score"], rth["coverage"], rth["grade"]) == (35, 100, "moderate")
    assert rth["weight_label"] == "the session's weight"


def test_a_lean_on_two_reads_is_a_thin_one() -> None:
    # 20:13 ET on Tue 10 Nov 2026: only SPY and QQQ against their levels could vote, both
    # a third of a percent up after hours. The card read "Long +100, moderate", capped at 4.
    levels = [_v("spy_levels", "long"), _v("qqq_levels", "long")]
    names = ("yields", "dollar", "vix_dir", "vix_curve", "credit", "sectors", "equal_weight",
             "index_volume", "participation")
    night = marketctx.conviction([*levels, *[_v(k, live=False) for k in names]], "closed")
    got = {k: night[k] for k in ("bias", "score", "coverage", "grade", "max_conviction", "thin")}
    # +35, not +100: the two reads are 35% of the weight and the rest says nothing. On
    # its own that is moderate, so the thin rule still holds the grade at weak.
    assert got == {"bias": "long", "score": 35, "coverage": 35, "grade": "weak",
                   "max_conviction": 3, "thin": True}
    assert (night["live"], night["total"]) == (2, 11)
    # Once the VIX, credit and the curve can vote too it is 70% of the weight: not thin.
    risk = [_v(k, "long") for k in ("vix_dir", "vix_curve", "credit")]
    off = [_v(k, live=False) for k in ("yields", "dollar", "sectors", "equal_weight",
                                       "index_volume", "participation")]
    pre = marketctx.conviction([*levels, *risk, *off], "pre")
    assert (pre["score"], pre["coverage"], pre["grade"], pre["thin"]) == (70, 70, "strong", False)
    # No lean at all is not a thin lean.
    flat = marketctx.conviction([_v("spy_levels"), _v("qqq_levels"),
                                 *[_v(k, live=False) for k in names]], "closed")
    assert (flat["bias"], flat["grade"], flat["thin"]) == (None, "none", False)
    # The futures board reads as it did: this is the tape's rule.
    board = bias.read([_v("value", "long")], bias.BOARD_FAMILY, bias.BOARD_WEIGHTS["asia"], "asia")
    assert (board["score"], board["coverage"], board["grade"]) == (53, 53, "moderate")
    assert "thin" not in board


# ---- a note written for another session is capped by that session's weights ------------


def test_a_note_for_another_session_is_read_with_its_weights() -> None:
    votes = [_v(k, "long") for k in ("value", "session")]
    votes += [_v("yields", "short"), _v("dollar", "short"), _v("gamma", "short")]
    # In Asia the structure carries it; in the New York pre-open the macro does.
    asia = bias.board_read("NQ", votes, "asia", regime=None, ny_open=False)
    assert asia["score"] > 0
    ny = bias.board_read("NQ", votes, "ny_pre", regime=None, ny_open=False)
    assert ny["score"] < asia["score"]
    snap = {"drivers": {"ny_open": False, "books": {"NQ": {**asia, "key": "NQ"}}}}
    at = datetime(2026, 11, 5, 20, 30, tzinfo=ET)
    assert report._drivers(snap, ["NQ"], "asia", at)["NQ"]["score"] == asia["score"]
    written = report._drivers(snap, ["NQ"], "ny", at)["NQ"]
    assert written["score"] == ny["score"]
    assert written["weights_for"] == "the New York pre-open's weight"
    assert written["votes"][0]["can_vote_now"] is True
