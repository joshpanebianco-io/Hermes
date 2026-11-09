"""
The Dashboard: the session on one page, built from what the other tabs hold.

WHY (owner, 2026-11-09: "can we also have a dashboard section like the shown in some
of the screen shots", then "can we follow the layout a bit closer"). Nothing here is
new information. Macro, the Scanner and the calendar each answer part of "what is my
plan before the open"; this is that answer on one page, every figure a click from
where it came from.

NO NEW JUDGEMENT. The read is the tape count, the VIX band and breadth put into words
by a fixed rule, and the top setups are the scanner's own rank rather than a list
somebody picked.

Pure, so the words can be tested: give it the blocks, get the page.
"""

from __future__ import annotations

from datetime import date
from typing import Any

#: The size of move the read's "moving" count means, the same as the page's.
MOVING_PCT = 4.0
#: Advancers against decliners at or past this ratio, either way, is more than split.
BREADTH_RATIO = 1.5
#: Sectors, and themes, the plan names at most.
FOCUS = 3
TOP_ROWS = 15
REPORTS = 12

_TITLE = {"pre": "Pre-market", "rth": "Regular session", "post": "After hours",
          "closed": "Market closed"}
_ROW_KEYS = ("sym", "name", "sector", "last", "chg_pct", "ext_pct", "rvol", "trend", "levels",
             "broken", "setup", "catalyst", "stage", "spark")


def _d(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _list(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def lean_words(side: str | None) -> str:
    """The tape's lean, as the sentence opens. Pure."""
    return {"long": "Tape leans long", "short": "Tape leans short"}.get(side or "",
                                                                        "No lean from the tape")


def weather_words(vix: float | None, band: str | None, shape: str | None) -> tuple[str, bool]:
    """What the VIX says about size, and whether that is a caution. Pure."""
    if vix is None or band is None:
        return "the VIX has not been read yet", False
    v = f"VIX {vix:.1f}"
    if band == "stressed":
        curve = " and the curve is inverted" if shape == "backwardation" else ""
        return f"{v} is stressed{curve}: cut size or sit out", True
    if band == "elevated":
        return f"{v} is elevated: moves extend then whip back, so size down", True
    if band == "grind":
        return f"{v} is low: small ranges, so a breakout needs proof", False
    return f"{v} is normal", False


def breadth_word(adv: int, dec: int) -> str:
    """Broad, weak or split. Pure."""
    if adv >= BREADTH_RATIO * max(dec, 1):
        return "broad"
    if dec >= BREADTH_RATIO * max(adv, 1):
        return "weak"
    return "split"


def _beat_spy(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """The funds ahead of SPY on the day, best first."""
    out = [r for r in rows
           if r.get("key") not in ("SPY", "RSP") and (_num(r.get("rs_day")) or 0.0) > 0.0]
    out.sort(key=lambda r: -float(r["rs_day"]))
    return [{"key": r["key"], "label": r.get("label"), "pct": r.get("day_pct"), "rs": r["rs_day"]}
            for r in out[:n]]


def _leaders_clause(focus: list[dict[str, Any]], themes: list[dict[str, Any]], session: str,
                    day: date) -> str:
    """"Technology and Bitcoin Miners led Friday." Pure."""
    when = day.strftime("%A")
    names = [x["label"] for x in (focus[:1] + themes[:1])]
    if not names:
        return f"Nothing beat SPY {'today' if session in ('rth', 'post') else when}"
    who = " and ".join(names)
    if session == "rth":
        return f"{who} {'is' if len(names) == 1 else 'are'} leading today"
    return f"{who} led {'today' if session == 'post' else when}"


def read_lines(regime: dict[str, Any], focus: list[dict[str, Any]], themes: list[dict[str, Any]],
               breadth: dict[str, Any], session: str, day: date) -> list[str]:
    """The card's two sentences. Pure."""
    conv = _d(regime.get("conviction"))
    side = conv.get("bias") if conv else regime.get("bias")
    vix = _d(regime.get("vix"))
    weather, caution = weather_words(_num(vix.get("last")), regime.get("band"), vix.get("shape"))
    first = f"{lean_words(side)}{', but' if caution and side else ';'} {weather}."
    second = f"{_leaders_clause(focus, themes, session, day)}."
    adv, dec = breadth.get("advancers"), breadth.get("decliners")
    if isinstance(adv, int) and isinstance(dec, int):
        word = breadth_word(adv, dec)
        second = f"{second[:-1]}; breadth is {word} ({adv:,} up, {dec:,} down)."
        against = (side == "long" and word == "weak") or (side == "short" and word == "broad")
        if word == "split" or against:
            second += " Stay selective."
    return [first, second]


def _slim(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in _ROW_KEYS}
    s = _d(r.get("score"))
    out["score"] = {"total": s.get("total"), "side": s.get("side")}
    return out


def _reports(earnings: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    """Who reports on the session this page is for, before the open first, biggest first."""
    rows = [e for e in earnings if e.get("date") == day and e.get("symbol")]
    order = {"pre": 0, "after": 1}
    rows.sort(key=lambda e: (order.get(str(e.get("when")), 2), -(_num(e.get("market_cap")) or 0.0)))
    return [{"sym": e["symbol"], "when": e.get("when")} for e in rows[:REPORTS]]


def _rotation(sectors: list[dict[str, Any]], leaders: dict[str, Any]) -> list[dict[str, Any]]:
    """The eleven, best first, each with the stocks pushing it."""
    rows = [s for s in sectors if s.get("key") not in ("SPY", "RSP")]
    def rank(s: dict[str, Any]) -> float:
        day = _num(s.get("day_pct"))
        return -day if day is not None else 1e9

    rows.sort(key=rank)
    return [{"key": s.get("key"), "label": s.get("label"), "day_pct": s.get("day_pct"),
             "rs_day": s.get("rs_day"),
             "leaders": [x.get("sym") for x in _list(_d(leaders.get(str(s.get("key")))).get("up"))]}
            for s in rows]


def build(scan: dict[str, Any], snap: dict[str, Any], brk: dict[str, Any], d23: dict[str, Any],
          stories: list[dict[str, Any]], *, session_day: date) -> dict[str, Any]:
    """The page. `session_day` is the session the cards' moves are about
    (universe.cards_day), which before the open is the last one."""
    rows = [r for r in _list(scan.get("rows")) if r.get("ok")]
    by_sym = {r["sym"]: r for r in rows}
    regime = _d(scan.get("regime"))
    session = str(scan.get("session") or "closed")
    trading_day = str(scan.get("trading_day") or "")
    sectors, themes = _list(snap.get("sectors")), _list(snap.get("themes"))
    wide = _d(snap.get("breadth_all"))
    leaders = _d(wide.get("leaders"))
    focus = _beat_spy(sectors, FOCUS)
    hot = _beat_spy(themes, FOCUS)

    scored = [r for r in rows if (_d(r.get("score")).get("total") or 0) > 0]
    moving = sum(1 for r in rows if abs(_num(r.get("chg_pct")) or 0.0) >= MOVING_PCT)
    conv = _d(regime.get("conviction"))
    stats, chips = _d(brk.get("stats")), _d(d23.get("chips"))
    status = _d(_d(snap.get("status")).get("stock_news"))

    return {
        "ok": bool(rows),
        "session": session,
        "trading_day": trading_day,
        "read": {
            "title": _TITLE.get(session, "Market closed"),
            "lines": read_lines(regime, focus, hot, wide, session, session_day),
            "foot": f"{len(scored)} active setups · {moving} names moving {MOVING_PCT:.0f}%+",
            "reports": _reports(_list(snap.get("earnings")), trading_day),
        },
        "plan": {
            "bias": {"side": conv.get("bias") if conv else regime.get("bias"),
                     "score": conv.get("score"), "grade": conv.get("grade"),
                     "live": conv.get("live"), "total": conv.get("total"),
                     "cap": conv.get("max_conviction")},
            "focus": focus,
            "themes": hot,
            "setups": [
                {"key": "day23", "word": "Day 2/3 continuation", "view": "day23", "chip": None,
                 "n": int(chips.get("day2") or 0) + int(chips.get("day3") or 0)},
                {"key": "pdh", "word": "Breakouts over prior-day high", "view": "breakouts",
                 "chip": "through", "n": stats.get("pdh")},
                {"key": "pdl", "word": "Breakdowns under prior-day low", "view": "breakouts",
                 "chip": "through", "n": stats.get("pdl")},
            ],
            "event": regime.get("event"),
        },
        "breadth": {k: wide.get(k) for k in ("basis", "floor", "names", "advancers", "decliners",
                                             "buckets")} if wide else None,
        "top": [_slim(r) for r in scored[:TOP_ROWS]],
        "list": [_slim(by_sym[s]) for s in scan.get("pinned") or [] if s in by_sym],
        "adds": [_slim(r) for r in rows if r.get("promoted")],
        "stories": stories,
        "news_live": bool(status.get("ok")),
        "rotation": _rotation(sectors, leaders),
    }
