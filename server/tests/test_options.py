"""The stocks desk's options layer: Cboe chains → OptionsCtx (optcalc, sources/options)."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from newsterminal import optcalc, scan, scanscore
from newsterminal.http import FetchResult
from newsterminal.optcalc import ET, Chain, Opt
from newsterminal.sources import options as opt_src

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
TUE = date(2026, 10, 13)


def et(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _doc(name: str) -> Any:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _opt(right: str, strike: float, bid: float, ask: float, delta: float | None,
         iv: float | None = 0.2, exp: date = TUE, oi: float = 100.0, theta: float | None = -0.1,
         ) -> Opt:
    return Opt(symbol=f"X{exp:%y%m%d}{right}{int(strike * 1000):08d}", expiry=exp, right=right,
               strike=strike, bid=bid, ask=ask, iv=iv, delta=delta, theta=theta, oi=oi,
               volume=10.0)


# --- parsing ------------------------------------------------------------------------------


def test_occ_symbols_parse_and_junk_does_not() -> None:
    assert optcalc.parse_occ("SPY261013C00778000") == ("SPY", date(2026, 10, 13), "C", 778.0)
    assert optcalc.parse_occ("BRK.B261016P00450500") == ("BRK.B", date(2026, 10, 16), "P", 450.5)
    assert optcalc.parse_occ("SPY26101C778") is None
    assert optcalc.parse_occ("SPY261399C00778000") is None  # month 13


def test_cboe_timestamp_is_utc() -> None:
    assert optcalc.parse_asof("2026-10-13 12:07:43") == datetime(2026, 10, 13, 12, 7, 43,
                                                                  tzinfo=UTC)
    assert optcalc.parse_asof(None) is None and optcalc.parse_asof("nope") is None


def test_real_chain_drops_expired_and_keeps_the_band() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    assert c.spot == pytest.approx(777.68) and c.iv30 == pytest.approx(12.069)
    assert c.asof is not None and c.asof.tzinfo is not None
    # 261012 — yesterday's 0DTE — is still in the feed and must not survive.
    assert date(2026, 10, 12) not in c.expiries
    assert c.expiries[0] == TUE and len(c.opts) <= optcalc.KEEP_EXPIRIES
    for opts in c.opts.values():
        assert all(abs(o.strike / 777.68 - 1) <= optcalc.STRIKE_BAND for o in opts)


def test_unreadable_document_is_an_empty_chain() -> None:
    c = optcalc.parse_chain({"nope": 1}, "SPY", TUE)
    assert c.spot is None and c.expiries == [] and c.opts == {}


# --- expiries -----------------------------------------------------------------------------


def test_sessions_left_skips_weekends_and_holidays() -> None:
    assert optcalc.sessions_left(TUE, date(2026, 10, 14)) == 1
    assert optcalc.sessions_left(TUE, date(2026, 10, 16)) == 3
    assert optcalc.sessions_left(date(2026, 10, 16), date(2026, 10, 19)) == 1  # over a weekend
    assert optcalc.sessions_left(date(2026, 11, 25), date(2026, 11, 27)) == 1  # Thanksgiving


SPY_EXP = [TUE, date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16)]
AAPL_EXP = [date(2026, 10, 14), date(2026, 10, 16), date(2026, 10, 19)]


@pytest.mark.parametrize("sym,exps,minute,front,weekly", [
    # SPY before 15:00: today's 0DTE is the front; Thursday has two sessions to run.
    ("SPY", SPY_EXP, 8 * 60, TUE, date(2026, 10, 15)),
    ("SPY", SPY_EXP, 14 * 60 + 59, TUE, date(2026, 10, 15)),
    # From 15:00 the 0DTE is too close to the bell; the next one is the front.
    ("SPY", SPY_EXP, 15 * 60, date(2026, 10, 14), date(2026, 10, 15)),
    # A single name's front is simply the nearest; its weekly needs two sessions.
    ("AAPL", AAPL_EXP, 10 * 60, date(2026, 10, 14), date(2026, 10, 16)),
])
def test_front_and_weekly(sym: str, exps: list[date], minute: int, front: date,
                          weekly: date) -> None:
    p = optcalc.pick_expiries(sym, exps, TUE, minute)
    assert (p["front"], p["weekly"]) == (front, weekly)


def test_half_day_moves_the_0dte_cutoff_to_noon() -> None:
    fri = date(2026, 11, 27)  # the day after Thanksgiving closes at 13:00
    exps = [fri, date(2026, 11, 30)]
    assert optcalc.pick_expiries("SPY", exps, fri, 11 * 60 + 59)["front"] == fri
    assert optcalc.pick_expiries("SPY", exps, fri, 12 * 60)["front"] == date(2026, 11, 30)


def test_overnight_counts_as_before_the_open() -> None:
    # Monday 21:00 ET plans Tuesday: Tuesday's 0DTE is the front.
    assert optcalc.minute_on(TUE, et(2026, 10, 12, 21, 0)) == 0
    assert optcalc.minute_on(TUE, et(2026, 10, 13, 10, 5)) == 605


# --- the readings ---------------------------------------------------------------------------


SYN = [
    _opt("C", 99, 1.9, 2.1, 0.62), _opt("C", 100, 1.4, 1.6, 0.5), _opt("C", 101, 0.9, 1.1, 0.38),
    _opt("C", 103, 0.3, 0.4, 0.24, iv=0.18),
    _opt("P", 99, 0.9, 1.1, -0.38), _opt("P", 100, 1.3, 1.5, -0.5), _opt("P", 101, 1.9, 2.1, -0.62),
    _opt("P", 97, 0.3, 0.4, -0.26, iv=0.24),
]


def test_atm_straddle_is_the_expected_move() -> None:
    m = optcalc.expected_move(SYN, 100.2)
    assert m is not None
    assert m["straddle"] == pytest.approx(1.5 + 1.4)  # call mid 1.5 + put mid 1.4
    assert m["pct"] == pytest.approx(2.9 / 100.2 * 100, rel=1e-3)
    assert (m["lo"], m["hi"]) == (pytest.approx(97.3), pytest.approx(103.1))


def test_real_0dte_expected_move_is_plausible() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    m = optcalc.expected_move(c.opts[TUE], c.spot or 0)
    assert m is not None and 0.1 < m["pct"] < 1.5


def test_nearest_delta_wants_a_bid() -> None:
    opts = [*SYN, _opt("C", 99.5, 0.0, 2.0, 0.6)]  # nearest delta, but no bid
    o = optcalc.nearest_delta(opts, "C", 0.60)
    assert o is not None and o.strike == 99
    p = optcalc.nearest_delta(SYN, "P", 0.30)
    assert p is not None and p.strike == 97


def test_skew_is_put_iv_minus_call_iv_at_25_delta() -> None:
    assert optcalc.skew25(SYN) == pytest.approx(6.0)  # 24 − 18 vol points


@pytest.mark.parametrize("bid,ask,grade", [(1.48, 1.52, "good"), (1.45, 1.55, "ok"),
                                           (1.0, 2.0, "poor")])
def test_liquidity_grade(bid: float, ask: float, grade: str) -> None:
    opts = [_opt("C", 100, bid, ask, 0.5), _opt("P", 100, bid, ask, -0.5)]
    liq = optcalc.liquidity(opts, 100.0)
    assert liq["grade"] == grade and liq["oi"] == 200.0


def test_realised_vol() -> None:
    assert optcalc.realised_vol([100.0] * 25) == 0.0
    assert optcalc.realised_vol([100.0] * 10) is None
    # Alternating ±1%: daily stdev ≈ 1.03%, annualised ≈ 16%.
    xs = [100.0]
    for i in range(30):
        xs.append(xs[-1] * (1.01 if i % 2 else 0.99))
    rv = optcalc.realised_vol(xs)
    assert rv is not None and 15.0 < rv < 17.5


def test_premium_verdict() -> None:
    assert optcalc.premium(0.8) == "cheap"
    assert optcalc.premium(1.0) == "fair"
    assert optcalc.premium(1.3) == "rich"
    assert optcalc.premium(None) is None


def test_iv_rank_needs_twenty_days() -> None:
    assert optcalc.iv_rank([20.0] * 19, 25.0) == (None, None)
    hist = [10.0 + i for i in range(20)]  # 10 … 29
    rank, pct = optcalc.iv_rank(hist, 29.0)
    assert rank == 100.0 and pct == 95.0
    assert optcalc.iv_rank(hist, 10.0)[0] == 0.0


def test_earnings_inside_an_expiry() -> None:
    pre = {"date": "2026-10-15", "when": "pre"}
    post = {"date": "2026-10-15", "when": "after"}
    assert optcalc.spans_earnings(date(2026, 10, 15), pre) is True
    assert optcalc.spans_earnings(date(2026, 10, 15), post) is False
    assert optcalc.spans_earnings(date(2026, 10, 16), post) is True
    assert optcalc.spans_earnings(date(2026, 10, 14), pre) is False
    assert optcalc.spans_earnings(date(2026, 10, 16), None) is False


# --- the stop and the contracts -------------------------------------------------------------


def test_stop_prefers_the_signal_while_price_holds_it() -> None:
    row = {"last": 101.0, "atr_b": 0.5, "setup": {"entry": {"kind": "PMH", "price": 100.0}},
           "signals": [{"kind": "L", "side": "long", "stop": 99.6}]}
    assert optcalc.stock_stop(row, "long")[0] == 99.6
    # Price below the signal's stop AND under the entry's buffer: one bar-ATR.
    row["last"] = 99.5
    stop, how = optcalc.stock_stop(row, "long")
    assert stop == pytest.approx(99.0) and "ATR" in how
    row["last"] = 100.5
    row["signals"] = [{"kind": "L", "side": "long", "stop": 100.9}]
    assert optcalc.stock_stop(row, "long")[0] == pytest.approx(100.0 - 0.25 * 0.5)


def test_stop_falls_back_to_one_atr_and_mirrors_for_shorts() -> None:
    row = {"last": 50.0, "atr_b": 0.4, "setup": {"entry": None}, "signals": []}
    assert optcalc.stock_stop(row, "long")[0] == pytest.approx(49.6)
    assert optcalc.stock_stop(row, "short")[0] == pytest.approx(50.4)
    assert optcalc.stock_stop({"last": 50.0, "atr_b": None}, "long")[0] is None


def test_long_contract_risk_is_capped_at_its_premium() -> None:
    o = _opt("C", 99, 1.9, 2.1, 0.62)
    c = optcalc.contract_long(o, "front", TUE, stock_risk=0.5)
    assert c["risk_per_contract"] == pytest.approx(0.5 * 0.62 * 100)
    assert c["note"].startswith("0.62Δ call, 0DTE")
    big = optcalc.contract_long(o, "front", TUE, stock_risk=10.0)
    assert big["risk_per_contract"] == pytest.approx(2.0 * 100)  # the mid, not 620


def test_debit_spread_maths() -> None:
    lo, sh = _opt("C", 99, 1.9, 2.1, 0.62), _opt("C", 101, 0.9, 1.1, 0.38)
    s = optcalc.contract_spread(lo, sh, "weekly", TUE, stock_risk=1.0)
    assert s is not None
    assert s["mid"] == pytest.approx(1.0) and s["max_value"] == pytest.approx(2.0)
    assert s["delta"] == pytest.approx(0.24)
    assert (s["bid"], s["ask"]) == (pytest.approx(0.8), pytest.approx(1.2))
    assert s["risk_per_contract"] == pytest.approx(24.0)
    puts = optcalc.contract_spread(_opt("P", 101, 1.9, 2.1, -0.62), _opt("P", 99, 0.9, 1.1, -0.38),
                                   "front", TUE, None)
    assert puts is not None and puts["delta"] == pytest.approx(-0.24)


# --- the live estimate --------------------------------------------------------------------


def _chain_at(spot: float, asof: datetime) -> Chain:
    return Chain("X", spot, 30.0, asof.astimezone(UTC), [TUE])


def test_live_move_only_in_the_session_on_a_same_day_chain() -> None:
    c = _chain_at(100.0, et(2026, 10, 13, 10, 0))
    assert optcalc.live_move(c, 101.0, TUE, et(2026, 10, 13, 10, 15)) == (101.0, 1.0)
    assert optcalc.live_move(c, 101.0, TUE, et(2026, 10, 13, 9, 29)) is None  # before the open
    assert optcalc.live_move(c, 101.0, TUE, et(2026, 10, 13, 16, 0)) is None  # the bell
    assert optcalc.live_move(c, 106.0, TUE, et(2026, 10, 13, 10, 15)) is None  # past REMARK_MAX
    old = _chain_at(100.0, et(2026, 10, 12, 15, 50))
    assert optcalc.live_move(old, 101.0, TUE, et(2026, 10, 13, 10, 15)) is None  # yesterday's
    assert optcalc.live_move(c, None, TUE, et(2026, 10, 13, 10, 15)) is None


def test_remark_moves_mid_and_delta_through_gamma() -> None:
    call = replace(_opt("C", 100, 2.9, 3.1, 0.6), gamma=0.05)  # mid 3.00
    got = optcalc.remark(call, 102.0, 2.0)
    assert got == (pytest.approx(3.0 + 0.6 * 2 + 0.5 * 0.05 * 4), pytest.approx(0.7))
    put = replace(_opt("P", 100, 2.9, 3.1, -0.4), gamma=0.05)
    got = optcalc.remark(put, 98.0, -2.0)  # the stock down two: the put gains
    assert got == (pytest.approx(3.0 + 0.8 + 0.1), pytest.approx(-0.5))
    # No gamma (a summary saved before it was kept): delta alone.
    assert optcalc.remark(_opt("C", 100, 2.9, 3.1, 0.6), 101.0, 1.0) == (pytest.approx(3.6), 0.6)


def test_remark_floors_at_intrinsic_and_keeps_delta_on_its_side() -> None:
    o = replace(_opt("C", 100, 0.4, 0.6, 0.2), gamma=0.0)
    mid, _d = optcalc.remark(o, 104.0, 4.0) or (0.0, 0.0)
    assert mid == pytest.approx(4.0)  # 0.5 + 0.8 would be under the 4.00 intrinsic
    assert (optcalc.remark(replace(o, gamma=0.5), 104.0, 4.0) or (0.0, 0.0))[1] == 1.0
    assert optcalc.remark(_opt("C", 100, 0, 0, 0.5), 101.0, 1.0) is None  # no mid to move


def test_contract_carries_the_estimate_and_risk_follows_it() -> None:
    o = replace(_opt("C", 99, 1.9, 2.1, 0.62), gamma=0.04)
    c = optcalc.contract_long(o, "front", TUE, stock_risk=0.5, move=(101.0, 1.0))
    assert c["mid"] == pytest.approx(2.0) and c["delta"] == pytest.approx(0.62)  # as quoted
    assert c["est_mid"] == pytest.approx(2.0 + 0.62 + 0.02)
    assert c["est_delta"] == pytest.approx(0.66)
    assert (c["est_spot"], c["quote_spot"]) == (101.0, 100.0)
    assert c["risk_per_contract"] == pytest.approx(0.5 * 0.66 * 100)
    plain = optcalc.contract_long(o, "front", TUE, stock_risk=0.5)
    assert plain["est_mid"] is None and plain["risk_per_contract"] == pytest.approx(31.0)


def test_spread_estimate_stays_inside_its_width() -> None:
    lo = replace(_opt("C", 99, 1.9, 2.1, 0.62), gamma=0.04)
    sh = replace(_opt("C", 101, 0.9, 1.1, 0.38), gamma=0.04)
    s = optcalc.contract_spread(lo, sh, "weekly", TUE, 1.0, move=(101.0, 1.0))
    assert s is not None
    # (2.00 + 0.62 + 0.02) − (1.00 + 0.38 + 0.02); the gammas cancel in the net delta.
    assert s["est_mid"] == pytest.approx(1.24) and s["est_delta"] == pytest.approx(0.24)
    far = optcalc.contract_spread(lo, sh, "weekly", TUE, 1.0, move=(109.0, 9.0))
    assert far is not None and far["est_mid"] == pytest.approx(2.0)  # never past the width


def test_options_ctx_re_marks_in_the_session_only() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    assert c.spot is not None
    row = _spy_row("long") | {"last": c.spot + 1.0}
    live = optcalc.options_ctx(c, row, [], [], TUE, et(2026, 10, 13, 10, 0), None)
    assert live["contracts"] and all(k["est_mid"] is not None for k in live["contracts"])
    long0 = live["contracts"][0]
    assert long0["est_mid"] > long0["mid"]  # a call, with the stock a dollar higher
    pre = optcalc.options_ctx(c, row, [], [], TUE, et(2026, 10, 13, 8, 0), None)
    assert all(k["est_mid"] is None for k in pre["contracts"])


def test_gamma_is_read_and_survives_the_summary() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    first = c.opts[TUE][0]
    assert first.gamma is not None
    back = opt_src.load_chain(opt_src.dump_chain(c))
    assert back is not None and back.opts[TUE][0].gamma == first.gamma
    # A summary written before gamma was kept still loads, without it.
    doc = json.loads(opt_src.dump_chain(c))
    doc["opts"] = {k: [r[:10] for r in rows] for k, rows in doc["opts"].items()}
    old = opt_src.load_chain(json.dumps(doc).encode())
    assert old is not None and old.opts[TUE][0].gamma is None


def _spy_row(side: str | None) -> dict[str, Any]:
    return {"last": 777.68, "atr_b": 0.7, "signals": [], "earnings": None,
            "setup": {"side": side, "entry": {"kind": "PDH", "price": 777.0, "dist_atr": 1.0}},
            "score": {"side": side}}


def test_options_ctx_on_a_real_chain() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    ctx = optcalc.options_ctx(c, _spy_row("long"), [500.0 + i for i in range(25)], [12.0] * 5,
                              TUE, et(2026, 10, 13, 8, 0), age_min=1.0)
    assert ctx["ok"] is True and ctx["zero_dte"] is True and ctx["iv_days"] == 5
    assert ctx["iv_rank"] is None  # five days logged is not a rank
    assert [m["key"] for m in ctx["em"]] == ["front", "weekly"]
    assert ctx["em"][0]["dte"] == 0 and ctx["em"][1]["expiry"] == "2026-10-15"
    kinds = [(k["key"], k["kind"]) for k in ctx["contracts"]]
    assert kinds == [("front", "long"), ("front", "spread"), ("weekly", "long"),
                     ("weekly", "spread")]
    long0 = ctx["contracts"][0]
    assert long0["right"] == "C" and 0.45 <= long0["delta"] <= 0.75
    assert long0["stock_risk"] == pytest.approx(777.68 - (777.0 - 0.25 * 0.7))
    assert ctx["liquidity"]["grade"] in ("good", "ok")


def test_no_side_no_contracts_and_shorts_buy_puts() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    none = optcalc.options_ctx(c, _spy_row(None), [], [], TUE, et(2026, 10, 13, 8, 0), None)
    assert none["contracts"] == [] and none["rv20"] is None and none["premium"] is None
    short = optcalc.options_ctx(c, _spy_row("short"), [], [], TUE, et(2026, 10, 13, 8, 0), None)
    assert {k["right"] for k in short["contracts"]} == {"P"}


def test_earnings_in_flags_the_first_expiry_that_spans_it() -> None:
    c = optcalc.parse_chain(_doc("cboe_aapl_trim.json"), "AAPL", TUE)
    row = _spy_row("long") | {"last": 343.5,
                              "earnings": {"date": "2026-10-15", "when": "after", "days": 2}}
    ctx = optcalc.options_ctx(c, row, [], [], TUE, et(2026, 10, 13, 10, 0), None)
    assert ctx["zero_dte"] is False  # AAPL lists no Tuesday expiry
    assert ctx["earnings_in"] == "2026-10-16"  # Wednesday's ends before the report


def test_empty_chain_is_unavailable_not_an_error() -> None:
    ctx = optcalc.options_ctx(Chain("X", 10.0, 30.0, None, []), _spy_row("long"), [], [], TUE,
                              et(2026, 10, 13, 10, 0), 2.0)
    assert ctx["ok"] is False and ctx["error"] and ctx["contracts"] == []


# --- the source ---------------------------------------------------------------------------


def test_cadence_by_session_and_name() -> None:
    assert opt_src.cadence("SPY", et(2026, 10, 13, 10, 0)) == opt_src.ETF_SEC
    assert opt_src.cadence("AAPL", et(2026, 10, 13, 10, 0)) == opt_src.SINGLE_SEC
    assert opt_src.cadence("AAPL", et(2026, 10, 13, 7, 59)) == opt_src.IDLE_SEC
    assert opt_src.cadence("SPY", et(2026, 10, 17, 10, 0)) == opt_src.IDLE_SEC  # Saturday
    assert opt_src.cadence("SPY", et(2026, 11, 26, 10, 0)) == opt_src.IDLE_SEC  # Thanksgiving


def test_iv_day_belongs_to_the_last_session_that_opened() -> None:
    assert opt_src.iv_day(et(2026, 10, 13, 8, 0), et(2026, 10, 13, 8, 0)) == date(2026, 10, 12)
    assert opt_src.iv_day(et(2026, 10, 13, 10, 0), et(2026, 10, 13, 10, 0)) == TUE
    assert opt_src.iv_day(et(2026, 10, 17, 12, 0), et(2026, 10, 17, 12, 0)) == date(2026, 10, 16)


def test_iv_history_round_trip_and_prune(tmp_path: Any) -> None:
    path = str(tmp_path / "iv.jsonl")
    h = opt_src.IvHistory(path)
    h.record("SPY", date(2025, 1, 2), 15.0)  # older than the keep window
    h.record("SPY", date(2026, 10, 12), 12.0)
    h.record("SPY", date(2026, 10, 13), 12.5)
    h.record("SPY", date(2026, 10, 13), 12.6)  # same day: last wins
    h.save(TUE)
    again = opt_src.IvHistory(path)
    assert again.series("SPY") == [12.0, 12.6]


def test_chain_summary_round_trip() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    back = opt_src.load_chain(opt_src.dump_chain(c))
    assert back is not None and back.expiries == c.expiries and back.spot == c.spot
    assert back.opts[TUE][0] == c.opts[TUE][0]
    assert opt_src.load_chain(b"not json") is None


def test_store_fetches_backs_off_and_pauses(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(_doc("cboe_spy_trim.json")).encode()
    calls: list[str] = []

    def fake(url: str, **_kw: Any) -> FetchResult:
        calls.append(url)
        if "SPY" in url:
            return FetchResult(True, body, "live", 0.0, None, 200)
        if "ZZZZ" in url:
            return FetchResult(False, None, "unavailable", None, "HTTP 404", 404)
        return FetchResult(False, None, "unavailable", None, "HTTP 429", 429)

    monkeypatch.setattr(opt_src, "fetch", fake)
    monkeypatch.setattr(opt_src.CACHE, "write", lambda *_a: None)
    monkeypatch.setattr(opt_src.CACHE, "read", lambda *_a: None)
    s = opt_src.OptionsStore(str(tmp_path / "iv.jsonl"))
    now = et(2026, 10, 13, 10, 0)
    st = s.tick(["SPY", "ZZZZ"], TUE, now)
    assert st.ok and "SPY" in s.chains and s.history.series("SPY") == [pytest.approx(12.069)]
    # SPY is fresh, ZZZZ is next; its 404 says why and backs it off.
    s.tick(["SPY", "ZZZZ"], TUE, now)
    assert "lists no options" in s.errors["ZZZZ"] and s.due(["SPY", "ZZZZ"], now) == []
    # A 429 pauses every fetch.
    s.tick(["MEH"], TUE, now)
    n = len(calls)
    st = s.tick(["MEH2"], TUE, now)
    assert len(calls) == n and any("paused" in x for x in st.notes)


# --- the join -----------------------------------------------------------------------------


def test_build_attaches_options_only_once_a_chain_is_held() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    clk = scan.clock_at(et(2026, 10, 13, 8, 0))
    now = et(2026, 10, 13, 8, 0)
    base = scanscore._empty("SPY", 1.0, "test")
    common: dict[str, Any] = dict(quotes=[], sectors=[], calendar=[], earnings=[], wire=[],
                                  news={}, filings={}, aliases={}, status=None,
                                  watchlist=["SPY", "AAPL"], clock=clk, now=now)
    p = scanscore.build({"rows": {"SPY": base, "AAPL": scanscore._empty("AAPL", 1.0, "t")}},
                        options={"SPY": (c, now.timestamp() - 120)}, **common)
    rows = {r["sym"]: r for r in p["rows"]}
    assert rows["SPY"]["options"]["ok"] is True
    assert rows["SPY"]["options"]["age_min"] == pytest.approx(2.0)
    assert rows["AAPL"]["options"] is None
