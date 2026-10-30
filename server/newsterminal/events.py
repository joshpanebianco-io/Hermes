"""
Heavyweights and event risk — the catalysts the brief's bias was blind to.

WHY (owner, 2026-10-30: "make the analysis report generation and bias take
into consideration the macro like catalysts that happen to nq heavyweights
like mag7 etc? geopolitics?"). The digest already held the pieces: the index
constituents with weights and contributions, the earnings rows with actual
against estimate, and the wire with its desks and impact tiers. It held them
as three blocks in three places, and nothing voted. On the night Alphabet
printed $2.12 against $2.94 and fell twelve percent — 0.37 NQ points on its
own — the driver board's ceiling on conviction was exactly what it would
have been on a quiet Tuesday, and the model had to notice the join itself.

TWO BLOCKS, BOTH PURE, BOTH FROM THE SNAPSHOT.

  heavyweights   one row per big index weight (and any name whose move alone
                 is worth a tenth of a point): weight, move, index points,
                 the print if it just reported, and the one headline that
                 explains it. "What the index is being moved by, name by
                 name." Each row has an id the brief's call cites.
  event_risk     the HIGH-impact wire on the geopolitics, policy and energy
                 desks since the last cash close, grouped by story, each
                 tagged with the channels it reaches (oil, rates, semis…).

THEY VOTE (drivers.py). Heavyweight prints are a macro vote: the net index
points of the names that just reported, past a threshold, is a direction.
Event risk is a DAMPER, never a direction — a strike on Saudi oil is not a
short NQ, it is a reason to be one notch less sure of anything — and it
lowers the board's ceiling by one the way a macro-against-structure conflict
does.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .holidays import close_time, is_trading_day, prev_trading_day
from .sources.scanner import ALIASES, mentions

ET = ZoneInfo("America/New_York")

#: How many of the index's largest weights the table always carries.
TOP_WEIGHTS = 10
#: A name whose own contribution is at or beyond this many index points joins
#: the table whatever its weight — Fortinet at 0.55% down 20% is a story.
BIG_MOVE_POINTS = 0.10
#: A print counts as "just reported" for this long after it lands.
PRINT_WINDOW_H = 36
#: The headline that explains a name's move is looked for this far back.
HEADLINE_WINDOW_H = 24
#: The net index points of names that just reported, at or beyond this, votes.
PRINTS_VOTE_POINTS = 0.25
#: The wire desks an event comes from.
EVENT_DESKS = frozenset({"geo", "policy", "energy"})
#: How many events the block carries, newest first.
MAX_EVENTS = 8

#: Where in the ET day a report lands, by Nasdaq's timing field (ranges and
#: the calendar use the same table — report.py's `_earnings_moment` reads it
#: from here).
PRINT_HOUR = {"pre": (8, 0), "after": (16, 5)}

#: What an event reaches — the channel a desk reads it through. Checked
#: against the title and summary, several may match.
CHANNELS: list[tuple[str, re.Pattern[str]]] = [
    ("oil", re.compile(
        r"\b(oil|crude|opec|refiner|tanker|houthi|hormuz|saudi|iran|brent|wti|gasoline)\b", re.I)),
    ("rates", re.compile(
        r"\b(fed|fomc|treasur|yield|rate (?:hike|cut|decision)|boj|ecb|"
        r"bank of (?:england|japan)|inflation|cpi|powell)\b", re.I)),
    ("semis", re.compile(
        r"\b(chip|semiconductor|export control|tsmc|taiwan|nvidia|huawei|foundry)\b", re.I)),
    ("tariffs", re.compile(r"\b(tariff|trade war|sanction|export ban|trade deal|wto)\b", re.I)),
    ("war", re.compile(
        r"\b(war|missile|strike|attack|ceasefire|troops|invasion|drone|escalat)\w*\b", re.I)),
    ("dollar", re.compile(r"\b(dollar|yen|yuan|currency|intervention)\b", re.I)),
    ("fiscal", re.compile(
        r"\b(shutdown|budget|debt ceiling|stimulus|election|senate|congress|white house)\b", re.I)),
]

_WORD = re.compile(r"[A-Za-z]{4,}")
#: Words that two unrelated stories share all the time; they do not make a match.
_STOP = frozenset({"that", "with", "from", "after", "says", "said", "over", "into", "amid",
                   "about", "against", "before", "while", "their", "this", "will", "more",
                   "than", "warns", "plans", "costs", "claim", "could", "would", "under"})
#: Two titles sharing this many content words are one story.
_SHARED = 3


def print_moment(e: dict[str, Any]) -> datetime | None:
    """When a report row prints, in ET; None for a row with no readable date. Pure."""
    try:
        day = datetime.strptime(str(e.get("date")), "%Y-%m-%d")
    except ValueError:
        return None
    # AN UNTIMED PRINT IS AN AFTER-CLOSE PRINT. The feed often omits the time
    # of day; placed at noon, Alphabet's Wednesday-evening print fell out of
    # the heavyweight vote's window at midnight on Friday while its move was
    # still the thing (owner, 2026-10-30). The index names mostly report after
    # the close, and the cost of being wrong about a morning print is a vote
    # that lives eight hours longer than it should.
    hh, mm = PRINT_HOUR.get(str(e.get("when") or ""), PRINT_HOUR["after"])
    return day.replace(hour=hh, minute=mm, tzinfo=ET)


def last_close(now: datetime) -> datetime:
    """The most recent NYSE close at or before `now`: today's if the cash
    session is over, else the previous trading day's. Pure."""
    et = now.astimezone(ET)
    d = et.date()
    if is_trading_day(d) and et.time() >= close_time(d):
        return datetime.combine(d, close_time(d), tzinfo=ET)
    p = prev_trading_day(d)
    return datetime.combine(p, close_time(p), tzinfo=ET)


def _stamp(ts: float | None, now: datetime) -> str | None:
    if ts is None:
        return None
    at = datetime.fromtimestamp(ts, ET)
    today = at.date() == now.astimezone(ET).date()
    return at.strftime("%H:%M") if today else at.strftime("%a %H:%M")


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


# ------------------------------------------------------------------ heavyweights


def _just_reported(e: dict[str, Any], now: datetime) -> bool:
    if not e.get("eps_actual"):
        return False
    at = print_moment(e)
    return at is not None and now - timedelta(hours=PRINT_WINDOW_H) <= at <= now


def _headline_for(sym: str, wire: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The newest material headline that names the company, within the window."""
    names = ALIASES.get(sym, [])
    since = now.timestamp() - HEADLINE_WINDOW_H * 3600
    rank = {"high": 0, "medium": 1, "low": 2}
    best: dict[str, Any] | None = None
    for h in wire:
        if not isinstance(h, dict):
            continue
        ts = _num(h.get("ts"))
        if ts is None or ts < since:
            continue
        title = str(h.get("title") or "")
        if not mentions(title, sym, names):
            continue
        key = (rank.get(str(h.get("impact") or "low"), 2), -ts)
        if best is None or key < best["_key"]:
            best = {"_key": key, "title": title, "publisher": h.get("publisher"),
                    "time_et": _stamp(ts, now), "impact": h.get("impact")}
    if best is None:
        return None
    best.pop("_key")
    return best


def heavyweights(snap: dict[str, Any], book: str, now: datetime) -> list[dict[str, Any]]:
    """The names moving an equity book's index, one row each, heaviest first.
    Empty for a book that is not an index (GC) or has no constituents yet. Pure."""
    ix = ((snap.get("constituents") or {}).get("indices") or {}).get(book)
    if not isinstance(ix, dict):
        return []
    members = [m for m in ix.get("members") or [] if isinstance(m, dict) and m.get("symbol")]
    by_weight = sorted(members, key=lambda m: -(_num(m.get("weight")) or 0.0))
    chosen: list[dict[str, Any]] = list(by_weight[:TOP_WEIGHTS])
    seen = {m["symbol"] for m in chosen}
    for m in members:
        if m["symbol"] not in seen and abs(_num(m.get("contribution")) or 0.0) >= BIG_MOVE_POINTS:
            chosen.append(m)
            seen.add(m["symbol"])
    prints = {e["symbol"]: e for e in snap.get("earnings") or []
              if isinstance(e, dict) and e.get("symbol") and _just_reported(e, now)}
    wire = [h for h in snap.get("wire") or [] if isinstance(h, dict)]
    out: list[dict[str, Any]] = []
    for i, m in enumerate(chosen, start=1):
        sym = str(m["symbol"])
        p = prints.get(sym)
        out.append({
            "id": f"w{i}",
            "symbol": sym,
            "weight_pct": _num(m.get("weight")),
            "move_pct": _num(m.get("pct")),
            "index_points": _num(m.get("contribution")),
            "reported": ({
                "date": p.get("date"), "when": p.get("when"),
                "eps_actual": p.get("eps_actual"), "eps_forecast": p.get("eps_forecast"),
                "surprise_pct": p.get("surprise_pct"),
            } if p else None),
            "headline": _headline_for(sym, wire, now),
        })
    return out


def net_print_points(rows: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """The index points supplied by the names that just reported, and who they were. Pure."""
    hit = [r for r in rows if r.get("reported") and _num(r.get("index_points")) is not None]
    return round(sum(float(r["index_points"]) for r in hit), 3), [str(r["symbol"]) for r in hit]


# ------------------------------------------------------------------ event risk


def _channels(text: str) -> list[str]:
    return [name for name, pat in CHANNELS if pat.search(text)]


def _signature(title: str) -> frozenset[str]:
    """The title's content words, lower-cased and with a plural s dropped, so
    "Houthis strike Saudi oil facilities" and "Houthi forces claim six attacks on
    Saudi airports, oil facilities" share houthi, saudi and facilitie."""
    return frozenset(w.lower().rstrip("s") for w in _WORD.findall(title)
                     if w.lower() not in _STOP)


def event_risk(snap: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """The HIGH-impact geopolitics, policy and energy wire since the last cash
    close, one row per story, newest first, each with the channels it reaches.
    Pure.

    GROUPED BY STORY, not by publisher: the wire already folds the same
    article from several outlets into one item, but a strike reported by three
    desks under three headlines is still one event, and three rows for it
    would read as three. Two items that share three content words are one
    story — "Iran war" alone is not."""
    since = last_close(now).timestamp()
    items = [h for h in snap.get("wire") or []
             if isinstance(h, dict) and h.get("impact") == "high"
             and h.get("category") in EVENT_DESKS
             and (_num(h.get("ts")) or 0.0) >= since]
    items.sort(key=lambda h: -(_num(h.get("ts")) or 0.0))
    events: list[dict[str, Any]] = []
    sigs: list[tuple[frozenset[str], list[str]]] = []
    for h in items:
        title = str(h.get("title") or "")
        channels = _channels(f"{title} {h.get('summary') or ''}")
        sig = _signature(title)
        dup = any(len(sig & s) >= _SHARED for s, _ in sigs)
        if dup:
            continue
        sigs.append((sig, channels))
        events.append({
            "id": f"e{len(events) + 1}",
            "time_et": _stamp(_num(h.get("ts")), now),
            "desk": h.get("category"),
            "title": title,
            "publisher": h.get("publisher"),
            "channels": channels,
            "also": len(h.get("also") or []) if isinstance(h.get("also"), list) else 0,
        })
        if len(events) >= MAX_EVENTS:
            break
    return events
