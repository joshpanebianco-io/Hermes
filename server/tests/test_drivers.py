"""The driver board: each vote's threshold and its clock, the grade, the
macro-against-structure conflict, the context rows, and the treatment line."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import drivers

NOW = datetime(2026, 10, 22, 14, 30, tzinfo=UTC)  # 10:30 ET, cash open


def _q(key: str, last: float, pct: float = 0.0, chg: float = 0.0,
       feed: str = "live") -> dict[str, Any]:
    return {"key": key, "last": last, "pct": pct, "chg": chg, "feed": feed}


def _snap(**over: Any) -> dict[str, Any]:
    quotes = [
        _q("NQ", 30_000.0), _q("ES", 8_000.0), _q("GC", 4_000.0),
        _q("US10Y", 4.10, chg=0.06), _q("DXY", 99.0, pct=0.4), _q("HYG", 80.0, pct=-0.3),
        _q("VIX", 18.0, pct=3.0), _q("VIX3M", 20.0), _q("SILVER", 50.0, pct=1.0),
        _q("COPPER", 5.0, pct=0.8), _q("VXN", 24.0),
    ]
    snap: dict[str, Any] = {
        "quotes": quotes, "calendar": [], "sectors": [], "constituents": {"indices": {}},
        "gex": {"enabled": True, "assets": {
            "NQ": {"ok": True, "spot": 30_000.0, "regime": "NEG",
                   "levels": [{"key": "flip", "price": 30_200.0}]}}},
        "profiles": {"assets": {"NQ": {"ok": True, "last": 30_000.0, "rows": [
            {"key": "prev_rth", "vah": 30_400.0, "val": 30_100.0, "poc": 30_250.0}]}}},
        "ranges": {"assets": {"NQ": {"last": 30_000.0, "sessions": [
            {"ok": True, "label": "Asia", "high": 30_300.0, "low": 30_050.0,
             "status": "complete", "start_ts": 100}]}}},
        "history": {"books": {"NQ": {"ok": True, "sma20": 30_500.0, "sma50": 30_800.0,
                                     "sma200": 29_000.0, "wk52_hi": 31_000.0, "wk52_lo": 25_000.0,
                                     "pw_hi": 30_900.0, "pw_lo": 30_200.0}}},
        "volterm": {"books": [{"key": "NQ", "sigma": 450.0}]},
        "cot": {"books": {"NQ": {"ok": True, "spec": "Leveraged funds", "net": -48_000,
                                  "pctile": 12, "read": "Leveraged funds net short.",
                                  "as_of": "2026-10-13"}}},
        "putcall": {"date": "2026-10-21", "ratios": {"equity": 0.52, "total": 0.87},
                    "read": {"equity": "call-heavy.", "total": "normal."}},
        "expiry": {"opex_week": False},
        "policy_meetings": {"meetings": []},
    }
    snap.update(over)
    return snap


def _votes(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {v["key"]: v for v in board["votes"]}


def test_nq_board_counts_the_votes_and_names_the_conflict() -> None:
    out = drivers.build(_snap(), "rth", NOW)
    nq = out["books"]["NQ"]
    v = _votes(nq)
    assert v["yields"]["vote"] == "short" and v["yields"]["value"] == "4.10% +6.0bp"
    assert v["dollar"]["vote"] == "short"
    assert v["credit"]["vote"] == "short"
    assert v["vix_dir"]["vote"] == "short"
    assert v["vix_curve"]["vote"] == "neutral"  # 18 / 20 = 0.90 sits on the calm bound
    assert v["gamma"]["vote"] == "short" and "200 below the flip (0.4σ)" in v["gamma"]["note"]
    assert v["value"]["vote"] == "short" and v["value"]["value"] == "below (VAL 30,100)"
    assert v["session"]["vote"] == "short" and "Asia's low is taken out" in v["session"]["note"]
    assert v["frame"]["vote"] == "short"
    assert v["frame"]["value"] == "Above the 200-day, below the 20 and 50-day"
    assert v["sectors"]["vote"] == "neutral" and v["leaders"]["vote"] == "neutral"
    assert nq["bias"] == "short" and nq["grade"] == "strong"
    assert nq["macro_lean"] == "short" and nq["structure_lean"] == "short"
    assert nq["conflict"] is False
    assert nq["treatment"].startswith("Lean short NQ, strong (")
    assert "Negative gamma: breaks run" in nq["treatment"]
    ctx = {c["key"]: c for c in nq["context"]}
    assert ctx["cot"]["value"] == "net short 48,000 · 12th pct"
    assert ctx["putcall"]["value"] == "equity 0.52 · total 0.87"


def test_vix_curve_threshold_is_the_stocks_desks() -> None:
    calm = drivers.build(_snap(quotes=[_q("NQ", 1.0), _q("VIX", 16.0), _q("VIX3M", 20.0)]),
                         "rth", NOW)
    assert _votes(calm["books"]["NQ"])["vix_curve"]["vote"] == "long"
    stress = drivers.build(_snap(quotes=[_q("NQ", 1.0), _q("VIX", 21.0), _q("VIX3M", 20.0)]),
                           "rth", NOW)
    assert _votes(stress["books"]["NQ"])["vix_curve"]["vote"] == "short"


def test_cash_reads_are_neutral_outside_us_hours_and_say_so() -> None:
    snap = _snap()
    for q in snap["quotes"]:
        if q["key"] in ("HYG", "VIX"):
            q["feed"] = "closed"
    out = drivers.build(snap, "closed", NOW)
    v = _votes(out["books"]["NQ"])
    assert v["credit"]["vote"] == "neutral" and "closed" in v["credit"]["note"]
    assert v["vix_dir"]["vote"] == "neutral" and "close" in v["vix_dir"]["note"]
    assert v["leaders"]["vote"] == "neutral"
    assert "(gamma is a reference outside New York)" in out["books"]["NQ"]["treatment"]


def test_conflict_lowers_the_read_to_the_levels() -> None:
    snap = _snap()
    # Structure long: above prior value, above Asia's high, above the averages.
    snap["quotes"][0]["last"] = 31_000.0
    snap["profiles"]["assets"]["NQ"]["last"] = 31_000.0
    snap["gex"]["assets"]["NQ"]["spot"] = 31_000.0
    out = drivers.build(snap, "rth", NOW)
    nq = out["books"]["NQ"]
    assert nq["macro_lean"] == "short" and nq["structure_lean"] == "long"
    assert nq["conflict"] is True
    assert nq["treatment"].startswith("Macro leans short on NQ but structure accepts long")


def test_gold_reads_silver_and_not_credit_and_never_the_equity_curve() -> None:
    out = drivers.build(_snap(), "rth", NOW)
    gc = out["books"]["GC"]
    v = _votes(gc)
    assert "credit" not in v and "sectors" not in v and "leaders" not in v
    assert v["silver"]["vote"] == "long" and "industrial as well" in v["silver"]["note"]
    assert v["vix_curve"]["vote"] == "neutral"
    assert v["yields"]["vote"] == "short" and "carrying cost" in v["yields"]["note"]
    assert v["dollar"]["note"].startswith("a firmer dollar is the unit gold is priced in")
    assert not any(c["key"] == "putcall" for c in gc["context"])


@pytest.mark.parametrize("bp,vote", [(0.06, "short"), (-0.05, "long"), (0.02, "neutral")])
def test_yields_threshold(bp: float, vote: str) -> None:
    out = drivers.build(_snap(quotes=[_q("NQ", 1.0), _q("US10Y", 4.0, chg=bp)]), "rth", NOW)
    assert _votes(out["books"]["NQ"])["yields"]["vote"] == vote


def test_prints_vote_on_inflation_only() -> None:
    cal = [{"region": "us", "score": 4, "ts": NOW.timestamp() - 3600, "event": "Core CPI m/m",
            "actual": 0.4, "consensus": 0.3, "previous": 0.3, "surprise": 0.1,
            "released": True, "themes": ["inflation"]},
           {"region": "us", "score": 4, "ts": NOW.timestamp() - 1800, "event": "Retail Sales m/m",
            "actual": 0.1, "consensus": 0.3, "previous": 0.2, "surprise": -0.2,
            "released": True, "themes": ["growth"]}]
    out = drivers.build(_snap(calendar=cal), "rth", NOW)
    v = _votes(out["books"]["NQ"])["prints"]
    assert v["vote"] == "short"
    assert "Core CPI m/m hot" in v["value"] and "Retail Sales m/m cold" in v["value"]
    assert v["note"].startswith("Hotter than priced")
    gc = _votes(out["books"]["GC"])["prints"]
    assert gc["vote"] == "short" and "real yields up" in gc["note"]


def test_empty_snapshot_is_all_neutral_with_reasons() -> None:
    out = drivers.build({"quotes": []}, "closed", NOW)
    for book in ("NQ", "ES", "GC"):
        b = out["books"][book]
        assert b["bias"] is None and b["grade"] == "none"
        assert all(v["vote"] == "neutral" and v["note"] for v in b["votes"])
        assert b["treatment"].startswith(f"No lean on {book}:")


def test_the_ten_minute_200_ema_votes_a_side() -> None:
    from newsterminal.drivers import _trend10m
    ranges = {"assets": {"NQ": {"ema200_10m": {"value": 29_800.0, "slope": "falling"}}}}
    above = _trend10m(ranges, "NQ", 30_000.0)
    assert above["vote"] == "long" and above["value"] == "above 29,800"
    assert "falling" in above["note"]
    assert _trend10m(ranges, "NQ", 29_500.0)["vote"] == "short"
    assert _trend10m(ranges, "NQ", 29_805.0)["vote"] == "neutral"       # on the line
    assert _trend10m({"assets": {"NQ": {}}}, "NQ", 30_000.0)["vote"] == "neutral"


def test_the_daily_200_ema_votes_the_regime() -> None:
    from newsterminal.drivers import _regime200
    frames = {"books": {"NQ": {"ok": True, "ema200": 28_000.0}}}
    up = _regime200(frames, "NQ", 29_000.0)
    assert up["vote"] == "long" and up["value"] == "above 28,000" and "3.6% above" in up["note"]
    assert _regime200(frames, "NQ", 27_000.0)["vote"] == "short"
    assert _regime200(frames, "NQ", 28_100.0)["vote"] == "neutral"      # within half a percent
    assert _regime200({"books": {"NQ": {"ok": True}}}, "NQ", 29_000.0)["vote"] == "neutral"
