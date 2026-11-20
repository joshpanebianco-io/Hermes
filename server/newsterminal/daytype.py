"""
Session type — will New York trend, or range? The pieces, kept pure, and the
record they are kept in.

WHY (owner, 2026-11-10: "is the app capable of determining whether each upcoming
new york session will be more likely to be a trending or ranging/inside day?
depending on what the previous days new york session did? or what the futures
indices did in other sessions overnight?"). It was not. The ladder says what
yesterday was (structure.yesterday), the profile says where today opened against
value, the gamma regime and the VIX band say what kind of tape to expect — and
nothing combined them into a call, and nothing had been measured. This module is
the measuring: the LABEL a finished session gets, the FEATURES known before the
bell, and the BASE RATES of one against the other, with the counts.

THE LABEL IS THE LADDER'S OWN RULE, so the forecast and the description agree: a
session TREND_DAY_ATR or more wide that closes in its outer CLOSE_EDGE is a trend
day; one RANGE_DAY_ATR or narrower is a range day; the rest are normal. An inside
day sits inside the session before it, whatever else it is. The ATR is the
fourteen-day average true range of the same instrument's daily bars.

WHAT IT RUNS ON. Two years of hourly bars (tools/daytype_backfill.py): the cash
ETF's for the session itself, because Yahoo aligns them to 09:30 while the
future's run on the hour and the 09:00 bar straddles the open; the future's for
the night, which the ETF never sees. So the features are read at 09:00 ET, not
09:25, in the backfill; the live card reads them at CARD_AT and the two are kept
apart in the tables. A probability here is a count, never a model: `base_rates`
prints n beside every figure, and a condition with under BASE_MIN sessions
behind it is printed but not to be trusted.

THE RECORD (SessionLog, cache/session_types.jsonl). The collector's daytype job
writes one card per book at CARD_AT with what was known before the bell — the
night's boxes from the Session ranges panel, yesterday's shape and the fuel from
the ladder's own readers (structure.py), the vol curve, the gamma regime, the
morning's prints — and after the close puts the label on it from the finished
New York row. One line per day and book; the label replaces the card. A card
written after the open says so (`late`), so the forward record can be read
without it. Nothing on a page reads this yet: the lean the Futures page is owed
is owed a record first.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import CACHE_DIR
from .sessions import NY_OPEN
from .structure import CLOSE_EDGE, QUIET_NIGHT_ATR, RANGE_DAY_ATR, TREND_DAY_ATR

ET = ZoneInfo("America/New_York")
#: The books the record is kept for: the ones the backfill has base rates for.
BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")
#: When the live card is written and when its label is put on, ET. The label
#: waits ten minutes past the bell for the ranges job's last five-minute bar.
CARD_AT = time(9, 25)
LABEL_AT = time(16, 10)
LOG_NAME = "session_types.jsonl"
#: Below this many sessions a base rate is printed with a mark, not read.
BASE_MIN = 25
#: The night's boxes, in ET, as the Session ranges panel draws them; the pre-market
#: box ends at 09:00 here because the hourly bars do (module docstring).
WINDOWS: dict[str, tuple[time, time]] = {
    "overnight": (time(18, 0), time(9, 0)),
    "asia": (time(20, 0), time(0, 0)),
    "london": (time(2, 0), time(5, 0)),
    "pre": (time(4, 0), time(9, 0)),
}
#: A gap, a night or a range this far in ATRs is "big"; this near, "quiet" — the
#: fuel line's own word for a night (structure.QUIET_NIGHT_ATR), in the same ATR.
BIG_ATR = 0.8
QUIET_ATR = QUIET_NIGHT_ATR
#: Where 09:00 sits in the night's range to count as at an edge.
EDGE_POS = 0.15
#: The morning's prints that go on the card: calendar score this or more, due in
#: this window ET (08:30 and 10:00 are the hours that matter; 08:15 is ADP).
PRINT_SCORE = 4
PRINT_WINDOW = (time(8, 0), time(11, 0))
#: A condition votes for a call only with this many sessions behind it: BASE_MIN
#: prints a rate, a call wants more.
VOTE_MIN = 50
#: A condition votes "range" when its range rate is this far over the base rate (and
#: its trend rate no higher), "trend" when its trend rate is TREND_LIFT times the base
#: and at least TREND_FLOOR — a lift from 7% to 9% is not a lean.
RANGE_LIFT = 0.10
TREND_LIFT = 1.5
TREND_FLOOR = 0.10
#: A condition votes AGAINST a trend day ("no_trend") when its trend rate is under this
#: share of the base (owner, 2026-11-16: "why are the nq and es both the same amount of
#: bias points but nq says no lean and es says trend say mor eposisble", then "do what you
#: recommend"). That morning ES read "Trend day more possible" on one condition (after a
#: normal day, 24 trend days in 189 against 41 in 573) while Monday, 3 trend days in 105,
#: under half the base, was printed and ignored: it only voted if its RANGE rate was ten
#: points up as well. A halved trend rate is a vote against the trend call, so the two
#: together read "Mixed record". Alone it calls nothing: fewer trend days is not a range
#: day.
TREND_DROP = 0.5
CALL_WORD = {"range": "Range day likely", "trend": "Trend day more possible",
             "mixed": "Mixed record", "none": "No lean"}
#: The backfill tool's file (tools/daytype_backfill.py), the record's larger half.
BACKFILL_NAME = "daytype_backfill.json"

Bar = tuple[int, float, float, float, float]  # ts, open, high, low, close
Span = tuple[float, float, float, float]  # open, high, low, close


# ------------------------------------------------------------------ the label


def label(o: float, h: float, lo: float, c: float, atr: float | None,
          prev_h: float | None = None, prev_l: float | None = None) -> dict[str, Any]:
    """A finished session's type by the ladder's rule. Pure.

    Worked examples (ATR 100): o 100 h 230 l 95 c 225 → trend up (1.35 ATR, closed at
    96% of its range); o 100 h 150 l 90 c 120 → range (0.60 ATR); o 100 h 210 l 90
    c 150 → normal (1.20 ATR, closed mid-range); inside when h ≤ prev_h and l ≥ prev_l,
    None when yesterday's range is not known.
    """
    r = h - lo
    rng_atr = r / atr if atr else None
    pos = (c - lo) / r if r > 0 else None
    eff = abs(c - o) / r if r > 0 else None
    kind, direction = "normal", None
    if rng_atr is not None and pos is not None:
        if rng_atr >= TREND_DAY_ATR and pos >= 1.0 - CLOSE_EDGE:
            kind, direction = "trend", "up"
        elif rng_atr >= TREND_DAY_ATR and pos <= CLOSE_EDGE:
            kind, direction = "trend", "down"
        elif rng_atr <= RANGE_DAY_ATR:
            kind = "range"
    inside = ((h <= prev_h and lo >= prev_l) if (prev_h is not None and prev_l is not None)
              else None)
    return {"type": kind, "dir": direction, "inside": inside,
            "range_atr": round(rng_atr, 3) if rng_atr is not None else None,
            "close_pos": round(pos, 3) if pos is not None else None,
            "efficiency": round(eff, 3) if eff is not None else None}


def true_range(h: float, lo: float, prev_c: float | None) -> float:
    return max(h - lo, abs(h - prev_c), abs(lo - prev_c)) if prev_c is not None else h - lo


def atr_series(days: list[tuple[date, float, float, float, float]], n: int = 14
               ) -> dict[date, float]:
    """{day: the ATR of the n sessions BEFORE it}, from (day, o, h, l, c) rows. Pure."""
    out: dict[date, float] = {}
    trs: list[float] = []
    prev_c: float | None = None
    for d, _o, h, lo, c in days:
        if len(trs) >= n:
            out[d] = sum(trs[-n:]) / n
        trs.append(true_range(h, lo, prev_c))
        prev_c = c
    return out


# --------------------------------------------------------------- the windows


def window(bars: Iterable[Bar], start: datetime, end: datetime) -> Span | None:
    """(o, h, l, c) of the bars whose START is in [start, end), or None. Pure."""
    s, e = start.timestamp(), end.timestamp()
    picked = [b for b in bars if s <= b[0] < e]
    if not picked:
        return None
    return (picked[0][1], max(b[2] for b in picked), min(b[3] for b in picked), picked[-1][4])


def at(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=ET)


def night_windows(session: date, prev_session: date) -> dict[str, tuple[datetime, datetime]]:
    """The night before `session`, box by box: 18:00 after `prev_session`'s close to
    09:00 on `session`; Asia 20:00 the evening before to midnight; London 02:00–05:00
    ET; the pre-market from 04:00. The overnight is anchored to the previous SESSION,
    so Monday's night starts Friday; Asia is the night's own evening. Pure."""
    eve = session - timedelta(days=1)
    on_start, on_end = WINDOWS["overnight"]
    return {
        "overnight": (at(prev_session, on_start), at(session, on_end)),
        "asia": (at(eve, WINDOWS["asia"][0]), at(session, time(0, 0))),
        "london": (at(session, WINDOWS["london"][0]), at(session, WINDOWS["london"][1])),
        "pre": (at(session, WINDOWS["pre"][0]), at(session, WINDOWS["pre"][1])),
    }


# -------------------------------------------------------------- the features


def features(session: date, prev: dict[str, Any] | None, prev_prev: dict[str, Any] | None,
             fut: list[Bar], atr_pct: float | None, prev_close_fut: float | None,
             vix: float | None, vix_ratio: float | None) -> dict[str, Any]:
    """What is known of `session` at 09:00 ET, for the backfill. `prev` is the
    previous session's labelled row ({day, type, dir, inside, close_pos, range_atr,
    high, low, ratio}), `fut` the future's hourly bars, `atr_pct` the ETF's ATR as a
    percent of price, `prev_close_fut` the future's price at the previous session's
    16:00, and the VIX figures the previous close's (ratio) and 09:00's (level). Pure.

    Ranges are percents of the future's own price against the ETF's ATR percent, so
    the night is in the same unit as the day: an overnight range of 0.5 ATR means the
    night covered half of what the cash session usually covers.
    """
    prev_day = prev["day"] if prev else session - timedelta(days=1)
    out: dict[str, Any] = {
        "day": session.isoformat(), "weekday": session.strftime("%a"),
        "prev_type": prev.get("type") if prev else None,
        "prev_dir": prev.get("dir") if prev else None,
        "prev_inside": prev.get("inside") if prev else None,
        "prev_close_pos": prev.get("close_pos") if prev else None,
        "prev_range_atr": prev.get("range_atr") if prev else None,
        "prev_prev_type": prev_prev.get("type") if prev_prev else None,
        "vix": vix, "vix_ratio": vix_ratio, "inventory": None, "gap_atr": None,
        "open_vs_prev": None,
    }
    pre_open: float | None = None
    for key, (s, e) in night_windows(session, prev_day).items():
        w = window(fut, s, e)
        if w is None or not prev_close_fut or not atr_pct:
            out[f"{key}_atr"] = None
            continue
        _o, h, lo, c = w
        out[f"{key}_atr"] = round((h - lo) / prev_close_fut * 100.0 / atr_pct, 3)
        if key == "overnight":
            pre_open = c
            out["inventory"] = round((c - lo) / (h - lo), 3) if h > lo else None
    if pre_open is not None and prev_close_fut and atr_pct:
        out["gap_atr"] = round((pre_open - prev_close_fut) / prev_close_fut * 100.0 / atr_pct, 3)
    # Where 09:00 sits against the previous session's range, in the future's prices:
    # the ETF's high and low scaled by the future's close over the ETF's.
    if pre_open is not None and prev and prev.get("ratio") and prev.get("high") and prev.get("low"):
        hi, lo = prev["high"] * prev["ratio"], prev["low"] * prev["ratio"]
        out["open_vs_prev"] = "above" if pre_open > hi else "below" if pre_open < lo else "inside"
    return out


# ------------------------------------------------------------- the base rates

Cond = tuple[str, Callable[[dict[str, Any]], bool | None]]


def _is(key: str, value: Any) -> Callable[[dict[str, Any]], bool | None]:
    return lambda f: (f.get(key) == value) if f.get(key) is not None else None


def _cmp(key: str, test: Callable[[float], bool]) -> Callable[[dict[str, Any]], bool | None]:
    return lambda f: test(float(f[key])) if f.get(key) is not None else None


def _two_trend(f: dict[str, Any]) -> bool | None:
    if not f.get("prev_type") or not f.get("prev_prev_type"):
        return None
    return f["prev_type"] == "trend" and f["prev_prev_type"] == "trend"


def _night_after(night: Callable[[float], bool], prev: Callable[[str], bool]
                 ) -> Callable[[dict[str, Any]], bool | None]:
    def test(f: dict[str, Any]) -> bool | None:
        on, p = f.get("overnight_atr"), f.get("prev_type")
        if on is None or not p:
            return None
        return night(float(on)) and prev(str(p))
    return test


CONDITIONS: tuple[Cond, ...] = (
    ("yesterday was a trend day", _is("prev_type", "trend")),
    ("yesterday was a range day", _is("prev_type", "range")),
    ("yesterday was a normal day", _is("prev_type", "normal")),
    ("yesterday was an inside day", _is("prev_inside", True)),
    ("two trend days behind it", _two_trend),
    ("yesterday closed in its outer fifth",
     _cmp("prev_close_pos", lambda p: p <= CLOSE_EDGE or p >= 1 - CLOSE_EDGE)),
    (f"quiet night (under {QUIET_ATR} ATR)", _cmp("overnight_atr", lambda x: x < QUIET_ATR)),
    (f"big night ({BIG_ATR} ATR or more)", _cmp("overnight_atr", lambda x: x >= BIG_ATR)),
    # The two pairs that separate most (the backfill, 2026-11-10): a quiet night
    # after a range day trended once in 114 sessions on NQ, once in 129 on ES.
    ("quiet night after a range day",
     _night_after(lambda x: x < QUIET_ATR, lambda p: p == "range")),
    ("big night, yesterday not a range day",
     _night_after(lambda x: x >= BIG_ATR, lambda p: p != "range")),
    (f"big Asia ({QUIET_ATR} ATR or more)", _cmp("asia_atr", lambda x: x >= QUIET_ATR)),
    (f"big London ({QUIET_ATR} ATR or more)", _cmp("london_atr", lambda x: x >= QUIET_ATR)),
    (f"gap of {QUIET_ATR} ATR or more at 09:00", _cmp("gap_atr", lambda x: abs(x) >= QUIET_ATR)),
    ("09:00 outside yesterday's range",
     lambda f: (f["open_vs_prev"] != "inside") if f.get("open_vs_prev") else None),
    ("09:00 inside yesterday's range", _is("open_vs_prev", "inside")),
    (f"09:00 at an edge of the night's range (outer {EDGE_POS:.0%})",
     _cmp("inventory", lambda p: p <= EDGE_POS or p >= 1 - EDGE_POS)),
    ("VIX under 18", _cmp("vix", lambda v: v < 18)),
    ("VIX 18 to 28", _cmp("vix", lambda v: 18 <= v < 28)),
    ("VIX 28 or more", _cmp("vix", lambda v: v >= 28)),
    ("VIX over VIX3M (backwardation)", _cmp("vix_ratio", lambda r: r >= 1.0)),
    ("Monday", _is("weekday", "Mon")),
    ("Friday", _is("weekday", "Fri")),
)


def rates(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts of each type, and the inside share, over labelled rows. Pure."""
    rs = [r for r in rows if r.get("type")]
    n = len(rs)
    if n == 0:
        return {"n": 0}
    c = {k: sum(1 for r in rs if r["type"] == k) for k in ("trend", "normal", "range")}
    ins = sum(1 for r in rs if r.get("inside"))
    return {"n": n, "trend": c["trend"] / n, "normal": c["normal"] / n, "range": c["range"] / n,
            "inside": ins / n, "trend_n": c["trend"], "normal_n": c["normal"],
            "range_n": c["range"], "inside_n": ins}


def base_rates(rows: list[dict[str, Any]], conditions: tuple[Cond, ...] = CONDITIONS
               ) -> list[dict[str, Any]]:
    """One line per condition: the rates when it holds, and when it does not, each
    with n — the lift is the reader's to judge against the overall line. Pure."""
    out = [{"condition": "every session", **rates(rows)}]
    for name, test in conditions:
        yes = [r for r in rows if test(r) is True]
        no = [r for r in rows if test(r) is False]
        out.append({"condition": name, **rates(yes), "else": rates(no)})
    return out


def table(lines: list[dict[str, Any]]) -> str:
    """The base rates as text, for the tool and the record. Pure."""
    head = (f"{'condition':48} {'n':>5} {'trend':>6} {'normal':>6} {'range':>6} {'inside':>6}"
            "   else: n trend range")
    rows = [head, "-" * len(head)]
    for ln in lines:
        if not ln.get("n"):
            rows.append(f"{ln['condition']:48} {0:>5}     —")
            continue
        mark = " *" if ln["n"] < BASE_MIN else ""
        e = ln.get("else") or {}
        tail = f"   {e['n']:>4} {e['trend']:.0%} {e['range']:.0%}" if e.get("n") else ""
        rows.append(f"{ln['condition']:48} {ln['n']:>5} {ln['trend']:>6.0%} {ln['normal']:>6.0%} "
                    f"{ln['range']:>6.0%} {ln['inside']:>6.0%}{tail}{mark}")
    rows.append(f"* fewer than {BASE_MIN} sessions: a count, not a rate")
    return "\n".join(rows)


# ------------------------------------------------------------------- the lean


def rate_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{condition: the rates when it holds}, "every session" first, over labelled
    rows — computed once per record, so a card's lean is a lookup. Pure."""
    out = {"every session": rates(rows)}
    for name, test in CONDITIONS:
        out[name] = rates([r for r in rows if test(r) is True])
    return out


def _shown(name: str, card: dict[str, Any]) -> str | None:
    """The card's own figure for a holding condition, to print beside its name."""
    low = name.lower()
    if "edge" in low:
        key, unit = "inventory", ""
    elif "asia" in low:
        key, unit = "asia_atr", " ATR"
    elif "london" in low:
        key, unit = "london_atr", " ATR"
    elif "night" in low:
        key, unit = "overnight_atr", " ATR"
    elif "gap" in low:
        key, unit = "gap_atr", " ATR"
    elif "vix over" in low:
        key, unit = "vix_ratio", ""
    elif "vix" in low:
        key, unit = "vix", ""
    else:
        return None
    v = _num(card.get(key))
    if v is None:
        return None
    if key == "inventory":
        return f"{v:.0%} up the night's range"
    if key == "vix_ratio":
        return f"VIX/VIX3M {v:.2f}"
    if key == "overnight_atr" and card.get("night_done") is False:
        return f"{v:.2f}{unit} so far"
    return f"{v:.2f}{unit}" if unit else f"{v:.1f}"


def _phrase(h: dict[str, Any]) -> str:
    """"quiet night (0.31 ATR so far): 2 trend days in 142, 108 range"."""
    name = str(h["condition"])
    label = f"{name.split(' (')[0]} ({h['shown']})" if h.get("shown") else name
    days = "day" if h["trend"] == 1 else "days"
    return f"{label}: {h['trend']} trend {days} in {h['n']}, {h['range']} range"


def lean(card: dict[str, Any], table: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """What the record says about a session that looks like `card`: every condition
    that holds today with its count, which of them vote, and the call. A vote needs
    VOTE_MIN sessions and a lift worth the name (RANGE_LIFT, TREND_LIFT), or a trend
    rate under TREND_DROP of the base ("no_trend", against a trend call); the call is
    the side the votes agree on, "mixed" when a trend vote meets a range or no_trend
    vote, "none" when nothing in the record separates the day. Counts, never a
    probability. Pure."""
    base = table.get("every session") or {"n": 0}
    holds: list[dict[str, Any]] = []
    for name, test in CONDITIONS:
        if test(card) is not True:
            continue
        r = table.get(name) or {"n": 0}
        vote = None
        if r.get("n", 0) >= VOTE_MIN and base.get("n"):
            if r["range"] >= base["range"] + RANGE_LIFT and r["trend"] <= base["trend"]:
                vote = "range"
            elif r["trend"] >= max(base["trend"] * TREND_LIFT, TREND_FLOOR):
                vote = "trend"
            elif r["trend"] < base["trend"] * TREND_DROP:
                vote = "no_trend"
        holds.append({"condition": name, "shown": _shown(name, card), "n": int(r.get("n", 0)),
                      "trend": int(r.get("trend_n", 0)), "range": int(r.get("range_n", 0)),
                      "vote": vote})
    votes = {h["vote"] for h in holds if h["vote"]}
    against = bool(votes & {"range", "no_trend"})
    call = ("mixed" if "trend" in votes and against else "trend" if "trend" in votes
            else "range" if "range" in votes else "none")
    why = " · ".join(_phrase(h) for h in holds if h["vote"])
    if call == "none" and why:
        # Only votes against a trend day: fewer trend days than usual, and no range call.
        why = f"fewer trend days than usual, not a range call: {why}"
    if not why:
        why = ("nothing in the record separates today" if base.get("n")
               else "no record yet: run tools/daytype_backfill.py")
    return {
        "call": call, "word": CALL_WORD[call], "why": why, "holds": holds,
        "base": {"n": int(base.get("n", 0)), "trend": int(base.get("trend_n", 0)),
                 "range": int(base.get("range_n", 0))},
        "night": {"atr": card.get("overnight_atr"), "done": card.get("night_done"),
                  "asia": card.get("asia_atr"), "london": card.get("london_atr"),
                  "pre": card.get("pre_atr")},
        "prev": {"type": card.get("prev_type"), "dir": card.get("prev_dir"),
                 "range_atr": card.get("prev_range_atr")},
    }


def words(book: str, ln: dict[str, Any]) -> str:
    """The lean in one line, for the brief, Hermes and a tooltip."""
    b = ln.get("base") or {}
    base = (f" · base {b.get('trend', 0)} trend days in {b.get('n', 0)}, {b.get('range', 0)} range"
            if b.get("n") else "")
    return f"{book}: {ln.get('word')} — {ln.get('why')}{base}"


def load_backfill(path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """The backfill's labelled rows per book (tools/daytype_backfill.py's file), full
    sessions only; {} when the tool has not been run."""
    path = path or os.path.join(CACHE_DIR, BACKFILL_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for book, rows in (doc.get("rows") or {}).items() if isinstance(doc, dict) else []:
        out[str(book)] = [r for r in rows if isinstance(r, dict) and r.get("type")
                          and r.get("prev_type") and not r.get("half_day")]
    return out


# ---------------------------------------------------------------- the live card


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _span_atr(s: dict[str, Any] | None, atr: float | None) -> float | None:
    if not s or not atr:
        return None
    hi, lo = _num(s.get("high")), _num(s.get("low"))
    return round((hi - lo) / atr, 3) if hi is not None and lo is not None else None


def vix_of(volterm: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """(the VIX, VIX over VIX3M) from the terminal's vol-curve block (volterm.state). Pure."""
    vt = volterm or {}
    level = next((p.get("value") for p in vt.get("points") or []
                  if isinstance(p, dict) and p.get("key") == "VIX"), None)
    return _num(level), _num(vt.get("ratio"))


def gamma_of(asset: dict[str, Any] | None) -> dict[str, Any] | None:
    """The regime and the flip from one book's gamma entry (sources/gex.py). Pure."""
    if not asset or not asset.get("ok"):
        return None
    flip = next((x.get("price") for x in asset.get("levels") or []
                 if isinstance(x, dict) and x.get("key") == "flip"), None)
    return {"regime": asset.get("regime"), "flip": _num(flip)}


#: The suffixes a print family's rows differ by — the calendar lists CPI as nine rows
#: (the index, m/m, y/y, core, n.s.a.) — so the card can name the family once.
_PRINT_SUFFIXES = (" m/m", " y/y", " q/q", " price index", " index", ", n.s.a.", ", n.s.a",
                   ", s.a.", ", s.a", " n.s.a.", " n.s.a", " s.a.", " s.a")


def print_family(name: str) -> str:
    """"Core CPI m/m" → "CPI", "CPI Index, n.s.a." → "CPI", "ISM Services PMI" as it is. Pure."""
    s = name.strip()
    if s.lower().startswith("core "):
        s = s[5:]
    while True:
        low = s.lower()
        suf = next((x for x in _PRINT_SUFFIXES if low.endswith(x)), None)
        if suf is None:
            return s.strip()
        s = s[: -len(suf)].rstrip()


def prints_of(rows: Iterable[dict[str, Any]], day: date) -> list[str]:
    """The morning's prints that matter, in order: calendar rows scored PRINT_SCORE or
    more and due inside PRINT_WINDOW on `day` ET, one entry per family, with the read
    once it has printed — "CPI (hot)", "Retail Sales (mixed)" when its rows disagree. Pure."""
    lo, hi = at(day, PRINT_WINDOW[0]).timestamp(), at(day, PRINT_WINDOW[1]).timestamp()
    first: dict[str, float] = {}
    reads: dict[str, set[str]] = {}
    for r in rows:
        ts, sc = _num(r.get("ts")), _num(r.get("score"))
        name = str(r.get("event") or "").strip()
        if ts is None or sc is None or sc < PRINT_SCORE or not lo <= ts < hi or not name:
            continue
        fam = print_family(name)
        first.setdefault(fam, ts)
        if r.get("read"):
            reads.setdefault(fam, set()).add(str(r["read"]))
    out: list[str] = []
    for fam in sorted(first, key=lambda f: (first[f], f)):
        rs = reads.get(fam) or set()
        tag = next(iter(rs)) if len(rs) == 1 else "mixed" if rs else None
        out.append(f"{fam} ({tag})" if tag else fam)
    return out


def card_from_live(book: str, day: date, sessions: list[dict[str, Any]], atr: float | None, *,
                   yesterday: dict[str, Any] | None, fuel: dict[str, Any] | None,
                   vix: float | None, vix_ratio: float | None, gamma: dict[str, Any] | None,
                   em: float | None, prints: list[str], now: datetime,
                   half_day: bool = False, prev_card: dict[str, Any] | None = None
                   ) -> dict[str, Any]:
    """The live session card at CARD_AT from what the collector holds: the Session
    ranges rows (ranges.py, whose boxes are `overnight`, `asia`, `london`, `premkt`
    and `ny`), the ladder's yesterday and fuel (structure.py), the vol curve, the
    gamma regime and the expected move. The same names as `features` where the thing
    is the same, so the backfill and the live log can be read together.

    YESTERDAY COMES FROM THE ROWS BEFORE THE BELL AND FROM THE LOG AFTER IT. The
    ranges keep one run of bars a box, so from 09:30 the New York row is today's
    and `yesterday` (structure.yesterday) is None; `prev_card`, the previous
    session's labelled card, then supplies the shape, the high and low (for the
    inside test at labelling time) and the gap at the reopen. Pure."""
    rows = [s for s in sessions if isinstance(s, dict) and s.get("ok")]
    # The night's boxes are this session's own: a prior day's row (last night's
    # after the 18:00 reopen, Thursday's over a weekend) is not "the night so far".
    by = {s.get("key"): s for s in rows if not s.get("prior_day")}
    on = by.get("overnight")
    last = _num(on.get("close")) if on else None
    y = yesterday or {}
    shape = str(y.get("shape") or "")
    pc = prev_card or {}
    pny = pc.get("ny") if isinstance(pc.get("ny"), dict) else {}
    if shape:
        prev_type = ("trend" if shape.startswith("trend") else
                     "range" if shape == "range day" else "normal")
        prev_dir = "up" if shape.endswith("up") else "down" if shape.endswith("down") else None
        prev_pos, prev_rng = y.get("close_pos"), y.get("range_atr")
    else:
        prev_type, prev_dir = pc.get("type"), pc.get("dir")
        prev_pos, prev_rng = pc.get("close_pos"), pc.get("range_atr")
    inventory = None
    if on and last is not None:
        hi, lo = _num(on.get("high")), _num(on.get("low"))
        if hi is not None and lo is not None and hi > lo:
            inventory = round((last - lo) / (hi - lo), 3)
    flip = (gamma or {}).get("flip")
    prev_ny = next((s for s in rows if s.get("key") == "ny" and s.get("prior_day")), None) or pny
    gap_atr = y.get("gap_atr")
    on_open, prev_close = _num(on.get("open")) if on else None, _num(pny.get("close"))
    if gap_atr is None and atr and on_open is not None and prev_close is not None:
        gap_atr = round((on_open - prev_close) / atr, 3)
    et = now.astimezone(ET)
    return {
        "day": day.isoformat(), "book": book, "at": et.strftime("%H:%M"),
        "late": et.time() > NY_OPEN, "half_day": half_day,
        "weekday": day.strftime("%a"), "source": "live",
        "prev_type": prev_type, "prev_dir": prev_dir,
        "prev_close_pos": prev_pos, "prev_range_atr": prev_rng,
        "prev_high": _num(prev_ny.get("high")), "prev_low": _num(prev_ny.get("low")),
        # Whether the night is finished (the box's own status): before the bell the
        # card is "the night so far", and the lean says so.
        "night_done": (on.get("status") == "complete") if on and on.get("status") else None,
        "overnight_atr": _span_atr(on, atr), "asia_atr": _span_atr(by.get("asia"), atr),
        "london_atr": _span_atr(by.get("london"), atr),
        "pre_atr": _span_atr(by.get("premkt"), atr),
        "inventory": inventory, "gap_atr": gap_atr,
        "fuel_pct": (fuel or {}).get("atr_pct"),
        "vix": vix, "vix_ratio": vix_ratio, "gamma": (gamma or {}).get("regime"),
        "flip_sigma": (round((last - flip) / em, 3)
                       if flip is not None and last is not None and em else None),
        "em": em, "prints": prints,
        # The yardstick the card was written with — the fourteen sessions before its
        # day, as the backfill's — so the label is measured by the same one.
        "atr": atr,
        "type": None, "dir": None, "inside": None, "range_atr": None, "close_pos": None,
    }


def row_day(s: dict[str, Any]) -> str | None:
    """The session date a ranges row belongs to, from the bar it started on. Pure."""
    ts = _num(s.get("start_ts"))
    return datetime.fromtimestamp(ts, ET).date().isoformat() if ts is not None else None


def label_from_live(card: dict[str, Any], sessions: list[dict[str, Any]], atr: float | None,
                    now: datetime) -> dict[str, Any]:
    """The card with its label, from the finished New York row of the card's own day
    and the high and low the card carries from the session before. The row is
    matched by the day it started on, so yesterday's card can still be labelled the
    next morning when a restart missed the close — the finished row stays the box's
    latest until the next session starts; a row without a date is taken when it is
    not a prior day's. The card's own ATR measures it, `atr` standing in for a card
    without one. The card as it was when there is no such row or nothing to measure
    by. Pure."""
    def its_day(s: dict[str, Any]) -> bool:
        d = row_day(s)
        return d == card.get("day") if d is not None else not s.get("prior_day")

    ny = next((s for s in sessions if isinstance(s, dict) and s.get("key") == "ny" and s.get("ok")
               and s.get("status") == "complete" and its_day(s)), None)
    yard = _num(card.get("atr")) or atr
    if ny is None or not yard:
        return card
    vals = [_num(ny.get(k)) for k in ("open", "high", "low", "close")]
    if any(v is None for v in vals):
        return card
    o, h, lo, c = (v for v in vals if v is not None)
    lab = label(o, h, lo, c, yard, _num(card.get("prev_high")), _num(card.get("prev_low")))
    # The session's own figures ride on the labelled card: tomorrow's card reads
    # yesterday from here once the ranges have moved on (card_from_live).
    return {**card, **lab, "ny": {"open": o, "high": h, "low": lo, "close": c},
            "labelled_at": now.astimezone(ET).strftime("%H:%M")}


# ------------------------------------------------------------------ the record


class SessionLog:
    """The record on disk (LOG_NAME under the cache): one line per day and book, the
    card as written before the bell until its label replaces it after the close.
    Loaded on start, so a restart at 09:27 neither writes the day twice nor loses
    the mark. Best effort on write, like the scanner's log: a full disk is a
    shorter record, not a broken collector."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.path.join(CACHE_DIR, LOG_NAME)
        self._lock = threading.Lock()
        self._cards: dict[tuple[str, str], dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with contextlib.suppress(OSError), open(self._path, encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError, TypeError, KeyError):
                    card = json.loads(line)
                    self._cards[(str(card["day"]), str(card["book"]))] = card

    def get(self, day: str, book: str) -> dict[str, Any] | None:
        with self._lock:
            return self._cards.get((day, book))

    def rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._cards[k] for k in sorted(self._cards)]

    def labelled(self, book: str, after: str | None = None) -> list[dict[str, Any]]:
        """The book's labelled full sessions, oldest first — those after `after`
        (a day) when the backfill already holds the earlier ones."""
        with self._lock:
            return [c for k, c in sorted(self._cards.items())
                    if k[1] == book and c.get("type") and not c.get("half_day")
                    and (after is None or k[0] > after)]

    def put(self, card: dict[str, Any]) -> None:
        """Keep `card` for its day and book, replacing the line it had, and rewrite
        the file whole: three lines a day, so a rewrite costs nothing and keeps one
        line per card."""
        with self._lock:
            self._cards[(str(card["day"]), str(card["book"]))] = card
            rows = [self._cards[k] for k in sorted(self._cards)]
            tmp = self._path + ".tmp"
            with contextlib.suppress(OSError):
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, separators=(",", ":")) + "\n")
                os.replace(tmp, self._path)
