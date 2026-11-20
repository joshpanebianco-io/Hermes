"""
The scanner's event log — the feed alerts are raised from, and the record the
score will one day be judged against.

WHY THE ENGINE KEEPS IT, NOT THE PAGE. The Pine script alerts on its signals; the
terminal now does too (owner instruction, 2026-10-13: alerts, and "signal
logging so the score can be calibrated"). An alert raised by diffing two polls
in the browser would fire twice in two tabs, never fire with the page closed,
and leave no record. So the collector detects each signal once, gives it an id
that keeps counting across restarts, and the page only asks "anything after
id N?".

WHAT IS AN EVENT. The script's own signals on confirmed ten-minute bars — an (L)
retest, an (E) trigger, a ◆ breakout — and NEAR: a name ninety per cent of the
way to a level during the regular session, the script's "about to break". They
are read off the same replay the scanner row is built from; nothing new is
fetched for them.

LIVE OR BACKFILLED. After a restart the replay finds the morning's signals all
over again. Those already in the file are recognised by their key (day, name,
kind, side, level, bar) and skipped; any it did not have are logged, but marked
`live: false` — found more than two bars after the bar closed — so the page
records them without alerting on a signal from two hours ago. A backfilled
event carries NO score (audit, 2026-10-14): the score its row has when the
replay finds it is the score hours later — 0 after the close — and the record
would file a strong signal under "score < 40".

ONLY FINAL BARS, AND A SECOND LOOK (audit, 2026-10-14). A signal is read off a
bar only once that name's bars were downloaded after the bar closed
(scan.CLOSE_LAG_SEC). Yahoo still revises a bar now and then — a pre-market
print dropped, a late trade added — so every logged (L), (E) and breakout is
checked again against the newest final bars (`revalidate`): one that no longer
exists is RETRACTED (kept, flagged, out of the record and announced as
withdrawn), and one whose price or stop moved is corrected, the first figures
kept beside it. A finished day is settled once more against bars read after
its close (`settle`) and marked `checked`.

THE OUTCOME OF EVERY (L) AND (E). Entry is the signal price, the stop is the
script's own "stop idea" (the (L) bar's low/high, the (E) candle's), and R is
the distance between them. From the signal on, the log tracks the best and
worst excursion in R, whether +1R (and +2R) came before the stop, and where
price stood 30 and 60 minutes after the signal bar and at the close. That is
the dataset the heuristic weights in scanscore.py can later be fitted to.

NEVER NEARER THAN THE RETEST BUFFER (owner, 2026-11-11: "do what you recommend").
A signal bar that closes on its low puts the script's stop two cents away (or on
the entry itself), and the record counted that as the trade. So R is the stop's
distance or the signal's `risk_min` (a quarter of the ten-minute ATR at its bar,
the script's own buffer), whichever is larger, and the stop is counted hit that
far from the entry. `outcome.floored` says when the floor is what set it, and
the stop shown is still the script's. Signals settled before that date were
worked again from the bars still held (`EventLog.refloor`), their first outcome
kept under `outcome_raw`; the ones whose bars were gone stay as they were, and
`stats` counts how many of each the record holds.

HOW FAR IT REACHES: 84 of the 893 settled signals read with it, 9%, every one an
(L), which on the script's own stop reached +1R 30% of the time against 41 to
52% for the bands above (the table is beside scan.risk_of). It is NOT the third
of the record the first audit counted: that was stops under 0.25% of price, and
a quarter of the ten-minute ATR is about 0.13% of price.

ON A TEN-MINUTE BAR THE ORDER INSIDE IT IS UNKNOWN. When one bar reaches both
+1R and the stop, the log counts it STOPPED — the conservative reading, since a
record that flatters the strategy is worse than none. Outcomes are read off the
5-minute bars, which halves how often that happens.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import statistics
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .config import CACHE_DIR
from .holidays import close_minute
from .scan import (
    ATR_LEN,
    BAR_SEC,
    BUF_MULT,
    CLOSE_LAG_SEC,
    ET,
    SRC_SEC,
    TF_SEC,
    Bar,
    atr,
    fmt_px,
    resample,
    risk_of,
    rth_bar_days,
)

EVENTS_FILE = os.path.join(CACHE_DIR, "scanner_events.jsonl")
#: The list as it stood before the bell, one line a day, beside the events: the
#: pre-open rank is what the game plan picks from, and nothing else records it.
PREOPEN_NAME = "scanner_preopen.jsonl"
#: The last look before the open: from this minute, once a day.
PREOPEN_AT = time(9, 25)
#: A held trade's R is capped here, so one tiny stop cannot carry an average.
HELD_CAP = 5.0
#: A TOUCH TO THE CENT COUNTS (the both-sides audit, 2026-11-14). Yahoo's bars carry
#: single-precision prices: 20.82 arrives as 20.81999969482422. HIMS's (E) long of 11 Nov
#: 14:30, entry 20.66 and stop 20.50 (R 0.16), made a high of 20.82 at 15:00, +1R to the
#: cent, and the bars said 0.15999969: it was filed as never reaching +1R and stopped at
#: 15:25 (whose low, 20.50, is a number a float holds exactly). The same trade turned
#: upside down came out a winner, which is how it was found. The target and the stop are
#: reached within this share of the price: a single-precision price is out by at most
#: 6e-8 of itself and a difference of two by twice that, and a quarter of a millionth of
#: the price is 0.0005c on a $20 stock and 0.025c on a $1,000 one, under any tick.
TOUCH_REL = 2.5e-7
KEEP_DAYS = 30
#: A day whose last bars never arrived settles anyway this long after its
#: close, on what there is — the bars will not get any better.
SETTLE_ANYWAY_SEC = 3600
#: Retractions the alert feed reports, by day: today's and the session before.
RETRACT_DAYS = 2
KINDS = ("L", "E", "V", "BO")
NEAR = "NEAR"
NEAR_PCT = 0.90
#: The kinds with an entry, a stop and an outcome. (V), the VWAP retest after an
#: extended run, from 2026-11-19 (scan.replay).
TRADES = ("L", "E", "V")

_LABEL = {"L": "(L)", "E": "(E)", "V": "(V)", "BO": "◆", NEAR: "Near"}

# EVERY CHART'S SIGNALS (owner, 2026-11-19: "it should print signals on both if it happens
# on 3m, 5m and 10m"). Each event names its chart (`tf`; one logged before then, or with
# none, is the 10m's). The same retest usually prints on two or three charts minutes
# apart, so ONE ALERTS: an event whose kind, side and level already printed on another
# chart within SAME_SETUP_SEC is logged with `alert: false` and `after` (those charts),
# and the page raises no alert for it (owner's choice: "first one only"). The record
# (`stats`, `record_table`, tools/fit_score.py's main tables) stays the 10m chart's, so it
# runs on from before; fit_score reads the charts against each other apart.
SAME_SETUP_SEC = 2 * BAR_SEC
TF_DEFAULT = "10m"


def tf_of(ev: dict[str, Any]) -> str:
    """The chart an event or signal was read on; the 10m when it says none. Pure."""
    tf = ev.get("tf")
    return tf if isinstance(tf, str) and tf in TF_SEC else TF_DEFAULT


def bar_sec(ev: dict[str, Any]) -> int:
    """The length of the bar an event fired on, in seconds. Pure."""
    return TF_SEC[tf_of(ev)]


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def _hm(t: float) -> str:
    return datetime.fromtimestamp(t, ET).strftime("%H:%M")


def dedupe_key(ev: dict[str, Any]) -> str:
    """One signal is one event however often the replay finds it. NEAR is once per
    level per day, whatever bar it was first seen on."""
    if ev["kind"] == NEAR:
        return f"{ev['day']}|{ev['sym']}|NEAR|{ev['level']}"
    # A faster chart's signal names its chart, so a 5m and a 10m bar opening at the same
    # minute are two events; the 10m's key is the one it always had.
    tf = tf_of(ev)
    return (f"{ev['day']}|{ev['sym']}|{ev['kind']}|{ev['side']}|{ev['level']}|{ev['t']}"
            + ("" if tf == TF_DEFAULT else f"|{tf}"))


def held_r(outcome: dict[str, Any] | None) -> float | None:
    """What holding to the close made: -1 R if the stop went first, else the close,
    capped at HELD_CAP. Pure.

    THE STOP IS PART OF THE TRADE (2026-11-05). `ret_close_r` reads the close whatever
    happened on the way, so a signal stopped out and recovered counted as a win, and
    one stop a tenth of a percent wide could carry a group: the record showed score
    under 40 averaging +4.9 R, which made the worst-ranked names look the best."""
    o = outcome or {}
    if o.get("stopped"):
        return -1.0
    c = o.get("ret_close_r")
    return max(-1.0, min(HELD_CAP, float(c))) if isinstance(c, int | float) else None


def blank_outcome() -> dict[str, Any]:
    return {"r": None, "mfe_r": None, "mae_r": None, "hit_1r": None, "hit_2r": None,
            "stopped": None, "ret_30m_r": None, "ret_60m_r": None, "ret_close_r": None,
            "final": False}


#: The earliest bars a floor is worked back from: the ten-minute ATR needs its
#: fourteen bars and a few dozen more before it has settled on the name's range.
REFLOOR_MIN_BARS = 60


def _event(sym: str, kind: str, side: str, level: str | None, bar_t: int, price: float,
           stop: float | None, score: int | None, note: str, day: str,
           now_ts: float, parts: dict[str, Any] | None = None,
           ctx: dict[str, Any] | None = None, risk_min: Any = None,
           tf: str | None = None) -> dict[str, Any]:
    tf = tf if tf in TF_SEC else TF_DEFAULT
    # Live within two of its own bars, and never less than one ten-minute bar: Yahoo's
    # bars land minutes late, and a 3m signal found seven minutes on was still found
    # by the rotation, not by a restart's replay.
    live = now_ts - (bar_t + TF_SEC[tf]) <= max(2 * TF_SEC[tf], BAR_SEC)
    ev: dict[str, Any] = {
        "id": 0,
        "ts": _iso(now_ts),
        "bar_ts": _iso(bar_t),
        "t": bar_t,
        "at_et": _hm(bar_t),
        "day": day,
        "sym": sym,
        "kind": kind,
        "side": side,
        "level": level,
        "tf": tf,
        "price": round(float(price), 4),
        "stop": round(float(stop), 4) if stop is not None else None,
        # The least the stop's distance is counted as (module docstring).
        "risk_min": (round(float(risk_min), 4)
                     if kind in TRADES and isinstance(risk_min, (int, float)) and risk_min > 0
                     else None),
        # The row's score NOW — which is the signal's only when found live.
        "score": score if live else None,
        # The score's parts at the signal (2026-10-22), for tools/fit_score.py:
        # {key: {pts, max}}. Live signals only, like the score.
        "parts": parts if (live and parts) else None,
        "note": note,
        "live": live,
        "outcome": blank_outcome() if kind in TRADES else None,
    }
    # What the next audit needs and the parts cannot say (2026-11-05): where the name
    # stood on the table, its stop's room and the raw figures behind the points, with
    # the 1-hour RS beside the day's, which includes the gap.
    if live and ctx:
        ev["ctx"] = ctx
    return ev


def score_parts(score: dict[str, Any] | None) -> dict[str, Any] | None:
    """A row's score parts as the log keeps them: {key: {pts, max}}. Pure."""
    parts = (score or {}).get("parts") if isinstance(score, dict) else None
    if not isinstance(parts, list):
        return None
    out = {str(p["key"]): {"pts": p.get("pts"), "max": p.get("max")}
           for p in parts if isinstance(p, dict) and p.get("key")}
    return out or None


def signal_events(sym: str, signals: Iterable[dict[str, Any]], score: int | None, day: str,
                  now_ts: float, parts: dict[str, Any] | None = None,
                  ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The (L) / (E) / breakout events one name's replayed signals imply. Pure."""
    out: list[dict[str, Any]] = []
    for sg in signals:
        kind = sg.get("kind")
        if kind not in KINDS or sg.get("t") is None or sg.get("price") is None:
            continue
        side = str(sg.get("side"))
        text = str(sg.get("note") or "")
        tf = tf_of(sg)
        # The chart is the event's `tf`, which the pages print beside the note.
        note = f"{_LABEL[kind]} {side} — {text[:1].lower()}{text[1:]}"
        out.append(_event(sym, kind, side, sg.get("level"), int(sg["t"]), sg["price"],
                          sg.get("stop"), score, note, day, now_ts, parts, ctx,
                          risk_min=sg.get("risk_min"), tf=tf))
    return out


def same_setup(ev: dict[str, Any], events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events already logged for the same setup on ANOTHER chart: the same day, name,
    kind, side and level, whose bars closed within SAME_SETUP_SEC of this one's. Pure."""
    if ev.get("kind") not in KINDS:
        return []
    end = int(ev["t"]) + bar_sec(ev)
    return [e for e in events
            if e.get("day") == ev.get("day") and e.get("sym") == ev.get("sym")
            and e.get("kind") == ev.get("kind") and e.get("side") == ev.get("side")
            and e.get("level") == ev.get("level") and tf_of(e) != tf_of(ev)
            and not e.get("retracted")
            and abs(int(e["t"]) + bar_sec(e) - end) <= SAME_SETUP_SEC]


def news_ctx(score: dict[str, Any] | None,
             read_of: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """What the catalyst part read, as the log keeps it: its points, the item that decided
    it (grade, tier, direction, whether with the side, where the direction came from —
    the name's move, the event's words, the tape, a report or a filing — and its age), how
    many headlines were in the window and how many the tape overruled. None without a
    catalyst part. Pure.

    AND, from 2026-11-14, two things that are logged and never scored, so the record can
    say whether they should be: `prior`, the previous session's major story (its grade and
    age; scanscore.prior_story), and `size`, how big the model read the deciding story to
    be (`read_of` is the row's `news_read`; newsread.py). `with` is None for a story that
    reads no way, which pays since the same day."""
    parts = (score or {}).get("parts") if isinstance(score, dict) else None
    part = next((p for p in parts or [] if isinstance(p, dict) and p.get("key") == "catalyst"),
                None)
    if part is None:
        return None
    raw_read = part.get("read")
    read: dict[str, Any] = raw_read if isinstance(raw_read, dict) else {}
    raw_item = read.get("item")
    item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
    raw_prior = read.get("prior")
    prior = ({k: raw_prior.get(k) for k in ("tag", "tier", "age_min")}
             if isinstance(raw_prior, dict) else None)
    size = read_of.get("size") if isinstance(read_of, dict) else None
    # From 2026-11-18: which way the model read it, and whether it had the story's text.
    mdir = read_of.get("direction") if isinstance(read_of, dict) else None
    mtext = read_of.get("text") if isinstance(read_of, dict) else None
    return {"pts": part.get("pts"), "tag": item.get("tag"), "tier": item.get("tier"),
            "dir": item.get("dir"), "with": item.get("with"), "src": item.get("src"),
            "age_min": item.get("age_min"), "fresh": read.get("fresh"),
            "set_aside": read.get("set_aside"), "prior": prior, "size": size,
            "mdir": mdir, "mtext": mtext}


def tape_ctx(regime: dict[str, Any] | None) -> dict[str, Any] | None:
    """The tape's bias as the log keeps it beside a signal (from 2026-11-19). Pure.

    WHY (owner, 2026-11-19, "do what you recommend"): the two-year backfill found the
    bias calls no index's close, and the bias is not used as a forecast of the close —
    it is the weather a stock trade is taken in. Whether trading with it pays can only be
    read on the trades, and the log kept only the Market part's points, which come from
    the scanner's own vote count (scanscore.regime), not from the bias. So each live
    signal carries both, as they stood in the payload it was found in:

      score, grade, bias, coverage, backers, conflict, weights   bias.py's tape read
          (the Scanner's `regime.conviction`, what the Market line and the Game plan say);
      fam    what each of its families put on the score, in points;
      vote   the regime's vote count's side, the one "tape agrees" pays (None: no lean).

    Logged, never scored: nothing here moves a rank. tools/fit_score.py reads it
    (`bias_lines`). None without a regime."""
    if not isinstance(regime, dict):
        return None
    vote = regime.get("bias") if regime.get("bias") in ("long", "short") else None
    c = regime.get("conviction")
    if not isinstance(c, dict):
        return {"score": None, "grade": None, "bias": None, "vote": vote}
    fams = c.get("families") or []
    return {"score": c.get("score"), "grade": c.get("grade"),
            "bias": c.get("bias") if c.get("bias") in ("long", "short") else None,
            "coverage": c.get("coverage"), "backers": c.get("backers"),
            "conflict": c.get("conflict"), "weights": c.get("session_key"),
            "fam": {str(f["key"]): f.get("points") for f in fams
                    if isinstance(f, dict) and f.get("key")},
            "vote": vote}


def shape_ctx(r: dict[str, Any]) -> dict[str, Any]:
    """A row's own day shape in its daily ATRs: yesterday's range and close position,
    the pre-market range, and the gap (the pre-market last against the previous close
    while the pre-market is on, else nothing). Pure; None where a figure is missing."""
    lv = r.get("levels") or {}
    atr = r.get("atr_d")
    pdh, pdl, prev = lv.get("pdh"), lv.get("pdl"), r.get("prev_close")
    pmh, pml = lv.get("pmh"), lv.get("pml")
    pm_last = (r.get("premkt") or {}).get("last")
    ok = lambda *xs: all(isinstance(x, int | float) and not isinstance(x, bool) for x in xs)  # noqa: E731
    out: dict[str, Any] = {"pd_range_atr": None, "pd_close_pos": None, "pm_range_atr": None,
                           "gap_atr": None}
    if ok(pdh, pdl, atr) and atr > 0:
        out["pd_range_atr"] = round((pdh - pdl) / atr, 3)
        if ok(prev) and pdh > pdl:
            out["pd_close_pos"] = round((prev - pdl) / (pdh - pdl), 3)
    if ok(pmh, pml, atr) and atr > 0:
        out["pm_range_atr"] = round((pmh - pml) / atr, 3)
    if ok(pm_last, prev, atr) and atr > 0:
        out["gap_atr"] = round((pm_last - prev) / atr, 3)
    return out


def candidates(rows: Iterable[dict[str, Any]], session: str, day: str,
               now: datetime, tape: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every event the payload's rows imply right now — new or not. `tape` is the
    payload's tape read as `tape_ctx` keeps it, the same for every name. Pure."""
    now_ts = now.timestamp()
    out: list[dict[str, Any]] = []
    good = [r for r in rows if r.get("ok")]
    for rank, r in enumerate(good, start=1):
        sym = str(r.get("sym"))
        score = (r.get("score") or {}).get("total")
        parts = score_parts(r.get("score"))
        ctx = {"rank": rank, "of": len(good), "rs": (r.get("rs") or {}).get("SPY"),
               "rs_1h": (r.get("rs_1h") or {}).get("SPY"),
               "rvol": r.get("rvol"), "atr_b": r.get("atr_b"),
               "state": (r.get("setup") or {}).get("state"),
               # The name's own day shape, for the session-type question (daytype.py,
               # 2026-11-10): yesterday's range in its daily ATRs and where it closed,
               # the pre-market range and the gap in the same unit. Logged, not scored.
               **shape_ctx(r),
               # PHASE 3 OF THE QUANT AUDIT (2026-11-13): the record has to be able to test
               # the news and the new rank, so the uncapped score, whether the RVOL gate
               # held the name back, and what the catalyst read (news_ctx) go with it.
               "raw": (r.get("score") or {}).get("raw"),
               "gated": bool((r.get("score") or {}).get("gated")),
               "news": news_ctx(r.get("score"), r.get("news_read")),
               # The tape's bias at the signal, logged and unscored (tape_ctx, 2026-11-19).
               "tape": tape}
        # Every chart's signals: the 10m's, then the 3m's and 5m's (scan.Tech.signals_fast).
        out += signal_events(sym, [*(r.get("signals") or []), *(r.get("signals_fast") or [])],
                             score, day, now_ts, parts, ctx)
        if session != "rth" or r.get("last") is None:
            continue
        prog = r.get("progress") or {}
        lv = r.get("levels") or {}
        for key, name in (("pdh", "PDH"), ("pmh", "PMH"), ("pdl", "PDL"), ("pml", "PML")):
            p = prog.get(key)
            if p is None or p < NEAR_PCT:
                continue
            if key in ("pmh", "pml") and not lv.get("pm_done"):
                continue
            side = "long" if key in ("pdh", "pmh") else "short"
            bar_t = int(now_ts) - int(now_ts) % BAR_SEC
            note = (f"Near {side} — {round(p * 100)}% of the way to {name} "
                    f"{fmt_px(lv.get(key))}")
            out.append(_event(sym, NEAR, side, name, bar_t, r["last"], None, score, note, day,
                              now_ts, parts))
    return out


def _moved(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(float(a) - float(b)) > 1e-6


def final_for(ev: dict[str, Any], final_to: Any) -> int | None:
    """Where the bars of the event's own chart are final: `final_to` is one figure (the
    10m chart's, as it always was) or {tf: figure} (2026-11-19). A chart the bars did not
    cover (no one-minute bars held) is None, and nothing on it is checked. Pure."""
    if isinstance(final_to, dict):
        v = final_to.get(tf_of(ev))
        return int(v) if isinstance(v, (int, float)) else None
    if tf_of(ev) != TF_DEFAULT:
        return None
    return int(final_to) if isinstance(final_to, (int, float)) else None


def revalidate(ev: dict[str, Any], found: dict[str, dict[str, Any]], final_to: Any,
               now_ts: float) -> bool:
    """Check one logged (L) / (E) / (V) / breakout against `found` — the events the newest
    bars imply, by dedupe key — once its bar is final in them (`final_to`, one figure for
    the 10m chart or {tf: figure}: `final_for`). In place; returns whether `ev` changed.

    Gone → retracted (kept, flagged). Price or stop moved → corrected, with the
    first figures kept under `revised` and the outcome recomputed from scratch.
    Back again → the retraction lifted. A bar not yet final is left alone.
    """
    fin = final_for(ev, final_to)
    if ev.get("kind") not in KINDS or fin is None or int(ev["t"]) + bar_sec(ev) > fin:
        return False
    cur = found.get(dedupe_key(ev))
    if cur is None:
        if ev.get("retracted"):
            return False
        ev["retracted"] = True
        ev["retracted_ts"] = _iso(now_ts)
        return True
    changed = False
    if ev.pop("retracted", None):
        ev.pop("retracted_ts", None)
        changed = True
    if _moved(ev.get("price"), cur["price"]) or _moved(ev.get("stop"), cur.get("stop")):
        ev.setdefault("revised", {"price": ev.get("price"), "stop": ev.get("stop"),
                                  "note": ev.get("note")})
        ev["price"], ev["stop"], ev["note"] = cur["price"], cur.get("stop"), cur["note"]
        ev["risk_min"] = cur.get("risk_min")
        if ev.get("outcome") is not None:
            ev["outcome"] = blank_outcome()
        changed = True
    # A signal logged before the floor existed takes it while its outcome is still
    # open, so the day it is settled on is settled by the one rule. A settled one is
    # left to `EventLog.refloor`, which keeps what it replaces.
    elif (ev.get("risk_min") is None and cur.get("risk_min") is not None
          and not (ev.get("outcome") or {}).get("final")):
        ev["risk_min"] = cur["risk_min"]
        changed = True
    return changed


def _session_close_ts(day: date) -> int:
    m = close_minute(day)
    return int(datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=ET).timestamp())


def compute_outcome(ev: dict[str, Any], bars5: list[Bar], now_ts: float,
                    asof: float | None = None) -> dict[str, Any]:
    """An (L) or (E)'s result so far, off completed 5-minute bars. Pure.

    The (L) enters at its bar's close, so the bars after it count; the (E)
    triggers inside its bar, so that bar counts too — its low (for a long) can
    already be the stop. Same-bar stop and target is STOPPED (module docstring).

    `asof` is when `bars5` were downloaded: a bar that had not ended
    CLOSE_LAG_SEC before it is only part of a bar and is not read. FINAL ONLY
    ON BARS THAT REACH THE BELL (audit, 2026-10-14): an outcome used to settle
    at 16:00 on whatever copy of the bars was held — one read at 15:58 has no
    15:55 bar, so its close return was the 15:50 bar's, filed for good. Now it
    settles once bars read after the close cover it, or, when the last bars
    never come (a halt), SETTLE_ANYWAY_SEC after the bell on what there is.
    """
    out = blank_outcome()
    entry, stop = float(ev["price"]), ev.get("stop")
    day = date.fromisoformat(ev["day"])
    close_ts = _session_close_ts(day)
    known = now_ts if asof is None else min(now_ts, asof - CLOSE_LAG_SEC)
    # R is the stop's distance, never less than the signal's floor: the stop is
    # counted hit that far from the entry, and +1R that far the other way. A STOP
    # EXACTLY ON THE ENTRY IS THE FLOOR'S OWN CASE, NOT A SIGNAL WITH NO R (audit,
    # 2026-11-11): an (L) whose bar closes on its low has a distance of nothing, and
    # until then it was sent back unmeasured before the floor was looked at (ARM
    # 29 Oct 12:00, PH 5 Nov 13:50, SHOP 9 Nov 14:00). Only a stop on the entry with
    # no floor to read it through has nothing to be measured in.
    dist = abs(entry - float(stop)) if stop is not None else 0.0
    r = risk_of(entry, float(stop), ev.get("risk_min")) if stop is not None else 0.0
    if r <= 0:
        out["final"] = known >= close_ts
        return out
    out["r"] = round(r, 4)
    out["floored"] = r > dist + 1e-9
    s = 1.0 if ev["side"] == "long" else -1.0
    tol = abs(entry) * TOUCH_REL
    t0 = int(ev["t"])
    span = bar_sec(ev)
    start = t0 if ev["kind"] == "E" else t0 + span
    ref = t0 + span  # the 30/60-minute marks run from the signal bar's close

    mfe = mae = 0.0
    seen = False
    hit1: bool | None = None
    hit2: bool | None = None
    stopped: bool | None = None
    ret30 = ret60 = None
    last_close: float | None = None
    last_end = 0
    for b in bars5:
        # A 3m signal's entry can fall inside a 5-minute bar (10:48 in 10:45-10:50). That
        # bar is read whole, minutes before the entry included: a stop it shows counts,
        # the conservative reading, as for a bar that reaches both (module docstring).
        if b.t + SRC_SEC <= start:
            continue
        end = b.t + SRC_SEC
        if b.t >= close_ts or end > known:
            break
        seen = True
        fav = (b.high - entry) if s > 0 else (entry - b.low)
        adv = (entry - b.low) if s > 0 else (b.high - entry)
        mfe, mae = max(mfe, fav), max(mae, adv)
        # A TOUCH TO THE CENT COUNTS, BY THE RULE AND NOT BY THE FEED'S ROUNDING (`TOUCH_REL`).
        stop_hit = adv >= r - tol
        if hit1 is None and stopped is None:
            if stop_hit:  # including the bar that also made +1R
                stopped, hit1, hit2 = True, False, False
            elif fav >= r - tol:
                hit1, stopped = True, False
                if fav >= 2 * r - tol:
                    hit2 = True
        elif hit1 and hit2 is None:
            if stop_hit:
                hit2 = False
            elif fav >= 2 * r - tol:
                hit2 = True
        if ret30 is None and end >= ref + 1800:
            ret30 = s * (b.close - entry) / r
        if ret60 is None and end >= ref + 3600:
            ret60 = s * (b.close - entry) / r
        last_close, last_end = b.close, end

    if seen:
        out["mfe_r"] = round(mfe / r, 3)
        out["mae_r"] = round(mae / r, 3)
    out["hit_1r"], out["hit_2r"], out["stopped"] = hit1, hit2, stopped
    out["ret_30m_r"] = round(ret30, 3) if ret30 is not None else None
    out["ret_60m_r"] = round(ret60, 3) if ret60 is not None else None
    # A bar ending at the bell was read whole — or there was nothing after the
    # signal to read (an (L) on the day's last bar).
    covered = last_end >= close_ts or start >= close_ts
    if known >= close_ts and covered and last_close is not None:
        out["ret_close_r"] = round(s * (last_close - entry) / r, 3)
    if known >= close_ts and (covered or now_ts >= close_ts + SETTLE_ANYWAY_SEC):
        out["final"] = True
        # Settled with neither: it did not reach +1R and was never stopped.
        for k in ("hit_1r", "hit_2r", "stopped"):
            if out[k] is None:
                out[k] = False
    return out


def floor_at(bars5: list[Bar], bar_t: int) -> float | None:
    """The stop's floor for a signal on the ten-minute bar that opens at `bar_t`:
    the retest buffer there, BUF_MULT x the ATR, worked from the bars up to it as the
    scanner works it. None when the bars do not hold that bar, or too few come before
    it for the ATR to have settled. Pure."""
    upto = [b for b in bars5 if b.t < bar_t + BAR_SEC]
    bars10 = resample(upto)
    if len(bars10) < max(REFLOOR_MIN_BARS, ATR_LEN + 1) or bars10[-1].t != bar_t:
        return None
    a = atr(bars10, sessions=rth_bar_days(upto))[-1]
    return a * BUF_MULT if a else None


def preopen_line(rows: Iterable[dict[str, Any]], day: str, now: datetime) -> dict[str, Any]:
    """The list as it stands before the bell, best first, for one line of the log. Pure."""
    good = [r for r in rows if r.get("ok")]
    return {
        "day": day, "at_et": now.astimezone(ET).strftime("%H:%M"),
        "rows": [{"sym": r.get("sym"), "rank": i, "score": (r.get("score") or {}).get("total"),
                  "side": (r.get("score") or {}).get("side"),
                  "state": (r.get("setup") or {}).get("state"),
                  "parts": score_parts(r.get("score"))}
                 for i, r in enumerate(good, start=1)],
    }


def stats(events: Iterable[dict[str, Any]], days: int, today: date) -> dict[str, Any]:
    """Settled (L)/(E) outcomes over the last `days`, grouped. Pure."""
    start = today - timedelta(days=days)
    # The 10m chart's, so the record runs on from before the faster charts (SAME_SETUP_SEC).
    rows = [
        e for e in events
        if e.get("kind") in TRADES and not e.get("retracted") and tf_of(e) == TF_DEFAULT
        and (e.get("outcome") or {}).get("final")
        and (e.get("outcome") or {}).get("r") is not None
        and start < date.fromisoformat(e["day"]) <= today
    ]

    def avg(xs: list[float | None]) -> float | None:
        v = [x for x in xs if x is not None]
        return round(sum(v) / len(v), 3) if v else None

    def med(xs: list[float | None]) -> float | None:
        v = [x for x in xs if x is not None]
        return round(statistics.median(v), 3) if v else None

    def group(key: str, evs: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(evs)
        outs = [e["outcome"] for e in evs]
        return {
            "key": key,
            "n": n,
            "win_1r": round(sum(1 for o in outs if o.get("hit_1r")) / n, 3) if n else None,
            "held_r": avg([held_r(o) for o in outs]),
            # Medians: one stop a hair wide reads as +440 R of best, and carried the
            # average to +10 R on a group whose typical signal saw +4.5 R (2026-11-05).
            "med_mfe_r": med([o.get("mfe_r") for o in outs]),
            "med_mae_r": med([o.get("mae_r") for o in outs]),
        }

    def scored(lo: float, hi: float) -> list[dict[str, Any]]:
        return [e for e in rows if e.get("score") is not None and lo <= e["score"] < hi]

    groups = [group("all", rows)]
    for kind in TRADES:
        for side in ("long", "short"):
            groups.append(group(f"{kind} {side}",
                                [e for e in rows if e["kind"] == kind and e["side"] == side]))
    groups += [group("score ≥ 60", scored(60, 1e9)), group("score 40–59", scored(40, 60)),
               group("score < 40", scored(-1e9, 40))]
    # How much of the record is on the floored stop (module docstring): `ruled` were
    # read with a floor to hand, `floored` are the ones it moved the stop on, and the
    # rest are older signals whose bars were gone before they could be worked again.
    ruled = sum(1 for e in rows if e.get("risk_min") is not None)
    floored = sum(1 for e in rows if (e.get("outcome") or {}).get("floored"))
    return {"days": days, "from": (start + timedelta(days=1)).isoformat(),
            "to": today.isoformat(), "total": len(rows), "groups": groups,
            "floor": {"ruled": ruled, "floored": floored, "unruled": len(rows) - ruled}}


def record_table(events: Iterable[dict[str, Any]], days: int,
                 today: date) -> dict[str, dict[str, Any]]:
    """Settled (L)/(E) outcomes over the last `days`, keyed "band|kind|side" —
    the record line under every row's score (scanscore.record_for). Pure.

    The band is the score the signal was LOGGED with, so a row's own band is
    compared with signals that looked the same when they fired. Backfilled
    signals carry no score and are left out.
    """
    start = today - timedelta(days=days)
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        # The 10m chart's, as `stats`.
        if e.get("kind") not in TRADES or e.get("retracted") or tf_of(e) != TF_DEFAULT:
            continue
        o = e.get("outcome") or {}
        if not o.get("final") or o.get("r") is None or o.get("hit_1r") is None:
            continue
        sc = e.get("score")
        if not isinstance(sc, (int, float)):
            continue
        try:
            d = date.fromisoformat(str(e.get("day")))
        except ValueError:
            continue
        if not start < d <= today:
            continue
        band = "60+" if sc >= 60 else "40-59" if sc >= 40 else "<40"
        groups.setdefault(f"{band}|{e['kind']}|{e['side']}", []).append(e)
    out: dict[str, dict[str, Any]] = {}
    for key, evs in groups.items():
        held = [h for x in evs if (h := held_r(x["outcome"])) is not None]
        out[key] = {
            "n": len(evs),
            "win_1r": round(sum(1 for x in evs if x["outcome"].get("hit_1r")) / len(evs), 3),
            "held_r": round(sum(held) / len(held), 2) if held else None,
            "sessions": len({x["day"] for x in evs}),
        }
    return out


class EventLog:
    """The persisted log: `observe` on the scanner thread, `since`/`stats` from the API."""

    def __init__(self, path: str = EVENTS_FILE) -> None:
        self._lock = threading.Lock()
        self._path = path
        self.events: list[dict[str, Any]] = []
        self._keys: set[str] = set()
        self._next = 1
        self._preopen_path = os.path.join(os.path.dirname(path), PREOPEN_NAME)
        self._preopen_days = self._read_preopen_days()
        self._load()

    def _read_preopen_days(self) -> set[str]:
        """The days already on file, so a restart at 09:27 does not write the day twice."""
        days: set[str] = set()
        with contextlib.suppress(OSError, ValueError), open(
                self._preopen_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    days.add(str(json.loads(line).get("day")))
        return days

    def _note_preopen(self, payload: dict[str, Any], rows: list[dict[str, Any]], day: str,
                      now: datetime) -> None:
        """One line a day: the rank at the last look before the open. Best effort: a
        full disk must not cost the signals."""
        et = now.astimezone(ET)
        if payload.get("session") != "pre" or et.time() < PREOPEN_AT or day in self._preopen_days:
            return
        self._preopen_days.add(day)
        with contextlib.suppress(OSError), open(self._preopen_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(preopen_line(rows, day, now), separators=(",", ":")) + "\n")

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                        # Logged before backfills stopped carrying a score: the
                        # one they have is from hours later (module docstring).
                        if ev.get("live") is False:
                            ev["score"] = None
                        self.events.append(ev)
        except OSError:
            return
        self.events.sort(key=lambda e: e["id"])
        self._keys = {dedupe_key(e) for e in self.events}
        self._next = max((e["id"] for e in self.events), default=0) + 1

    def _save(self, today: date) -> None:
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self.events = [e for e in self.events if e.get("day", "") >= cutoff]
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                for e in self.events:
                    f.write(json.dumps(e, separators=(",", ":")) + "\n")
            os.replace(tmp, self._path)
        except OSError:
            pass  # a log that cannot be written is a shorter log, not a broken scanner

    def observe(self, payload: dict[str, Any], bars: dict[str, list[Bar]],
                now: datetime | None = None,
                fetched: dict[str, float] | None = None) -> list[dict[str, Any]]:
        """Log what is new in this payload, check today's logged signals against
        the newest final bars, and update open outcomes. Returns the new.

        `fetched` is when each name's `bars` were downloaded — an outcome reads
        only the bars that had ended by then (compute_outcome)."""
        now = now or datetime.now(UTC)
        day = str(payload.get("trading_day") or "")
        if not day:
            return []
        rows = [r for r in payload.get("rows") or [] if isinstance(r, dict)]
        now_ts = now.timestamp()
        new: list[dict[str, Any]] = []
        changed = False
        with self._lock:
            self._note_preopen(payload, rows, day, now)
            tape = tape_ctx(payload.get("regime"))
            today = [e for e in self.events if e.get("day") == day]
            # In the order their bars closed, so the chart that printed a setup first is
            # the one that alerts when two arrive in one pass.
            cands = sorted(candidates(rows, str(payload.get("session")), day, now, tape),
                           key=lambda c: int(c["t"]) + bar_sec(c))
            for c in cands:
                k = dedupe_key(c)
                if k in self._keys:
                    continue
                # ONE SETUP, ONE ALERT (SAME_SETUP_SEC): printed on another chart first,
                # this one is logged and kept quiet.
                prior = same_setup(c, today)
                if prior:
                    c["alert"] = False
                    c["after"] = sorted({tf_of(e) for e in prior}, key=lambda x: TF_SEC[x])
                c["id"] = self._next
                self._next += 1
                self._keys.add(k)
                self.events.append(c)
                today.append(c)
                new.append(c)
                changed = True
            # The second look at what was logged today (module docstring), each chart's
            # signals against that chart's own final bars.
            found: dict[str, tuple[dict[str, dict[str, Any]], dict[str, Any]]] = {}
            for r in rows:
                if r.get("ok"):
                    sigs = [*(r.get("signals") or []), *(r.get("signals_fast") or [])]
                    evs = signal_events(str(r.get("sym")), sigs, None, day, now_ts)
                    found[str(r.get("sym"))] = ({dedupe_key(e): e for e in evs},
                                                {TF_DEFAULT: r.get("final_to"),
                                                 **(r.get("final_to_tf") or {})})
            for e in self.events:
                if e.get("day") == day and e.get("sym") in found:
                    got, final_to = found[e["sym"]]
                    changed |= revalidate(e, got, final_to, now_ts)
            changed |= self._outcomes(bars, now_ts, fetched or {})
            if changed:
                self._save(now.astimezone(ET).date())
        return new

    def _outcomes(self, bars: dict[str, list[Bar]], now_ts: float,
                  fetched: dict[str, float]) -> bool:
        """Every open outcome brought up to date. Under the lock."""
        changed = False
        for e in self.events:
            o = e.get("outcome")
            if o is None or o.get("final") or e.get("retracted"):
                continue
            b = bars.get(e["sym"])
            if not b:
                continue
            o2 = compute_outcome(e, b, now_ts, fetched.get(e["sym"]))
            if o2 != o:
                e["outcome"] = o2
                changed = True
        return changed

    def unchecked(self, before: str) -> dict[str, set[str]]:
        """{day: names} with a logged (L), (E) or breakout from a finished day
        (before `before`, the trading day) not yet settled against final bars."""
        out: dict[str, set[str]] = {}
        with self._lock:
            for e in self.events:
                if e.get("kind") in KINDS and not e.get("checked") and e.get("day", "") < before:
                    out.setdefault(e["day"], set()).add(e["sym"])
        return out

    def settle(self, day: str, by_sym: dict[str, tuple[list[dict[str, Any]], Any]],
               now: datetime | None = None, known_only: Iterable[str] = ()) -> int:
        """Settle a FINISHED day against its signals replayed from bars read after
        its close — {name: (signals, final_to)}, `final_to` one figure for the 10m chart
        or {tf: figure} (`final_for`). Each logged event is checked
        (`revalidate`) and marked `checked` once the bars reach the bell; a
        signal those bars hold that was never logged is logged now, not live, when its
        own chart's bars reach the bell. Returns how many events changed or were added.

        `known_only` names the names that were NOT being watched to the bell: one
        that left the list during the day and was read again afterwards for this
        (sources/scanner.ScanStore.read_owed), or one read for a chart. What was
        logged for it is checked like anything else; a signal the bars hold that
        was never logged is NOT added. A name's earlier signals are on its row
        the minute it joins the list, so those are logged then; what it did after
        it left was on nobody's screen, and the log is of what the engine showed."""
        now = now or datetime.now(UTC)
        now_ts = now.timestamp()
        close = _session_close_ts(date.fromisoformat(day))
        quiet = set(known_only)
        n = 0
        with self._lock:
            for sym, (signals, final_to) in by_sym.items():
                evs = signal_events(sym, signals, None, day, now_ts)
                got = {dedupe_key(e): e for e in evs}
                fin10 = final_for({}, final_to)
                whole = fin10 is not None and fin10 >= close
                for e in self.events:
                    if e.get("day") != day or e.get("sym") != sym or e.get("kind") not in KINDS:
                        continue
                    hit = revalidate(e, got, final_to, now_ts)
                    if whole and not e.get("checked"):
                        e["checked"] = True
                        hit = True
                    n += hit
                if not whole or sym in quiet:
                    continue
                for k, c in got.items():
                    if k in self._keys:
                        continue
                    fc = final_for(c, final_to)
                    if fc is None or fc < close:
                        continue  # that chart's bars do not reach the bell
                    c["id"] = self._next
                    c["checked"] = True
                    self._next += 1
                    self._keys.add(k)
                    self.events.append(c)
                    n += 1
            if n:
                self._save(now.astimezone(ET).date())
        return n

    def refloor(self, bars_of: Callable[[str], list[Bar] | None],
                now: datetime | None = None) -> dict[str, int]:
        """Work the signals settled before the stop had a floor again, where the bars
        still allow it (module docstring). Returns {seen, ruled, floored, skipped}.

        NOTHING IS LOST, AND IT CAN BE RUN AGAIN. For each settled (L)/(E) with no
        `risk_min`: the floor is taken from the bars held for the name (`floor_at`),
        and where it would have moved the stop the outcome is read again from those
        bars, the first one kept under `outcome_raw`. A signal is left exactly as it
        was when its bars are gone, do not reach back far enough for an ATR, or stop
        short of that day's bell: a result read from part of a day is worse than the
        one on file. Before the first change is written the file as it stood is
        copied beside itself (`.before-floor`), once.

        Two more kinds of settled signal are read again here, by the same rule and
        with the same first outcome kept (audit, 2026-11-11): one whose stop sat
        exactly on its entry and so came back with no R, and one settled with an R
        and no bar read after it (`unread`).
        """
        now = now or datetime.now(UTC)
        now_ts = now.timestamp()
        counts = {"seen": 0, "ruled": 0, "floored": 0, "skipped": 0}

        def unread(e: dict[str, Any]) -> bool:
            """Settled with an R and no bar read after it, on a day that went on: its
            bars were not to hand an hour after the bell and it was settled anyway
            (SETTLE_ANYWAY_SEC), as "neither". GEV's (L) at 10:00 on 28 Oct 2026 stood
            that way; the bars say it was stopped. An (L) on the day's last bar has
            nothing after it and is not one of these."""
            o = e.get("outcome") or {}
            if o.get("r") is None or o.get("mfe_r") is not None:
                return False
            t0 = int(e["t"])
            start = t0 if e.get("kind") == "E" else t0 + BAR_SEC
            return start < _session_close_ts(date.fromisoformat(e["day"]))

        def due(e: dict[str, Any]) -> bool:
            o = e.get("outcome") or {}
            # The floor is worked on ten-minute bars (`floor_at`): the 10m chart's only.
            if (e.get("kind") not in TRADES or e.get("retracted") or e.get("stop") is None
                    or not o.get("final") or tf_of(e) != TF_DEFAULT):
                return False
            # No floor yet; or a floor and still no R (a stop exactly on its entry,
            # settled while that was sent back unmeasured, compute_outcome); or an R
            # and nothing read after it.
            return e.get("risk_min") is None or o.get("r") is None or unread(e)

        with self._lock:
            syms = sorted({str(e.get("sym")) for e in self.events if due(e)})
        # The bars are read outside the lock: for a name off today's list that is a
        # file to parse, and the page's reads of the log should not wait on it.
        held = {s: bars_of(s) for s in syms}
        with self._lock:
            for e in self.events:
                if not due(e):
                    continue
                counts["seen"] += 1
                bars = held.get(str(e.get("sym")))
                floor = floor_at(bars, int(e["t"])) if bars else None
                close_ts = _session_close_ts(date.fromisoformat(e["day"]))
                if not bars or floor is None or bars[-1].t + SRC_SEC < close_ts:
                    counts["skipped"] += 1
                    continue
                rm = round(floor, 4)
                price, stop = float(e["price"]), float(e["stop"])
                if rm <= 0:
                    counts["skipped"] += 1
                    continue
                real = risk_of(price, stop, rm) <= abs(price - stop) + 1e-9
                blind = unread(e)
                again = (compute_outcome({**e, "risk_min": rm}, bars, now_ts)
                         if blind or not real else None)
                if again is not None and blind and real and again.get("mfe_r") is None:
                    again = None  # these bars hold nothing after it either
                if again is None:
                    # The stop was already a real distance: nothing to read again.
                    if e.get("risk_min") is None:
                        e["risk_min"] = rm
                        e["outcome"] = {**e["outcome"], "floored": False}
                        counts["ruled"] += 1
                    else:
                        counts["skipped"] += 1
                    continue
                if not again.get("final") or again == e["outcome"]:
                    counts["skipped"] += 1
                    continue
                e["risk_min"] = rm
                # The FIRST outcome is the one kept: a signal worked a second time
                # (the stop on its entry) does not write the first one over.
                e.setdefault("outcome_raw", e["outcome"])
                e["outcome"] = again
                counts["ruled"] += 1
                counts["floored"] += bool(again.get("floored"))
            if counts["ruled"]:
                self._backup_once()
                self._save(now.astimezone(ET).date())
        return counts

    def _backup_once(self) -> None:
        """The log as it stood before the first refloor, beside it. Best effort."""
        root, ext = os.path.splitext(self._path)
        keep = f"{root}.before-floor{ext}"
        if os.path.exists(keep) or not os.path.exists(self._path):
            return
        with contextlib.suppress(OSError):
            shutil.copy2(self._path, keep)

    def holding(self, day: str, now_ts: float, *, trade_sec: float,
                break_sec: float) -> set[str]:
        """The names the live rotation (rotation.py) keeps on the list for their signals, on
        any chart: a live (L) / (E) / (V) on `day` whose bar closed in the last `trade_sec` and
        whose stop has not been hit (a trade the owner may be in), or a live breakout in the
        last `break_sec` (its retest, the trade, is still to come). Withdrawn ones count for
        nothing. Live only: a signal replayed when a name joined the list never holds it."""
        out: set[str] = set()
        with self._lock:
            for e in self.events:
                if (e.get("day") != day or not e.get("live") or e.get("retracted")
                        or e.get("kind") not in KINDS):
                    continue
                age = now_ts - (int(e["t"]) + bar_sec(e))
                if e.get("kind") in TRADES:
                    if age <= trade_sec and not (e.get("outcome") or {}).get("stopped"):
                        out.add(str(e.get("sym")))
                elif age <= break_sec:
                    out.add(str(e.get("sym")))
        return out

    def since(self, since: int, limit: int = 200) -> dict[str, Any]:
        """Events with id > since, and `retracted`: the ids of the last
        RETRACT_DAYS days' withdrawn events, so a page that announced one can
        say it was withdrawn."""
        with self._lock:
            latest = self._next - 1
            evs = [dict(e) for e in self.events if e["id"] > since][:limit]
            days = sorted({str(e.get("day", "")) for e in self.events})[-RETRACT_DAYS:]
            gone = [e["id"] for e in self.events if e.get("retracted") and e.get("day") in days]
        return {"latest": latest, "events": evs, "retracted": gone}

    def stats(self, days: int = 20, today: date | None = None) -> dict[str, Any]:
        with self._lock:
            evs = list(self.events)
        return stats(evs, days, today or datetime.now(ET).date())

    def record_table(self, days: int = 30, today: date | None = None) -> dict[str, dict[str, Any]]:
        with self._lock:
            evs = list(self.events)
        return record_table(evs, days, today or datetime.now(ET).date())
