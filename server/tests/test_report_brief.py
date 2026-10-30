"""
The brief's tables are computed, not written — so they are what gets tested.

Every figure the page prints outside the model's prose comes from
`build_facts`, and the model's answer is joined to those figures by id in
`sanitize_brief`. A wrong ladder, or a join that let an invented id through,
would put a number on the page that nobody computed — the one failure the
brief's split between facts and words exists to prevent.
"""

from __future__ import annotations

import math
from typing import Any

from newsterminal.report import build_digest, build_facts, norm_bias, sanitize_brief

CLOCK = {"et": "2026-09-15T08:50:00-04:00"}


def _lv(key: str, label: str, side: str, price: float, rank: int) -> dict[str, Any]:
    return {"key": key, "label": label, "side": side, "price": price, "rank": rank}


def _sess(key: str, high: float, low: float) -> dict[str, Any]:
    return {"key": key, "label": key, "ok": True, "high": high, "low": low}


def _snap(**over: Any) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "clock": CLOCK,
        "status": {},
        "quotes": [
            {"key": "NQ", "last": 29408.0, "prev": 29152.0, "pct": 0.88, "chg": 256.0},
            {"key": "VXN", "last": 22.1, "pct": 1.0},
            {"key": "DXY", "last": 99.58, "chg": 0.1, "pct": 0.1},
        ],
        "gex": {"assets": {"NQ": {
            "ok": True, "regime": "NEG", "spot": 29408.0, "em_hi": 29548.0, "em_lo": 29268.0,
            "levels": [
                _lv("call_2", "Call wall 2", "call", 30500.0, 2),
                _lv("flip", "Gamma flip", "flip", 29618.0, 1),
                _lv("call_1", "Call wall", "call", 29459.0, 1),
                _lv("put_2", "Put wall 2", "put", 29300.0, 2),
                _lv("put_1", "Put wall", "put", 29044.0, 1),
            ],
        }}},
        "ranges": {"assets": {"NQ": {"last": 29408.0, "sessions": [
            _sess("asia", 29495.0, 29300.0),
            _sess("london", 29420.0, 29231.0),
            _sess("premkt", 29440.0, 29380.0),
            {"key": "ny", "ok": False},
            # The ladder's overnight is this one row (2026-10-30), not the boxes' union.
            _sess("overnight", 29495.0, 29231.0),
        ]}}},
    }
    snap.update(over)
    return snap


def _nq(snap: dict[str, Any]) -> dict[str, Any]:
    ladder: dict[str, Any] = build_facts(snap, "ny", "NQ")["ladders"][0]
    return ladder


def test_ladder_is_price_ordered_with_last_in_place() -> None:
    rows = _nq(_snap())["rows"]
    prices = [r["price"] for r in rows]
    assert prices == sorted(prices, reverse=True)
    labels = [r["label"] for r in rows]
    assert labels.index("Gamma flip") < labels.index("Call wall") < labels.index("Last")
    assert labels.index("Last") < labels.index("Put wall")


def test_far_secondary_walls_are_left_off() -> None:
    labels = [r["label"] for r in _nq(_snap())["rows"]]
    assert "Call wall 2" not in labels  # 1,092 points out, far past 1.5 expected moves
    assert "Put wall 2" in labels  # 108 points out, inside one


def test_overnight_range_is_the_overnight_box() -> None:
    rows = {r["label"]: r for r in _nq(_snap())["rows"]}
    assert rows["ON high"]["price"] == 29495.0
    assert rows["ON low"]["price"] == 29231.0
    assert rows["Gamma flip"]["dist"] == 210
    assert rows["Prior settle"]["dist"] == -256
    assert rows["ON high"]["inside_em"] is True
    assert rows["Put wall"]["inside_em"] is False


def test_expected_move_prefers_the_gexygen_band() -> None:
    ladder = _nq(_snap())
    assert ladder["em"] == 140
    assert ladder["em_basis"] == "GEXYGEN"


def test_expected_move_falls_back_to_implied_vol_and_says_so() -> None:
    ladder = _nq(_snap(gex={"assets": {}}))
    assert ladder["em"] == round(29408.0 * 22.1 / 100 / math.sqrt(252))
    assert "VXN" in ladder["em_basis"]
    assert "not GEXYGEN" in ladder["note"]


def test_ratio_direction_uses_the_week_with_a_flat_band() -> None:
    sectors = [
        {"key": "XLK", "last": 180.0, "week_pct": 2.0},
        {"key": "XLU", "last": 40.0, "week_pct": -1.0},
        {"key": "SPY", "last": 700.0, "week_pct": 1.9},
    ]
    facts = build_facts(_snap(sectors=sectors), "ny", "NQ")
    ratios = {r["id"]: r for r in facts["rotation"]["ratios"]}
    assert ratios["XLK/XLU"]["dir"] == "up"
    assert ratios["XLK/XLU"]["level"] == 4.5
    assert ratios["XLK/SPY"]["dir"] == "flat"  # 0.1% over a week is noise


def test_headlines_and_catalysts_carry_ids_into_the_digest() -> None:
    snap = _snap(
        wire=[{"title": "10Y hits 19-year high", "impact": "high", "region": "us",
               "utc": "2026-09-15T12:36:00+00:00", "publisher": "Wire", "url": "u"}],
        calendar=[{"event": "Empire State", "country": "US", "ts": 1789475400.0,
                   "released": True, "score": 3, "core": True, "actual_raw": "11.2",
                   "consensus_raw": "14.8"}],
        earnings=[{"symbol": "NVDA", "bellwether": True, "date": "2026-09-15",
                   "when": "after", "eps_forecast": "1.10"}],
    )
    facts = build_facts(snap, "ny", "NQ")
    assert facts["headlines"][0]["id"] == "h1"
    assert facts["headlines"][0]["time_et"] == "08:36 ET"
    digest = build_digest(snap, "ny", "NQ", facts)
    assert [c["id"] for c in digest["catalysts"]] == ["c1", "c2"]
    assert digest["catalysts"][0]["when"] == "Today 08:30 ET"
    # An earnings row relabels `when`; that override once collided with the
    # builder's own parameter and raised.
    assert digest["catalysts"][1]["when"] == "Today after the close"
    assert "url" not in digest["headlines"][0]


def test_tomorrows_fomc_survives_a_morning_of_prints() -> None:
    """The first live brief: eleven released prints filled the list and the FOMC fell off."""
    at_0830 = 1789475400.0
    prints = [
        {"event": f"CPI {i}", "country": "US", "core": True, "score": 4,
         "released": True, "ts": at_0830 - 60 * i}
        for i in range(20)
    ]
    foreign = [
        {"event": "CPI", "country": "Norway", "core": False, "score": 4,
         "released": False, "ts": at_0830 + 3600},
        # An actual already in on a print stamped for later today: a bad stamp.
        {"event": "Retail Sales", "country": "China", "core": True, "score": 4,
         "released": True, "ts": at_0830 + 13 * 3600},
    ]
    fed = [{"kind": "FOMC", "title": "FOMC decision", "date": "2026-09-16",
            "ts": 1789581600.0, "major": True}]
    cats = build_facts(_snap(calendar=prints + foreign, fed=fed), "ny", "NQ")["catalysts"]
    assert cats[-1]["title"] == "FOMC decision"
    assert cats[-1]["when"] == "Tomorrow 14:00 ET"
    assert len([c for c in cats if c["kind"] == "data"]) == 6
    assert all(c.get("country") not in {"Norway", "China"} for c in cats)


def _facts() -> dict[str, Any]:
    return {
        "books": ["NQ"],
        "snapshot": [{"key": "US10Y"}],
        "catalysts": [{"id": "c1"}],
        "rotation": {"ratios": [{"id": "QQQ/IWM"}]},
        "headlines": [{"id": "h1"}],
    }


BRIEF: dict[str, Any] = {
    "thesis": "Real yields are the driver.",
    "calls": [
        {"book": "NQ", "open_bias": "Lean Bear", "conviction": "3",
         "rest_of_day": "Neutral to leaning bearish", "rest_of_day_bias": "nonsense",
         "wrong_if": "Acceptance above 29,459"},
        {"book": "GC", "open_bias": "bearish", "conviction": 3},
    ],
    "reads": [{"book": "NQ", "regime": "Rate scare", "chain": ["Oil up", 7, "Yields up"],
               "drivers": [{"label": "10Y", "text": "19-yr high", "tone": "sideways"}]}],
    "snapshot_watch": [{"key": "US10Y", "note": "19-yr high"}, {"key": "BTC", "note": "x"}],
    "catalyst_notes": [{"id": "c1", "note": "missed"}, {"id": "c9", "note": "invented"}],
    "headlines": [
        {"id": "h1", "books": ["NQ", "Gold"], "note": "driver"},
        {"id": "h7", "books": ["NQ"], "note": "no such headline"},
    ],
}


def test_sanitize_maps_spelling_and_drops_what_it_cannot_join() -> None:
    out = sanitize_brief(BRIEF, _facts())
    assert out is not None
    assert [c["book"] for c in out["calls"]] == ["NQ"]  # GC is out of scope
    assert out["calls"][0]["open_bias"] == "leaning bearish"
    assert out["calls"][0]["conviction"] == 3
    assert out["calls"][0]["rest_of_day_bias"] == "leaning bearish"  # falls back to the open
    assert out["reads"][0]["chain"] == ["Oil up", "Yields up"]
    assert out["reads"][0]["drivers"][0]["tone"] == "neutral"
    assert [w["key"] for w in out["snapshot_watch"]] == ["US10Y"]
    assert [n["id"] for n in out["catalyst_notes"]] == ["c1"]
    assert out["headlines"] == [{"id": "h1", "books": ["NQ", "GC"], "note": "driver"}]


def test_a_book_in_scope_without_a_call_is_not_a_brief() -> None:
    facts = {**_facts(), "books": ["NQ", "GC"]}
    broken = {**BRIEF, "calls": [c for c in BRIEF["calls"] if c["book"] == "NQ"]}
    assert sanitize_brief(broken, facts) is None


def test_norm_bias() -> None:
    assert norm_bias("Lean Bull") == "leaning bullish"
    assert norm_bias("leaning_bearish") == "leaning bearish"
    assert norm_bias("bearish") == "bearish"
    assert norm_bias("up") is None
