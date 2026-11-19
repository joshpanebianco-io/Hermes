"""
The bias's yardsticks: how big a driver's move is for that driver, and how it has
moved with each book lately.

WHY (owner, 2026-11-19: "weight everything as best and accurate as we can based on
logic then gather data to test"). Three things the reads could not do with a fixed
cut-off each and a vote that was all or nothing:

  * SIZE. The 10-year up 4bp and up 15bp cast one vote each, and the VIX's cut-off
    was 1.5% at a VIX of 12 and at a VIX of 25. A move is now measured in its own
    USUAL DAY (the mean absolute daily change over the last twenty sessions): it
    starts to count at half a usual day and counts in full at one and a half.

  * THE ECHO. On a day the Nasdaq falls 1% the VIX rises: that is the same fact
    told twice. A co-mover (the VIX and credit for an index, silver for gold, gold
    and copper for silver, the products, copper and credit for crude) votes on what
    the book's own move does NOT explain: its move less its beta times the book's,
    measured in the usual size of that remainder.

  * WHETHER IT IS DRIVING. "Yields up is a headwind" holds while yields and the
    index have been moving against each other; in a growth tape they rise
    together, and then a rise is no headwind. A macro driver (the 10-year, the
    note future, the dollar) votes only while its correlation with the book over
    the last sixty sessions has the sign its vote assumes, by at least GATE.

Every one of these is arithmetic on the context feed's daily closes (sources/quotes.py
`hist`), which carry their dates so two markets' days line up across holidays.
With too little history a read falls back to a stated usual day and beta, says so,
and votes as it would have.

PURE. Nothing here does I/O; the driver board (drivers.py) and the tape
(marketctx.py) each build one `Stats` per read.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

#: Sessions a usual day is read over, and the fewest it is read from.
USUAL_N = 20
USUAL_MIN = 10
#: Sessions a beta and a correlation are read over, and the fewest they are read from.
LINK_N = 60
LINK_MIN = 20
#: A move under START usual days is no read; at FULL it counts in full; linear between.
START = 0.5
FULL = 1.5
#: A macro driver votes only while its correlation with the book has the sign its vote
#: assumes by at least this. Sixty sessions put a correlation's noise near 0.13.
GATE = 0.2

#: Inputs whose day change is said in basis points (a yield), not percent.
BP_KEYS = frozenset({"US10Y"})
#: The board's book -> its key in the context feed (silver and crude ride under their names).
BOOK_KEY = {"NQ": "NQ", "ES": "ES", "GC": "GC", "SIL": "SILVER", "CL": "WTI"}
#: A synthetic series: the two products averaged, crude's "pulled through" read.
PRODUCTS = ("RBOB", "HEATOIL")

#: A usual day to fall back on with too little history: about what each has been in a
#: normal year. bp for the 10-year, percent for the rest.
FALLBACK_USUAL: dict[str, float] = {
    "US10Y": 6.0, "ZN": 0.35, "DXY": 0.4, "VIX": 6.0, "HYG": 0.25, "SILVER": 2.0,
    "GC": 1.0, "COPPER": 1.3, "PRODUCTS": 1.8, "NQ": 1.2, "ES": 0.9, "WTI": 2.0,
}
#: A co-mover's beta to a book to fall back on: the VIX moves about four times the S&P
#: the other way, silver about one and a third times gold.
PRIOR_BETA: dict[tuple[str, str], float] = {
    ("VIX", "NQ"): -3.5, ("VIX", "ES"): -4.5,
    ("HYG", "NQ"): 0.15, ("HYG", "ES"): 0.2, ("HYG", "WTI"): 0.05,
    ("SILVER", "GC"): 1.3, ("GC", "SILVER"): 0.45, ("COPPER", "SILVER"): 0.4,
    ("COPPER", "WTI"): 0.3, ("PRODUCTS", "WTI"): 0.8,
}


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(float(v)):
        return None
    return float(v)


def changes(row: dict[str, Any], today: date) -> dict[str, float]:
    """A context row's completed daily changes by date: basis points for a yield,
    percent for the rest. A bar dated today or later is still forming and is left out.
    Pure."""
    hist = row.get("hist") or {}
    days, closes = hist.get("days") or [], hist.get("closes") or []
    bp = row.get("key") in BP_KEYS
    out: dict[str, float] = {}
    prev: float | None = None
    for d, raw in zip(days, closes, strict=False):
        c = _num(raw)
        if c is None or str(d) >= today.isoformat():
            continue
        if prev is not None and prev:
            out[str(d)] = (c - prev) * 100.0 if bp else (c / prev - 1.0) * 100.0
        prev = c
    return out


def _mean_abs(xs: list[float]) -> float | None:
    return sum(abs(x) for x in xs) / len(xs) if xs else None


class Stats:
    """The usual day of every input on the context feed, and the link (beta, correlation,
    the usual size of the remainder) between any two. Built once per read."""

    def __init__(self, context: list[dict[str, Any]] | None, today: date) -> None:
        self._chg: dict[str, dict[str, float]] = {}
        for row in context or []:
            if isinstance(row, dict) and row.get("key"):
                self._chg[str(row["key"])] = changes(row, today)
        legs = [self._chg.get(k) or {} for k in PRODUCTS]
        common = set(legs[0]).intersection(*legs[1:]) if legs and legs[0] else set()
        if common:
            self._chg["PRODUCTS"] = {d: sum(leg[d] for leg in legs) / len(legs)
                                     for d in common}
        self._links: dict[tuple[str, str], dict[str, Any] | None] = {}

    def usual(self, key: str) -> tuple[float, bool]:
        """(the usual day, whether it is measured). A stated fallback when it is not."""
        xs = [v for _, v in sorted((self._chg.get(key) or {}).items())][-USUAL_N:]
        u = _mean_abs(xs) if len(xs) >= USUAL_MIN else None
        if u:
            return u, True
        return FALLBACK_USUAL.get(key, 1.0), False

    def link(self, x: str, book: str) -> dict[str, Any] | None:
        """How `x` has moved with `book`: beta, correlation and the usual size of what
        the book's move leaves unexplained, over their last LINK_N common days. None
        with fewer than LINK_MIN."""
        if (x, book) in self._links:
            return self._links[(x, book)]
        a, b = self._chg.get(x) or {}, self._chg.get(book) or {}
        days = sorted(set(a) & set(b))[-LINK_N:]
        out: dict[str, Any] | None = None
        if len(days) >= LINK_MIN:
            xs, ys = [a[d] for d in days], [b[d] for d in days]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxy = sum((p - mx) * (q - my) for p, q in zip(xs, ys, strict=True))
            sxx = sum((p - mx) ** 2 for p in xs)
            syy = sum((q - my) ** 2 for q in ys)
            if syy > 0 and sxx > 0:
                beta = sxy / syy
                corr = sxy / math.sqrt(sxx * syy)
                res = [p - beta * q for p, q in zip(xs, ys, strict=True)][-USUAL_N:]
                out = {"beta": beta, "corr": corr, "usual_res": _mean_abs(res) or None,
                       "n": len(days)}
        self._links[(x, book)] = out
        return out


def multiple(move: float, usual: float) -> float:
    """A move in its usual days. Pure."""
    return abs(move) / usual if usual > 0 else 0.0


def strength(mult: float) -> float:
    """How much of a full vote a move of `mult` usual days carries: none under START,
    all of it from FULL, a straight line between. Pure."""
    return max(0.0, min(1.0, (mult - START) / (FULL - START)))


def residual(st: Stats, x: str, x_move: float, book: str,
             book_move: float | None) -> dict[str, Any]:
    """What `x`'s move is beyond what the book's own move explains. Pure.

    {"res", "usual", "beta", "expected", "measured"}: with no book move it is x's raw
    move against its own usual day; with no measured link, the stated prior beta and
    x's usual day."""
    if book_move is None:
        u, measured = st.usual(x)
        return {"res": x_move, "usual": u, "beta": None, "expected": None,
                "measured": measured}
    ln = st.link(x, book)
    if ln is not None and ln.get("usual_res"):
        beta, usual, measured = float(ln["beta"]), float(ln["usual_res"]), True
    else:
        beta = PRIOR_BETA.get((x, book), 0.0)
        usual, _ = st.usual(x)
        measured = False
    expected = beta * book_move
    return {"res": x_move - expected, "usual": usual, "beta": beta, "expected": expected,
            "measured": measured}


def driving(st: Stats, x: str, book: str, sign: int) -> tuple[bool, float | None]:
    """(whether `x` votes on `book`, the correlation it was judged on). `sign` is the
    correlation the vote assumes: -1 for a driver whose rise is short the book (the
    10-year, the dollar), +1 for one whose rise is long (the note future). Unmeasured
    is taken as driving: the read votes as it always did. Pure."""
    ln = st.link(x, book)
    if ln is None:
        return True, None
    corr = float(ln["corr"])
    return corr * sign >= GATE, corr


def size_words(mult: float, s: float) -> str:
    """"1.2× its usual day, counts 70%" — the size a note carries. Pure."""
    return f"{mult:.1f}× its usual day, counts {round(s * 100)}%"


# ---- the three kinds of read, as (vote, strength, note): the board and the tape each
# wrap them in their own row ---------------------------------------------------------


def _signed(x: float, dp: int, unit: str = "") -> str:
    return f"{x:+.{dp}f}{unit}"


def _other(side: str) -> str:
    return "short" if side == "long" else "long"


def sized(move: float, usual: float, measured: bool, up: str, notes: tuple[str, str],
          what: str = "the move") -> tuple[str, float | None, str]:
    """A driver voted by its size in its usual days: `up` is the side a rise votes for,
    `notes` the reason for a rise and for a fall. Pure."""
    mult = multiple(move, usual)
    s = strength(mult)
    basis = "" if measured else " (no history yet: a usual day is taken as stated)"
    if s <= 0:
        return "neutral", None, (f"{what} is {mult:.1f}× its usual day, under {START}× "
                                 f"— no read{basis}")
    side = up if move > 0 else _other(up)
    return side, s, f"{notes[0] if move > 0 else notes[1]} — {size_words(mult, s)}{basis}"


def surprise(st: Stats, x: str, x_move: float, book: str, book_move: float | None,
             book_name: str, up: str, notes: tuple[str, str]) -> tuple[str, float | None, str]:
    """A co-mover voted on what the book's own move leaves unexplained: `up` is the side
    a rise beyond the echo votes for. Pure."""
    r = residual(st, x, x_move, book, book_move)
    res, usual = float(r["res"]), float(r["usual"])
    mult = multiple(res, usual)
    s = strength(mult)
    echo = _echo(r, book_name, book_move)
    if s <= 0:
        return "neutral", None, (f"{echo}; the {_signed(res, 2, '%')} beyond that is "
                                 f"{mult:.1f}× its usual, under {START}× — the book's own "
                                 "echo, no read")
    side = up if res > 0 else _other(up)
    return side, s, (f"{notes[0] if res > 0 else notes[1]}: {echo}, {_signed(res, 2, '%')} "
                     f"beyond it — {size_words(mult, s)}")


def context_note(st: Stats, x: str, x_move: float, book: str, book_move: float | None,
                 book_name: str, notes: tuple[str, str]) -> str:
    """What `surprise` would say of a co-mover that is never a side, without the vote's
    size: the VIX since the evening of 2026-11-19 (bias.BOARD_FAMILY). `notes` are the
    words for a rise and a fall beyond the echo. Pure."""
    r = residual(st, x, x_move, book, book_move)
    res, usual = float(r["res"]), float(r["usual"])
    mult = multiple(res, usual)
    echo = _echo(r, book_name, book_move)
    if strength(mult) <= 0:
        return f"{echo}; the {_signed(res, 2, '%')} beyond that is the book's own echo"
    return (f"{notes[0] if res > 0 else notes[1]}: {echo}, {_signed(res, 2, '%')} beyond it, "
            f"{mult:.1f}× its usual day")


def _echo(r: dict[str, Any], book_name: str, book_move: float | None) -> str:
    """"NQ's -1.00% would put it at +3.50%": what the book's own move explains."""
    if r["expected"] is None:
        return f"no {book_name} move to read it against"
    return (f"{book_name}'s {_signed(book_move or 0.0, 2, '%')} would put it at "
            f"{_signed(float(r['expected']), 2, '%')}"
            + ("" if r["measured"] else " (a stated beta: no history yet)"))


def gate_note(st: Stats, x: str, book: str, sign: int, book_name: str,
              what: str) -> str | None:
    """Why a macro driver is not voting on this book now, or None when it is. Pure."""
    ok, corr = driving(st, x, book, sign)
    if ok or corr is None:
        return None
    lately = "against" if sign < 0 else "with"
    return (f"{what} and {book_name} have not been moving {lately} each other lately "
            f"(correlation {corr:+.2f} over the last {LINK_N} sessions; it votes from "
            f"{'-' if sign < 0 else '+'}{GATE}) — not a driver now")


#: Net breadth ((up - down) / reporting) at which a breadth read counts in full: 80/20.
BREADTH_FULL = 0.6


def breadth_strength(up: int, down: int) -> float:
    """How much of a full vote a breadth read carries: its net breadth over
    BREADTH_FULL, capped at one. Pure."""
    n = up + down
    return min(1.0, abs(up - down) / n / BREADTH_FULL) if n else 0.0
