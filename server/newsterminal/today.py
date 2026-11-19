"""
TODAY: THE STOCKS TAB'S ONE LIST, RANKED FOR THE HOUR IT IS.

The owner, 2026-11-13: "we really need to overhaul the whole stocks scanner section so
that it calculates and scores as best as possible depending on the time ... instead we
have set ups that just change and display the best options for a given period and
updates and scores live based on changes and what happens and any news that comes in";
then "make premarket 4:00-9:30 and the open 9:30-10:00 and then the rest of the
session". Setups, Breakouts, Extended hours and Day 2/3 were four answers to one
question, each ranked its own way; this is one answer that changes with the clock.

Four phases (ET; a half day closes at 13:00 and its late session ends at 17:00):

  after      the close → 20:00   moving after the close, and the day's big movers
  overnight  20:00 → 04:00, and every day the market is shut: the evening's movers and
             the reports due before the next open, the prep for the next session
  pre        04:00 → 09:30       in play going into the open
  session    09:30 → the close   the best trades now: the engine's setup score

THE OPEN IS THE SESSION (owner, 2026-11-13: "i think 9:30-16:00 should just be ranked by
score? because a lot of good trades can be taken in the first 30 mins"). From 09:30 to
10:00 there was a fifth phase, "the open", which kept the pre-market's in-play score and
ordered the names by what the bell had done to them (entry live, through a level, not
triggered, failed), on the audit's figures below. It left relative strength and the
open's own volume out of the order, which is what the first half hour shows best; the
setup score reads both, so it ranks from the bell.

WHAT EACH RANKS BY, AND WHY (the quant audit of 2026-11-13). Before the bell the size of
a move can be read and its direction cannot: a gap of 3+ daily ATRs meant 2.7x a normal
day's range over a year, and the gap's direction told nothing. So the evening, the
overnight and the pre-market lists rank how in play a name is, read the way the pool
reads it (sources/pool: the move in daily ATRs, volume against normal, a report, a fresh
major story, a level already through, a Day 2 or 3), and show the levels both ways with
the gap's side as a lean, never a call. The open's first half hour reached +1R on 39% of
signals against 52% from 10:00, and RVOL is thin until about 09:45: worth knowing when
reading an early signal, and no longer a reason to rank the first half hour another way
(above). From 09:30 the engine's score ranks, unchanged, so the two-week test of its
weights runs on.

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

PHASES = ("after", "overnight", "pre", "session")
LABELS = {"after": "After hours", "overnight": "Overnight", "pre": "Pre-market",
          "session": "Session"}
TITLES = {
    "after": "Moving after the close, and today's big movers: the prep for the next session",
    "overnight": "The prep for the next session: the evening's movers and the reports "
                 "due before the open",
    "pre": "In play going into the open",
    "session": "The best trades now",
}
PRE_START = 4 * 60
OPEN_START = 9 * 60 + 30
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
                "next": self.next_key,
                # The session's start is still called the open where it is counted down
                # to ("The open in 48m"), though it is no phase of its own any more.
                "next_label": "The open" if self.next_key == "session" else LABELS[self.next_key]}


def _at(d: date, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=ET)


def phase_at(now: datetime) -> Phase:
    """The phase at `now`. Pure.

    Worked examples (tests/test_today.py has the table): Friday 13 Nov 2026 03:59 is
    overnight for the 13th, 04:00 pre, 09:30 session, 16:00 after hours for
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
            return Phase("pre", d, _at(d, OPEN_START), "session")
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
        # NO PRE-MARKET TRADE, NOT IN PLAY INTO THE OPEN (live, 13 Nov 04:03): IREN made
        # the list on an old story and "day 5 of a big move" with nothing traded yet. The
        # pool may still rank it (a story and a Day 3 clear its bar); this list waits for
        # the name to trade.
        if r.get("pm_close") is None:
            continue
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
            # The report the pool read, for the pre-market record (premarket_record.py).
            "report": e.get("reports"),
        })
        if len(out) >= limit:
            break
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
            "spark": r.get("spark"), "spark_ref": r.get("spark_ref"),
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
            why.append(f"{str((story or {}).get('tag') or 'major').lower()} news")
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
            # A lean needs the move the pre-market list asks for (pool.GAP_MIN, a tenth of
            # an ATR): under it the name is on the list for its report or its story, and
            # 0.09 of an ATR after the close is not a side (MSFT, 14 Nov 2026).
            "lean": (("long" if read["chg"] > 0 else "short")
                     if read["chg"] and read["move_atr"] >= pool.GAP_MIN else None),
            "plan": plan_of(last, lv["pdh"], lv["pdl"], None, None), "setup": None,
            "levels": lv, "gap_atr": round(read["move_atr"], 2), "vol_pct": read["share"],
            "rvol": read["rvol"], "stage": tomorrow or None,
        })
    out.sort(key=lambda x: (-x["score"], x["sym"]))
    return out[:limit]


# ------------------------------------------------------------ the rest of the list


def rest_of_list(rows: list[dict[str, Any]], engine: Iterable[dict[str, Any]], *,
                 inplay: dict[str, dict[str, Any]], favs: frozenset[str]
                 ) -> list[dict[str, Any]]:
    """Every name the engine tracks that the phase's ranking left off, to go under it,
    as the Setups table always showed the whole list (owner, 2026-11-13, at 04:13 ET:
    "why are only 8 stocks showing?" — the pre-market had traded on eight names the
    stream had seen, and the screener runs fifteen minutes behind). Ordered by the
    pool's in-play read where it has one (`inplay`, pool rank entries by symbol), then
    the engine's own order. Pure."""
    have = {r["sym"] for r in rows}
    rest = [e for e in engine if e.get("ok") and e.get("sym") not in have]

    def key(e: dict[str, Any]) -> tuple[float, int]:
        ip = inplay.get(str(e["sym"])) or {}
        return (-float(ip.get("score") or 0.0), int((e.get("score") or {}).get("rank") or 999))

    out = []
    for e in sorted(rest, key=key):
        ip = inplay.get(str(e["sym"])) or {}
        lv = e.get("levels") or {}
        out.append({
            **_base(str(e["sym"]), name=e.get("name"), sector=e.get("sector"), favs=favs,
                    tracked=frozenset({str(e["sym"])})),
            "last": e.get("last"), "live": bool(e.get("live")), "chg": _chg_of(e),
            "move": "day", "score": float(ip.get("score") or 0.0),
            "score_max": pool.SCORE_MAX, "score_kind": "in play",
            "why": [str(ip.get("reason") or "not in play yet")], "story": e.get("catalyst"),
            "lean": (e.get("score") or {}).get("side"), "plan": None, "setup": None,
            "levels": {k: lv.get(k) for k in ("pdh", "pdl", "pmh", "pml", "pdc")},
            "gap_atr": ip.get("gap_atr"), "vol_pct": ip.get("vol_pct"), "rvol": e.get("rvol"),
            "stage": e.get("stage"), "spark": e.get("spark"), "spark_ref": e.get("spark_ref"),
            "listed": True,
        })
    return out


# ------------------------------------------------------------- the table's row

def _inplay_score(t: dict[str, Any], side: str | None, base: dict[str, Any] | None
                  ) -> dict[str, Any]:
    """Before 10:00 the list ranks how in play a name is (0 to pool.SCORE_MAX); the
    table's Score column reads 0 to 100, so the in-play read shows as its share of the
    most, with the read itself as the one part (the score's hover)."""
    pts = float(t.get("score") or 0.0)
    mx = float(t.get("score_max") or pool.SCORE_MAX)
    return {**(base or {}), "total": round(min(100.0, 100.0 * pts / mx)) if mx else 0,
            "raw": round(pts, 1), "rank": t.get("rank"), "side": side, "gated": None,
            # What this score is, for the slide-out's Score card: the list's in-play read,
            # not the setup score (owner, 2026-11-18).
            "kind": "inplay",
            "parts": [{"key": "inplay", "label": "In play", "pts": round(pts, 1),
                       "max": round(mx), "note": " · ".join(t.get("why") or [])}]}


def off_list(sym: str, ip: dict[str, Any] | None) -> dict[str, Any]:
    """A name the phase's list does not hold, as a Today row for `scan_row`: its in-play
    read from the pool, worded as `rest_of_list` words it for the tracked names under
    the ranking, and no lean of its own. Pure."""
    ip = ip or {}
    return {"sym": sym, "score": float(ip.get("score") or 0.0),
            "score_max": pool.SCORE_MAX, "why": [str(ip.get("reason") or "not in play yet")],
            "lean": None, "rank": None}


def _lean_setup(lean: str, eng: dict[str, Any]) -> dict[str, Any]:
    """The engine's pre-market plan for the other side: the same trigger `plan_of` picks
    on the engine's own levels, in the words scan.setup_of writes for a plan. Pure."""
    lv = eng.get("levels") or {}
    last = _num(eng.get("last"))
    out: dict[str, Any] = {"side": lean, "state": "forming", "level": None, "entry": None,
                           "note": ""}
    trig = plan_of(last, _num(lv.get("pdh")), _num(lv.get("pdl")), _num(lv.get("pmh")),
                   _num(lv.get("pml"))).get(lean)
    if not trig or last is None:
        return out
    k, p = trig["level"], float(trig["price"])
    ab = _num(eng.get("atr_b"))
    out["level"] = k
    out["entry"] = {"kind": k, "price": p, "dist_atr": round((last - p) / ab, 2) if ab else 0.0}
    if trig["held"]:
        word = "above" if lean == "long" else "below"
        out["note"] = f"Holding {word} {k} {scan.fmt_px(p)} — plan: the retest of it after the open"
    else:
        out["note"] = f"Plan: break of {k} {scan.fmt_px(p)}, then the retest"
    return out


def scan_row(t: dict[str, Any], eng: dict[str, Any] | None, phase: str,
             wide: dict[str, Any] | None) -> dict[str, Any]:
    """The Setups table's row for one Today row (src/types/scanner.ts ScanRow), so the
    list is drawn in the table the owner knows (2026-11-13: "i prefer the general style
    of what it was before"). A name the engine tracks is its own row, with the score
    shown as the phase ranks it (in play before 10:00, the setup score after). A name it
    does not track yet is built from the wide read: levels, the move, the pre-market,
    the story, and the plan as the setup. Pure."""
    if eng is not None and eng.get("ok"):
        row = dict(eng)
        if phase == "session":
            row["score"] = {**(eng.get("score") or {}), "rank": t.get("rank")}
        else:
            side = (eng.get("score") or {}).get("side") or t.get("lean")
            # ONE RULE FOR THE LIST (owner, 2026-11-15, of an audit of the sides: "do what
            # you recommend"). A name the engine does not track is leaned by the move that
            # put it on the list; a tracked one took the engine's side whatever it was, so
            # the weekend of 14 Nov showed NVDA long on a row that read "day ▼". While the
            # engine is planning (before the bell, overnight: its setup is "forming"), a
            # tracked name keeps the engine's side only when it is through a level; inside
            # them it takes the list's lean, and the plan is written for that side.
            planning = (eng.get("setup") or {}).get("state") == "forming"
            lean = t.get("lean")
            if planning and not (eng.get("lvl_state") or 0) and lean and lean != side:
                side = lean
                row["setup"] = _lean_setup(lean, eng)
            row["score"] = _inplay_score(t, side, eng.get("score"))
            # The record line is the setup score's band ("longs scored 40-59"), which is
            # not the number this row shows before the bell.
            row["record"] = None
        row["catalyst"] = eng.get("catalyst") or t.get("story")
        row["today"] = {k: t.get(k) for k in ("rank", "why", "new", "status", "move")}
        # For the Today bar's Filters (market cap): the engine's row does not carry it.
        row["market_cap"] = t.get("cap") or (wide or {}).get("cap")
        # Before the bell: the four figures shown and logged, never scored
        # (premarket_record.py, 2026-11-18). None in the session.
        row["pre_ctx"] = t.get("pre_ctx") if phase != "session" else None
        # The list's spark, laid on as the list was read (collector.today, fill_spark).
        if t.get("spark"):
            row["spark"], row["spark_ref"] = t["spark"], t.get("spark_ref")
        return row
    w = wide or {}
    lv = t.get("levels") or {}
    last = t.get("last")
    pdh, pdl, pmh, pml = lv.get("pdh"), lv.get("pdl"), lv.get("pmh"), lv.get("pml")

    def over(x: Any) -> bool:
        return isinstance(last, (int, float)) and isinstance(x, (int, float)) and last > x

    def under(x: Any) -> bool:
        return isinstance(last, (int, float)) and isinstance(x, (int, float)) and last < x

    up = int(over(pdh)) + int(over(pmh))
    dn = int(under(pdl)) + int(under(pml))
    lean = t.get("lean")
    trig = ((t.get("plan") or {}).get(lean) if lean else None) or {}
    pre_like = phase in ("pre", "after", "overnight")
    move = t.get("chg")
    if t.get("move") == "day":
        chg, ext = move, None
    else:
        chg, ext = _num(w.get("chg")), move
    vol_pct = t.get("vol_pct")
    pm_vol = _num(w.get("pm_vol")) if phase == "pre" else None
    return {
        "sym": t["sym"], "name": t.get("name"), "sector": t.get("sector"), "sector_rs": None,
        "ok": True, "error": None, "age_min": None, "promoted": None,
        "last": last, "prev_close": lv.get("pdc"), "chg_pct": chg, "ext_pct": ext,
        "volume": _num(w.get("vol")) if t.get("move") == "day" else None,
        "rvol": t.get("rvol"), "atr_d": _num(w.get("atr")), "atr_b": None,
        "rs": {"SPY": None, "QQQ": None}, "rs_1h": {"SPY": None, "QQQ": None},
        "levels": {"pdh": pdh, "pdl": pdl, "pdc": lv.get("pdc"), "pmh": pmh, "pml": pml,
                   "pm_done": not pre_like, "vwap": None, "wave_hi": None, "wave_lo": None,
                   "ema8": None, "day_hi": None, "day_lo": None, "open": None},
        "progress": {"pdh": None, "pdl": None, "pmh": None, "pml": None},
        "broken": {"pdh": over(pdh), "pdl": under(pdl), "pmh": over(pmh), "pml": under(pml)},
        # As scan.lvl_state_of: over one high and under one low is no state.
        "lvl_state": up if up and not dn else -dn if dn and not up else 0,
        "trend": 1 if up == 2 else -1 if dn == 2 else 0,
        "range_used": None,
        "setup": {"side": lean, "state": "forming", "level": trig.get("level"), "entry": None,
                  "note": ""},
        "signals": [], "score": _inplay_score(t, lean, None), "flags": [], "earnings": None,
        "news": [], "filings": [], "options": None, "adv": _num(w.get("avg")),
        "premkt": ({"volume": pm_vol, "pct_adv": vol_pct, "high": pmh, "low": pml,
                    "last": last, "asof": None, "source": "screener"}
                   if phase == "pre" else None),
        "catalyst": t.get("story"), "stage": t.get("stage"), "spark": t.get("spark"),
        "spark_ref": t.get("spark_ref"), "tracked": False,
        "market_cap": t.get("cap") or _num(w.get("cap")),
        "today": {k: t.get(k) for k in ("rank", "why", "new", "status", "move")},
        "pre_ctx": t.get("pre_ctx") if phase != "session" else None,
    }


# ------------------------------------------------------------------- the payload


def mark_new(rows: list[dict[str, Any]], seen: dict[str, float], now_ts: float,
             fresh: bool) -> None:
    """Mark the rows that came into the top ten in the last NEW_MIN minutes, and keep
    `seen` (symbol → when first seen there) for the phase. On the phase's first read
    with rows (`fresh`, or nothing seen yet) nothing is new: everything is. (Live, 13 Nov:
    the pre-market's first read at 04:00 had no rows, and the first names at 04:03 were
    all stamped new.) In place."""
    fresh = fresh or not seen
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
                                         "tracked", "group", "why", "listed")}
                 for r in (got.get("rows") or [])[:MARKS_LOGGED]],
    }


def log_list(path: str, got: dict[str, Any], now: datetime) -> None:
    """Append `log_line` to `path`; a log that cannot be written is skipped."""
    pool._append(path, log_line(got, now))
