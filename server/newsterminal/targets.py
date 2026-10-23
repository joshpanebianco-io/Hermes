"""
The first targets a trade may take — one rule for the plan and the options card.

MOVED OUT OF stockplan.py (2026-10-22) because a second reader arrived: the
options card now prices each contract at the first target so it can show the
option's own R, and a target computed by two functions is two targets. The
plan's `_name` facts and the scanner row's `targets` call the same function
on the same view of the row, so the plan, the card and the Analysis tab name
the same price.

THE RULE, unchanged: only levels that are FINAL — PDH, PDL, the previous
close, and PMH / PML once they lock — then today's expected move (the
same-day straddle's bounds) and a day's average range from the previous
close. Each must sit past the entry by `min_reach` and past the last price:
a target the stock has already traded through is not one.
"""

from __future__ import annotations

from typing import Any

#: A first target must sit at least this many ten-minute ATRs past the entry.
#: The Pine's stop is beyond the signal bar, about one ten-minute ATR from the
#: level, so 1.5 is a first target worth a stop and a half before the option's
#: spread is paid. Worked, from 2026-10-14's 05:18 facts: DELL short at PML
#: 552.66 with a 3.38 ten-minute ATR needs a target at or below 547.59 — PDL
#: 548.4 is 4.26 away, 1.26 ATRs, and is not one; GME long at PDH 27.53 with a
#: 0.12 ATR needs 27.71 or higher.
MIN_REACH_BARS = 1.5
#: The same floor from the daily ATR when the ten-minute one is missing — a
#: ten-minute ATR runs about a tenth of the daily on these names (GME 0.12 of
#: 0.99, NVDA 0.46 of 5.4), so 1.5 bar-ATRs is about 0.15 of a day.
MIN_REACH_DAY = 0.15


def min_reach(n: dict[str, Any]) -> float | None:
    """How far past the entry a first target must sit, in price. Pure."""
    b, d = n.get("atr_b"), n.get("atr_d")
    if isinstance(b, (int, float)) and b > 0:
        return MIN_REACH_BARS * float(b)
    if isinstance(d, (int, float)) and d > 0:
        return MIN_REACH_DAY * float(d)
    return None


def sign_of(n: dict[str, Any]) -> int:
    return 1 if n.get("side") == "long" else -1 if n.get("side") == "short" else 0


def entry_of(n: dict[str, Any]) -> float | None:
    e = n.get("entry")
    p = e.get("price") if isinstance(e, dict) else None
    return float(p) if isinstance(p, (int, float)) else None


def forming_levels(n: dict[str, Any]) -> list[float]:
    """The pre-market high and low while they are still forming. Pure."""
    if not n.get("pm_forming"):
        return []
    lv = n.get("levels") or {}
    return [float(v) for k in ("pmh", "pml") if isinstance(v := lv.get(k), (int, float))]


def target_candidates(n: dict[str, Any], keep: int = 3) -> list[dict[str, Any]]:
    """The first targets a plan may take, nearest first (module docstring). Pure."""
    sign, e = sign_of(n), entry_of(n)
    if not sign or e is None:
        return []
    lv = n.get("levels") or {}
    pool: list[tuple[str, Any]] = [("PDH", lv.get("pdh")), ("PDL", lv.get("pdl")),
                                   ("previous close", lv.get("pdc"))]
    if not n.get("pm_forming"):
        pool += [("PMH", lv.get("pmh")), ("PML", lv.get("pml"))]
    o = n.get("options") or {}
    if o.get("em_front_dte") == 0:
        pool.append(("today's expected-move " + ("high" if sign > 0 else "low"),
                     o.get("em_front_hi") if sign > 0 else o.get("em_front_lo")))
    pdc, atr = lv.get("pdc"), n.get("atr_d")
    if isinstance(pdc, (int, float)) and isinstance(atr, (int, float)) and atr > 0:
        pool.append(("a day's average range from the close", round(pdc + sign * atr, 2)))
    reach = min_reach(n) or 0.0
    last = n.get("last")
    ref = e if not isinstance(last, (int, float)) else (max(e, last) if sign > 0 else min(e, last))
    out: list[dict[str, Any]] = []
    for label, v in pool:
        if not isinstance(v, (int, float)):
            continue
        p = float(v)
        if sign * (p - e) < reach - 1e-9 or sign * (p - ref) <= 0:
            continue
        # A second candidate inside half a reach of one already kept says the
        # same thing twice (SPY's expected-move high 783.85, its ATR 783.87).
        if any(abs(c["price"] - p) < max(0.005, 0.5 * reach) for c in out):
            continue
        out.append({"label": label, "price": round(p, 2)})
    out.sort(key=lambda c: sign * (c["price"] - e))
    return out[:keep]


def view(row: dict[str, Any], em_front: dict[str, Any] | None) -> dict[str, Any]:
    """A scanner row as `target_candidates` reads it — the plan's `_name` shape,
    built from the row's own fields and the front straddle. Pure."""
    setup = row.get("setup") or {}
    score = row.get("score") or {}
    lv = row.get("levels") or {}
    entry = setup.get("entry") if isinstance(setup.get("entry"), dict) else None
    pm_done = lv.get("pm_done")
    return {
        "side": score.get("side") or setup.get("side"),
        "entry": None if entry is None else {"price": entry.get("price")},
        "levels": {k: lv.get(k) for k in ("pdh", "pdl", "pmh", "pml", "pdc")},
        "pm_forming": (not pm_done) if isinstance(pm_done, bool) else True,
        "atr_b": row.get("atr_b"),
        "atr_d": row.get("atr_d"),
        "last": row.get("last"),
        "options": None if not em_front else {
            "em_front_dte": em_front.get("dte"),
            "em_front_hi": em_front.get("hi"),
            "em_front_lo": em_front.get("lo"),
        },
    }
