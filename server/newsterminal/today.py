"""
TODAY: THE STOCKS TAB'S ONE LIST, RANKED FOR THE HOUR IT IS.

The owner, 2026-11-13: "we really need to overhaul the whole stocks scanner section so
that it calculates and scores as best as possible depending on the time ... instead we
have set ups that just change and display the best options for a given period and
updates and scores live based on changes and what happens and any news that comes in";
then "make premarket 4:00-9:30 and the open 9:30-10:00 and then the rest of the
session". Setups, Breakouts, Extended hours and Day 2/3 were four answers to one
question, each ranked its own way; this is one answer that changes with the clock.

Five phases (ET; a half day closes at 13:00 and its late session ends at 17:00):

  after      the close → 20:00   moving after the close, and the day's big movers
  overnight  20:00 → 04:00, and every day the market is shut: the evening's movers and
             the reports due before the next open, the prep for the next session
  pre        04:00 → 09:30       in play going into the open
  open       09:30 → 10:00       the pre-market's names, ordered by what they have done
  session    10:00 → the close   the best trades now: the engine's setup score

WHAT EACH RANKS BY, AND WHY (the quant audit of 2026-11-13). Before the bell the size of
a move can be read and its direction cannot: a gap of 3+ daily ATRs meant 2.7x a normal
day's range over a year, and the gap's direction told nothing. So the evening, the
overnight and the pre-market lists rank how in play a name is, read the way the pool
reads it (sources/pool: the move in daily ATRs, volume against normal, a report, a fresh
major story, a level already through, a Day 2 or 3), and show the levels both ways with
the gap's side as a lean, never a call. The open's first half hour reached +1R on 39% of
signals against 52% from 10:00, and RVOL is thin until about 09:45, so the open keeps
the pre-market's in-play score and orders the names by what the bell has done to them:
an entry live, through a level, not triggered, failed. From 10:00 the engine's score
ranks, unchanged, so the two-week test of its weights runs on.

Everything here is pure: the collector hands in the reads (collector.today).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from . import scan
from .holidays import is_trading_day, next_trading_day
from .sources import pool
from .sources.scanner import BENCHMARKS

ET = scan.ET

PHASES = ("after", "overnight", "pre", "open", "session")
LABELS = {"after": "After hours", "overnight": "Overnight", "pre": "Pre-market",
          "open": "The open", "session": "Session"}
TITLES = {
    "after": "Moving after the close, and today's big movers: the prep for the next session",
    "overnight": "The prep for the next session: the evening's movers and the reports "
                 "due before the open",
    "pre": "In play going into the open",
    "open": "The open: the pre-market's names, by what the bell has done to them",
    "session": "The best trades now",
}
PRE_START = 4 * 60
OPEN_START = 9 * 60 + 30
SESSION_START = 10 * 60
#: Rows shipped before the bell and in the evening (the session ships every tracked row).
TOP_N = 30
#: A name that came into the top ten this recently is marked new (collector.today).
NEW_MIN = 15.0
#: A stream trade this fresh stands in for the screener's fifteen-minute-old price.
LIVE_SEC = 15 * 60
#: The evening's gates: a price and a dollar day the desk would trade (the pool's), or a
#: move after the close of UNUSUAL_PCT on AH_TURNOVER, which is a report being traded.
AH_TURNOVER = 25_000_000.0
#: A Day 1 by the Day 2/3 tracker's default (momentum.DEFAULT_MOVE, 1.5x volume).
DAY1_MOVE = 20.0
DAY1_RVOL = 1.5
#: The evening's bar. The pool's (MIN_SCORE, 4) is for the pre-market, where a third of
#: an ATR and a little volume already say something; over a whole day a quarter-ATR
#: drift on normal volume scores 4.2 and is not a mover. 8 is a 0.75-ATR day on its own,
#: or half an ATR on 1.5x volume, or a report or a story with a smaller move.
EVENING_MIN = 8.0


@dataclass(frozen=True)
class Phase:
    key: str
    #: The session the list is for: today, or the next one in the evening and overnight.
    day: date
    #: When the next phase begins, and which it is.
    ends: datetime
    next_key: str

    def as_dict(self, now: datetime) -> dict[str, Any]:
        return {"key": self.key, "label": LABELS[self.key], "title": TITLES[self.key],
                "day": self.day.isoformat(), "ends_utc": self.ends.isoformat(),
                "ends_in_min": round((self.ends - now).total_seconds() / 60.0, 1),
                "next": self.next_key, "next_label": LABELS[self.next_key]}


def _at(d: date, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=ET)


def phase_at(now: datetime) -> Phase:
    """The phase at `now`. Pure.

    Worked examples (tests/test_today.py has the table): Friday 13 Nov 2026 03:59 is
    overnight for the 13th, 04:00 pre, 09:30 open, 10:00 session, 16:00 after hours for
    Monday the 16th, 20:00 overnight for Monday, and the whole weekend overnight for
    Monday; Friday 27 Nov (a half day) is after hours from 13:00 to 17:00; Thanksgiving
    is overnight for the 27th.
    """
    et = now.astimezone(ET)
    d = et.date()
    m = et.hour * 60 + et.minute
    if is_trading_day(d):
        close, late = scan.rth_end(d), scan.post_end(d)
        if m < PRE_START:
            return Phase("overnight", d, _at(d, PRE_START), "pre")
        if m < OPEN_START:
            return Phase("pre", d, _at(d, OPEN_START), "open")
        if m < SESSION_START:
            return Phase("open", d, _at(d, SESSION_START), "session")
        if m < close:
            return Phase("session", d, _at(d, close), "after")
        nxt = next_trading_day(d)
        if m < late:
            return Phase("after", nxt, _at(d, late), "overnight")
        return Phase("overnight", nxt, _at(nxt, PRE_START), "pre")
    nxt = next_trading_day(d)
    return Phase("overnight", nxt, _at(nxt, PRE_START), "pre")


# ---------------------------------------------------------------- the row pieces


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def plan_of(last: float | None, pdh: float | None, pdl: float | None,
            pmh: float | None, pml: float | None) -> dict[str, Any]:
    """The two triggers before a session has decided a side: for a long the break of the
    nearest of PMH and PDH above price, or the retest of the highest already under it;
    for a short the same with PML and PDL. The engine's own pre-market plan reads the
    levels the same way (scan.setup_of, "forming"). Pure."""
    out: dict[str, Any] = {"long": None, "short": None}
    if last is None:
        return out
    up = [(k, p) for k, p in (("PMH", pmh), ("PDH", pdh)) if p is not None]
    dn = [(k, p) for k, p in (("PML", pml), ("PDL", pdl)) if p is not None]
    under = [x for x in up if x[1] < last]
    over = [x for x in up if x[1] >= last]
    if under:
        k, p = max(under, key=lambda x: x[1])
        out["long"] = {"level": k, "price": round(p, 4), "held": True}
    elif over:
        k, p = min(over, key=lambda x: x[1])
        out["long"] = {"level": k, "price": round(p, 4), "held": False}
    above = [x for x in dn if x[1] > last]
    below = [x for x in dn if x[1] <= last]
    if above:
        k, p = min(above, key=lambda x: x[1])
        out["short"] = {"level": k, "price": round(p, 4), "held": True}
    elif below:
        k, p = max(below, key=lambda x: x[1])
        out["short"] = {"level": k, "price": round(p, 4), "held": False}
    return out


def _arrow(x: float | None) -> str:
    return "▲" if (x or 0.0) > 0 else "▼"


def _why_inplay(e: dict[str, Any], move: float | None, what: str) -> list[str]:
    """The in-play read in words, one piece each (pool.in_play's parts)."""
    out: list[str] = []
    g = e.get("gap_atr")
    if isinstance(g, (int, float)) and g >= pool.GAP_MIN:
        out.append(f"{what} {_arrow(move)} {g:.2f} ATR")
    if what == "gap":
        v = e.get("vol_pct")
        if isinstance(v, (int, float)):
            out.append(f"pre-market {v:.1f}% of an average day")
    elif isinstance(e.get("rvol"), (int, float)):
        out.append(f"RVOL {e['rvol']:.2f}×")
    if e.get("reports"):
        out.append(str(e["reports"]))
    through = e.get("through")
    if through:
        word = "above" if through == "PDH" else "below"
        # Before the bell the pre-market range cannot be through itself, so a name past
        # the previous day's level is just that (lib/outsideDay.ts says the same).
        if what != "gap" and e.get("outside"):
            pm = "high" if through == "PDH" else "low"
            out.append(f"outside day: {word} {through} and the pre-market {pm}")
        else:
            out.append(f"{word} {through}")
    if e.get("day"):
        out.append(f"day {e['day']} of a big move")
    return out


def _base(sym: str, *, name: Any = None, sector: Any = None, cap: Any = None,
          favs: frozenset[str], tracked: frozenset[str]) -> dict[str, Any]:
    return {"sym": sym, "name": name, "sector": sector, "cap": cap,
            "fav": sym in favs, "tracked": sym in tracked, "new": False}


# --------------------------------------------------------------------- pre-market


def live_premarket(rows: Iterable[dict[str, Any]],
                   quote: Callable[[str], dict[str, Any] | None], now_ts: float
                   ) -> list[dict[str, Any]]:
    """The pool's rows with each name's pre-market last taken from the stream where it
    has a pre-market trade under LIVE_SEC old: the screener runs fifteen minutes behind,
    and a gap is read off that price. Volume stays the screener's. Pure."""
    out = []
    for r in rows:
        q = quote(str(r.get("symbol") or ""))
        if (q and isinstance(q.get("price"), (int, float)) and q.get("session") == "pre"
                and now_ts - float(q.get("at") or 0.0) <= LIVE_SEC):
            r = {**r, "pm_close": float(q["price"]), "live": True}
        out.append(r)
    return out


def rank_pre(ranked: list[dict[str, Any]], rows: dict[str, dict[str, Any]], *,
             levels: Callable[[str], dict[str, Any] | None],
             catalyst: Callable[[str], dict[str, Any] | None],
             favs: frozenset[str], tracked: frozenset[str],
             limit: int = TOP_N) -> list[dict[str, Any]]:
    """The pre-market list: the pool's in-play rank (`ranked`, pool.rank on rows with
    live prices) over its bar, best first, each with its two triggers. `rows` are the
    same rows by symbol, for the price. Pure."""
    out: list[dict[str, Any]] = []
    for e in ranked:
        sym = e["symbol"]
        if sym in BENCHMARKS or e["score"] < pool.MIN_SCORE:
            continue
        r = rows.get(sym) or {}
        last, ref = _num(r.get("pm_close")), _num(r.get("close"))
        move = (last / ref - 1.0) * 100.0 if last is not None and ref else None
        lv = levels(sym) or {}
        out.append({
            **_base(sym, name=e.get("name"), sector=e.get("sector"), cap=e.get("cap"),
                    favs=favs, tracked=tracked),
            "last": last, "live": bool(r.get("live")), "chg": move, "move": "pre",
            "score": e["score"], "score_max": pool.SCORE_MAX, "score_kind": "in play",
            "why": _why_inplay(e, move, "gap"), "story": catalyst(sym),
            "lean": ("long" if (move or 0) > 0 else "short")
            if (e.get("gap_atr") or 0) >= pool.GAP_MIN else None,
            "plan": plan_of(last, lv.get("pdh"), lv.get("pdl"), lv.get("pmh"), lv.get("pml")),
            "setup": None, "levels": lv, "gap_atr": e.get("gap_atr"),
            "vol_pct": e.get("vol_pct"), "rvol": None, "stage": e.get("day"),
        })
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------- the open

#: The open's order: an entry live (a retest, a pullback, near VWAP / the 8 EMA), through
#: a level with no entry yet, not triggered, then failed or chopping.
GROUP_WORDS = ("entry live", "through a level", "not triggered", "failed")


def open_group(setup: dict[str, Any] | None, wide: dict[str, Any] | None,
               lean: str | None) -> int:
    """Where a name stands since the bell (GROUP_WORDS), from the engine's setup when
    the name is tracked, else the wide read's place against its levels. Pure."""
    if setup:
        state = setup.get("state")
        entry = setup.get("entry") or {}
        if setup.get("lost_vwap") and state not in ("forming", None):
            return 3
        if state in ("retest", "pullback"):
            return 0
        if state == "extended":
            return 0 if abs(entry.get("dist_atr") or 99) <= 1.0 else 1
        if state in ("failed", "chop"):
            return 3
        return 2
    if wide:
        up = wide.get("pd_state") == "above" or wide.get("pm_state") == "above"
        down = wide.get("pd_state") == "below" or wide.get("pm_state") == "below"
        if (lean == "long" and up) or (lean == "short" and down) or (lean is None and (up or down)):
            return 1
    return 2


def rank_open(pre: list[dict[str, Any]], *, engine: dict[str, dict[str, Any]],
              wide: Callable[[str], dict[str, Any] | None],
              price: Callable[[str], tuple[float | None, bool]]) -> list[dict[str, Any]]:
    """The open: the pre-market list as it stood at the bell (`pre`, rank_pre's rows with
    their in-play score kept), re-ordered by GROUP_WORDS and then that score, each with
    the engine's setup where the name is tracked. `price(sym)` is the live last and
    whether it is live. Pure."""
    out: list[dict[str, Any]] = []
    for row in pre:
        sym = row["sym"]
        eng = engine.get(sym) or {}
        setup = eng.get("setup") if eng.get("ok") else None
        w = wide(sym)
        g = open_group(setup, w, row.get("lean"))
        last, live = price(sym)
        ref = _num((eng.get("levels") or {}).get("pdc")) or _num((w or {}).get("pdc"))
        chg = (last / ref - 1.0) * 100.0 if last is not None and ref else row.get("chg")
        out.append({**row, "last": last if last is not None else row.get("last"), "live": live,
                    "chg": chg, "move": "day", "group": g, "status": GROUP_WORDS[g],
                    "setup": _setup_out(setup),
                    "lean": (setup or {}).get("side") or row.get("lean")})
    out.sort(key=lambda r: (r["group"], -(r["score"] or 0.0)))
    return out


def _setup_out(setup: dict[str, Any] | None) -> dict[str, Any] | None:
    if not setup:
        return None
    return {k: setup.get(k) for k in ("state", "side", "level", "note", "entry", "lost_vwap")}


# ------------------------------------------------------------------------ session


def _why_score(score: dict[str, Any], limit: int = 4) -> list[str]:
    """A setup score's best parts, in its own words (scanscore.score_row's notes)."""
    parts = [p for p in score.get("parts") or []
             if (p.get("pts") or 0) > 0 and p.get("key") != "catalyst"]
    parts.sort(key=lambda p: -(p.get("pts") or 0))
    out = []
    for p in parts[:limit]:
        note = str(p.get("note") or "").split(" · capped")[0]
        out.append(f"{p.get('label')}: {note}" if note else str(p.get("label")))
    pens = [p for p in score.get("parts") or [] if (p.get("pts") or 0) < 0]
    out += [f"{p.get('label')} {p.get('pts')}" for p in pens]
    return out


def rank_session(rows: list[dict[str, Any]], *, favs: frozenset[str],
                 tracked: frozenset[str]) -> list[dict[str, Any]]:
    """The session: every tracked name the engine has read, in its own order (the setup
    score, ranked on the uncapped sum with the RVOL gate: scanscore.build). Pure."""
    ok = [r for r in rows if r.get("ok") and r.get("score")]
    ok.sort(key=lambda r: ((r.get("score") or {}).get("rank") or 999))
    out = []
    for r in ok:
        sc = r["score"]
        lv = r.get("levels") or {}
        cat = r.get("catalyst")
        out.append({
            **_base(r["sym"], name=r.get("name"), sector=r.get("sector"), favs=favs,
                    tracked=tracked),
            "last": r.get("last"), "live": bool(r.get("live")), "chg": _chg_of(r), "move": "day",
            "score": sc.get("total"), "raw": sc.get("raw"), "score_max": 100,
            "score_kind": "setup", "gated": bool(sc.get("gated")),
            "why": _why_score(sc), "story": cat, "lean": sc.get("side"),
            "plan": None, "setup": _setup_out(r.get("setup")),
            "levels": {k: lv.get(k) for k in ("pdh", "pdl", "pmh", "pml", "pdc", "vwap")},
            "gap_atr": None, "vol_pct": None, "rvol": r.get("rvol"), "stage": r.get("stage"),
            "spark": r.get("spark"),
        })
    return out


def _chg_of(r: dict[str, Any]) -> float | None:
    last, pdc = _num(r.get("last")), _num((r.get("levels") or {}).get("pdc"))
    if last is not None and pdc:
        return (last / pdc - 1.0) * 100.0
    return _num(r.get("chg_pct"))


# ------------------------------------------------------------------------ evening


def evening_points(r: dict[str, Any], ah: dict[str, Any] | None) -> dict[str, Any] | None:
    """One name's evening read: the better of its move after the close (the move in
    daily ATRs and the session's share of an average day, pool.session_points) and its
    day (the day's move in ATRs and its RVOL on the pool's scale). None when it has
    neither figure. Pure.

    `r` is the wide read's row (sources/universe), `ah` its after-hours figures when
    they are this evening's ({"last", "chg", "vol"}), else None.
    """
    atr, close, avg = _num(r.get("atr")), _num(r.get("close")), _num(r.get("avg"))
    if not atr or not close:
        return None
    best: dict[str, Any] | None = None
    if ah and ah.get("last") is not None and ah.get("chg") is not None:
        move_atr = abs(float(ah["last"]) - close) / atr
        share = (float(ah["vol"]) / avg * 100.0) if ah.get("vol") and avg else None
        best = {"which": "after", "pts": pool.session_points(move_atr, share),
                "move_atr": move_atr, "chg": float(ah["chg"]), "share": share,
                "rvol": None, "last": float(ah["last"])}
    prev, chg = _num(r.get("c1")), _num(r.get("chg"))
    if prev and chg is not None:
        move_atr = abs(close - prev) / atr
        rvol = (float(r["vol"]) / avg) if r.get("vol") and avg else None
        pts = pool.gap_points(move_atr) + pool.volume_points(
            rvol, pool.RVOL_MIN, pool.RVOL_FULL, pool.RVOL_FAR)
        day = {"which": "day", "pts": pts, "move_atr": move_atr, "chg": chg, "share": None,
               "rvol": rvol, "last": close}
        if best is None or pts > best["pts"]:
            best = day
    return best


def evening_gate(r: dict[str, Any], ah: dict[str, Any] | None) -> bool:
    """The evening's names: $10 and the pool's dollar day (on average or today), or a
    move after the close of pool.UNUSUAL_PCT on AH_TURNOVER, which is a report or a
    story being traded. Pure."""
    close, avg, vol = _num(r.get("close")), _num(r.get("avg")), _num(r.get("vol"))
    if close is None or close < pool.MIN_PRICE:
        return False
    if (avg or 0) * close >= pool.MIN_DOLLAR_VOL or (vol or 0) * close >= pool.MIN_DOLLAR_VOL:
        return True
    if ah and ah.get("vol") and ah.get("chg") is not None and ah.get("last"):
        return (abs(float(ah["chg"])) >= pool.UNUSUAL_PCT
                and float(ah["vol"]) * float(ah["last"]) >= AH_TURNOVER)
    return False


def report_words(sym: str, reports: dict[str, dict[str, Any]], today: date,
                 next_day: date) -> tuple[str | None, float]:
    """A report tonight or before the next open, in words and the pool's points. Pure."""
    rep = reports.get(sym)
    if not rep:
        return None, 0.0
    d, when, sp = rep.get("date"), rep.get("when"), rep.get("surprise_pct")
    if d == today.isoformat() and when == "after":
        tail = f", EPS {sp:+.1f}% vs estimate" if isinstance(sp, (int, float)) else ""
        return f"reported after the close{tail}", float(pool.W_REPORT)
    if d == next_day.isoformat() and when == "pre":
        return "reports before the open", float(pool.W_REPORT)
    return None, 0.0


def rank_evening(rows: Iterable[dict[str, Any]], *, ah_of: Callable[[dict[str, Any]],
                 dict[str, Any] | None],
                 catalyst: Callable[[str], dict[str, Any] | None],
                 stage: dict[str, int], reports: dict[str, dict[str, Any]],
                 session_day: date, next_day: date, favs: frozenset[str],
                 tracked: frozenset[str], floor: float = pool.MIN_CAP,
                 limit: int = TOP_N) -> list[dict[str, Any]]:
    """The evening and overnight list: every $2bn+ name past `evening_gate`, scored by
    `evening_points` plus a fresh major story (pool.W_NEWS) or a report tonight or
    before the open (pool.W_REPORT), and tomorrow's Day 2 or 3 (a Day 1 today of
    DAY1_MOVE on DAY1_RVOL, or a track the Day 2/3 ledger already holds), over
    EVENING_MIN, best first. Tomorrow's levels are today's range. Pure."""
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = r.get("sym")
        if not sym or sym in BENCHMARKS or (r.get("cap") or 0) < floor:
            continue
        ah = ah_of(r)
        if not evening_gate(r, ah):
            continue
        read = evening_points(r, ah)
        if read is None:
            continue
        story = catalyst(sym)
        rep_words, rep_pts = report_words(sym, reports, session_day, next_day)
        news_pts = float(pool.W_NEWS) if (story or {}).get("major") and not rep_pts else 0.0
        day_chg, rvol_day = _num(r.get("chg")), (
            float(r["vol"]) / float(r["avg"]) if r.get("vol") and r.get("avg") else None)
        n = stage.get(sym, 0)
        tomorrow = n + 1 if n >= 1 else (
            2 if day_chg is not None and abs(day_chg) >= DAY1_MOVE
            and (rvol_day or 0) >= DAY1_RVOL else 0)
        day_pts = (float(pool.W_DAY2) if tomorrow == 2 else
                   float(pool.W_DAY3) if tomorrow >= 3 else 0.0)
        score = read["pts"] + rep_pts + news_pts + day_pts
        if score < EVENING_MIN:
            continue
        why: list[str] = []
        if read["which"] == "after":
            why.append(f"after hours {_arrow(read['chg'])} {read['move_atr']:.2f} ATR")
            if read["share"] is not None:
                why.append(f"{read['share']:.1f}% of an average day after the close")
        else:
            why.append(f"day {_arrow(read['chg'])} {read['move_atr']:.2f} ATR")
            if read["rvol"] is not None:
                why.append(f"RVOL {read['rvol']:.2f}×")
        if rep_words:
            why.append(rep_words)
        elif news_pts:
            why.append(f"{str(story.get('tag') or 'major').lower()} news")
        if tomorrow >= 2:
            why.append(f"tomorrow is day {tomorrow} of a {day_chg:+.0f}% move"
                       if n < 1 and day_chg is not None else f"tomorrow is day {tomorrow}")
        last = read["last"]
        lv = {"pdh": _num(r.get("high")), "pdl": _num(r.get("low")), "pmh": None, "pml": None,
              "pdc": _num(r.get("close"))}
        out.append({
            **_base(sym, name=r.get("name"), sector=r.get("sector"), cap=r.get("cap"),
                    favs=favs, tracked=tracked),
            "last": last, "live": False, "chg": read["chg"], "move": read["which"],
            "score": round(score, 1), "score_max": pool.SCORE_MAX, "score_kind": "in play",
            "why": why, "story": story,
            "lean": "long" if read["chg"] > 0 else "short" if read["chg"] < 0 else None,
            "plan": plan_of(last, lv["pdh"], lv["pdl"], None, None), "setup": None,
            "levels": lv, "gap_atr": round(read["move_atr"], 2), "vol_pct": read["share"],
            "rvol": read["rvol"], "stage": tomorrow or None,
        })
    out.sort(key=lambda x: (-x["score"], x["sym"]))
    return out[:limit]


# ------------------------------------------------------------------- the payload


def mark_new(rows: list[dict[str, Any]], seen: dict[str, float], now_ts: float,
             fresh: bool) -> None:
    """Mark the rows that came into the top ten in the last NEW_MIN minutes, and keep
    `seen` (symbol → when first seen there) for the phase. On the phase's first read
    (`fresh`) nothing is new: everything is. In place."""
    for i, r in enumerate(rows):
        if i >= 10:
            break
        first = seen.setdefault(r["sym"], now_ts if not fresh else now_ts - NEW_MIN * 60.0 - 1)
        r["new"] = now_ts - first <= NEW_MIN * 60.0


def numbered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


# ------------------------------------------------------------------- the record
#: Each phase's list is written down this close to its end (collector._today_log), so
#: the evening's, the pre-market's and the open's ranks can be held to what the names did
#: next, as the pool's marks are (pool_marks.jsonl). The session's is the signal log.
MARKS_NAME = "today_marks.jsonl"
LOG_BEFORE_END_MIN = 5.0
MARKS_LOGGED = 20


def log_line(got: dict[str, Any], now: datetime) -> dict[str, Any]:
    """One phase's list as a log line: its top MARKS_LOGGED, each with what ranked it.
    Pure."""
    ph = got.get("phase") or {}
    return {
        "kind": "today", "phase": ph.get("key"), "day": ph.get("day"),
        "at_et": now.astimezone(ET).strftime("%Y-%m-%d %H:%M"),
        "rows": [{k: r.get(k) for k in ("rank", "sym", "score", "score_kind", "lean", "chg",
                                         "last", "gap_atr", "vol_pct", "rvol", "stage", "fav",
                                         "tracked", "group", "why")}
                 for r in (got.get("rows") or [])[:MARKS_LOGGED]],
    }


def log_list(path: str, got: dict[str, Any], now: datetime) -> None:
    """Append `log_line` to `path`; a log that cannot be written is skipped."""
    pool._append(path, log_line(got, now))
