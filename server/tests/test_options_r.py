"""The options maths added 2026-10-22: the report's expiry kept, the term
structure, the earnings number, the realised moves, the contract at the target
with its R, and the structure pick."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from newsterminal import optcalc
from newsterminal.scan import DayBar

REF = date(2026, 10, 22)  # Thursday
NOW = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
SPOT = 100.0


def _opt(exp: date, right: str, strike: float, mid: float, iv: float, delta: float,
         oi: float = 500.0, vol: float = 50.0) -> optcalc.Opt:
    return optcalc.Opt(symbol=f"X{exp:%y%m%d}{right}{int(strike * 1000):08d}", expiry=exp,
                       right=right, strike=strike, bid=mid - 0.05, ask=mid + 0.05, iv=iv,
                       delta=delta if right == "C" else -delta, theta=-0.05, oi=oi, volume=vol,
                       gamma=0.02)


def _chain(expiries: list[date], straddle_pct: dict[date, float] | None = None) -> optcalc.Chain:
    """Strikes 80..120 every 5, delta falling with distance; the ATM straddle's
    mid per expiry set by `straddle_pct` (half each leg)."""
    opts: dict[date, list[optcalc.Opt]] = {}
    for e in expiries:
        half = (straddle_pct or {}).get(e, 4.0) / 2.0
        rows = []
        for k in range(80, 125, 5):
            dist = (k - SPOT) / SPOT
            cd = max(0.05, min(0.95, 0.5 - dist * 4))
            c_mid = max(0.1, half + (SPOT - k) * 0.6) if k <= SPOT else max(0.1, half - dist * 40)
            p_mid = max(0.1, half + (k - SPOT) * 0.6) if k >= SPOT else max(0.1, half + dist * 40)
            rows.append(_opt(e, "C", float(k), c_mid, 0.40 + half / 100, cd))
            rows.append(_opt(e, "P", float(k), p_mid, 0.42 + half / 100, 1 - cd))
        opts[e] = rows
    return optcalc.Chain("X", SPOT, 40.0, NOW, expiries, opts)


def _doc(expiries: list[date]) -> dict[str, Any]:
    rows = []
    for e in expiries:
        for k in (95.0, 100.0, 105.0):
            for right in "CP":
                rows.append({"option": f"X{e:%y%m%d}{right}{int(k * 1000):08d}", "bid": 1.0,
                             "ask": 1.2, "iv": 0.4, "delta": 0.5, "theta": -0.05,
                             "open_interest": 10, "volume": 5, "gamma": 0.02})
    return {"data": {"current_price": SPOT, "iv30": 40.0, "options": rows},
            "timestamp": "2026-10-22T14:45:00"}


def test_parse_chain_keeps_the_reports_expiry_beyond_the_nearest_four() -> None:
    exps = [REF + timedelta(days=7 * i) for i in range(8)]
    plain = optcalc.parse_chain(_doc(exps), "X", REF)
    assert sorted(plain.opts) == exps[:4]
    kept = optcalc.parse_chain(_doc(exps), "X", REF, keep_after=exps[6] - timedelta(days=2))
    assert sorted(kept.opts) == [*exps[:4], exps[6]]
    # The flow's window stays the nearest four.
    assert optcalc.near_expiries(kept) == exps[:4]


def test_term_structure_is_atm_iv_per_expiry() -> None:
    e1, e2 = REF + timedelta(days=1), REF + timedelta(days=8)
    c = _chain([e1, e2], {e1: 6.0, e2: 4.0})
    term = optcalc.term_structure(c, SPOT, REF)
    assert [t["expiry"] for t in term] == [e1.isoformat(), e2.isoformat()]
    assert term[0]["dte"] == 1 and term[0]["iv"] > term[1]["iv"]


def test_earnings_move_covers_the_reaction_day_and_nets_the_days_before() -> None:
    e1, e2, e3 = REF + timedelta(days=1), REF + timedelta(days=8), REF + timedelta(days=15)
    c = _chain([e1, e2, e3], {e1: 2.0, e2: 3.0, e3: 8.0})
    # A report on e2 after the close reacts the next day: e3 covers it.
    m = optcalc.earnings_move(c, SPOT, e2, "after", REF)
    assert m is not None
    assert m["expiry"] == e3.isoformat() and m["pct"] == pytest.approx(8.0, abs=0.01)
    assert m["before_expiry"] == e2.isoformat() and m["before_pct"] == pytest.approx(3.0, abs=0.01)
    assert m["clean_pct"] == pytest.approx((8.0**2 - 3.0**2) ** 0.5, abs=0.02)
    # Pre-market on e2: e2 itself covers it.
    pre = optcalc.earnings_move(c, SPOT, e2, "pre", REF)
    assert pre is not None and pre["expiry"] == e2.isoformat()
    # Beyond the kept expiries: nothing.
    assert optcalc.earnings_move(c, SPOT, e3 + timedelta(days=30), "after", REF) is None


def test_realised_earnings_moves_pick_the_reaction_day_by_volume() -> None:
    days = []
    d, px = date(2026, 9, 1), 100.0
    for _ in range(30):
        if d.weekday() < 5:
            vol = 1_000.0
            if d == date(2026, 9, 16):  # the day after a 15 Sep AMC report
                px, vol = 108.0, 9_000.0
            days.append(DayBar(d, px, px + 1, px - 1, px, vol))
        d += timedelta(days=1)
    out = optcalc.realised_earnings_moves(days, [date(2026, 9, 15), date(2026, 12, 1)])
    assert len(out) == 1
    assert out[0]["date"] == "2026-09-15" and out[0]["reaction"] == "2026-09-16"
    assert out[0]["pct"] == pytest.approx(8.0, abs=0.01)
    assert optcalc.realised_earnings_moves([], [date(2026, 9, 15)]) == []


def _row(side: str = "long") -> dict[str, Any]:
    return {"sym": "X", "last": 100.0, "atr_b": 0.5, "atr_d": 3.0,
            "setup": {"side": side, "state": "retest", "level": "PDH",
                      "entry": {"kind": "PDH", "price": 100.0, "dist_atr": 0.0}},
            "score": {"side": side, "total": 50, "parts": []},
            "levels": {"pdh": 100.0, "pdl": 95.0, "pdc": 98.0, "pmh": 101.0, "pml": 97.0,
                       "pm_done": True}, "signals": [], "earnings": None}


def test_contracts_carry_the_value_at_the_first_target_and_an_r() -> None:
    e1 = REF + timedelta(days=8)
    c = _chain([e1], {e1: 4.0})
    ctx = optcalc.options_ctx(c, _row("long"), [100.0] * 25, [], REF, NOW, 5.0)
    assert ctx["ok"]
    # The first target by the plan's rule: PMH 101 (locked) is 1.0 past the
    # entry — more than 1.5 × 0.5 — and a day's range from the close, 98 + 3,
    # lands on the same price and folds into it.
    assert ctx["targets"][0] == {"label": "PMH", "price": 101.0}
    lg = next(x for x in ctx["contracts"] if x["kind"] == "long")
    assert lg["target_price"] == 101.0 and lg["target_basis"] == "delta and gamma"
    assert lg["target_mid"] > lg["entry_mid"]
    assert lg["reward_per_contract"] > 0 and lg["r_multiple"] is not None
    assert lg["r_multiple"] == pytest.approx(lg["reward_per_contract"] / lg["risk_per_contract"],
                                             abs=0.01)
    assert ctx["structure"]["kind"] in ("long", "spread")
    assert ctx["structure"]["by"] in ("r", "premium")
    assert [t["expiry"] for t in ctx["term"]] == [e1.isoformat()]
    assert ctx["earnings_move"] is None


def test_structure_pick_prefers_the_better_r_else_premium() -> None:
    cs = [{"key": "weekly", "kind": "long", "r_multiple": 1.2},
          {"key": "weekly", "kind": "spread", "r_multiple": 0.8}]
    assert optcalc.structure_pick(cs, "weekly", "rich") == {
        "kind": "long", "by": "r", "long_r": 1.2, "spread_r": 0.8}
    tie = [{"key": "weekly", "kind": "long", "r_multiple": 1.0},
           {"key": "weekly", "kind": "spread", "r_multiple": 1.03}]
    assert optcalc.structure_pick(tie, "weekly", "rich")["kind"] == "spread"
    assert optcalc.structure_pick(tie, "weekly", "cheap")["kind"] == "long"
    assert optcalc.structure_pick([], "weekly", None)["by"] == "premium"


def test_flow_reads_oi_change_and_unusual_volume() -> None:
    e1 = REF + timedelta(days=1)
    c = _chain([e1])
    opts = c.opts[e1]
    prev = {"day": "2026-10-21", "call_oi": 4_000.0, "put_oi": 6_000.0,
            "by": {opts[0].symbol: 400.0}}
    f = optcalc.options_flow(c, prev, [100.0] * 20)
    assert f is not None
    assert f["oi_chg_calls"] == int(sum(o.oi for o in opts if o.right == "C") - 4_000)
    assert f["oi_chg_puts"] == int(sum(o.oi for o in opts if o.right == "P") - 6_000)
    assert f["oi_prev_day"] == "2026-10-21"
    assert f["vol_avg20"] == 100
    assert f["vol_x"] == pytest.approx((f["call_vol"] + f["put_vol"]) / 100, abs=0.01)
    assert f["unusual"] is True
    top = f["top"][0]
    assert "oi_chg" in top
    bare = optcalc.options_flow(c)
    assert bare is not None and bare["oi_chg_calls"] is None and bare["unusual"] is False
