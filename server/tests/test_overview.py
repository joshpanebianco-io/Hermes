"""The Market overview (overview.py): its facts, what it keeps of the model's
answer, the numerals guard, the 09:00 clock and a whole generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import overview as ov
from newsterminal import report as rp
from newsterminal import stockplan as sp

ET = ZoneInfo("America/New_York")


def _idx(sym: str, last: float, trend: int = 1) -> dict[str, Any]:
    return {"sym": sym, "ok": True, "last": last, "chg_pct": 0.42, "ext_pct": 0.61,
            "levels": {"pdh": 600.0, "pdl": 590.0, "pmh": 603.5, "pml": 598.25, "pdc": 597.0},
            "trend200": trend, "frame_read": {"text": "above the 20, 50 and 200-day"},
            "score": {"total": 0, "side": None}, "setup": {}}


def _scan() -> dict[str, Any]:
    return {
        "built_utc": "2026-11-13T14:00:00+00:00", "session": "pre", "trading_day": "2026-11-13",
        "regime": {"vix": {"last": 17.12, "pct": -2.5, "shape": "contango"}, "band": "normal",
                   "bias": "long", "confirm": "confirm", "spy_em_pct": 1.07,
                   "tape": {"SPY": {"chg_pct": 0.42, "ext_pct": 0.61, "trend": 1}}},
        "rows": [_idx("SPY", 595.5), _idx("QQQ", 520.0, -1), _idx("IWM", 603.25)],
    }


def _snap() -> dict[str, Any]:
    sec = [
        {"key": "XLK", "label": "Technology", "day_pct": 1.2, "rs_day": 0.8, "week_pct": 2.0},
        {"key": "XLE", "label": "Energy", "day_pct": -1.5, "rs_day": -1.9, "week_pct": -3.0},
        {"key": "XLF", "label": "Financials", "day_pct": 0.5, "rs_day": 0.1, "week_pct": 1.0},
        {"key": "SPY", "label": "S&P 500", "day_pct": 0.4, "rs_day": 0.0},
    ]
    return {
        "status": {"scanner": {"ok": True, "source": "live"}},
        "quotes": [{"key": "US10Y", "chg": 0.04, "pct": 1.0}, {"key": "WTI", "chg": -1.0,
                                                               "pct": -2.1}],
        "sectors": sec, "themes": [],
        "breadth_all": {"ok": True, "basis": "pre", "names": 414, "of": 2021, "advancers": 260,
                        "decliners": 150,
                        "leaders": {"XLK": {"up": [{"sym": "NVDA", "chg": 2.31}], "down": []},
                                    "XLE": {"up": [], "down": [{"sym": "XOM", "chg": -1.8}]}}},
        "wire": [], "calendar": [],
    }


TODAY = {"phase": {"label": "Pre-market", "title": "In play going into the open"}, "rows": [
    {"sym": "CBRS", "name": "Cerebras", "sector": "XLK", "chg": 16.5319, "lean": "long",
     "why": ["gap ▲ 1.52 ATR", "reported last night"],
     "story": {"title": "Cerebras rallies on its forecast", "tag": "Earnings"}},
    {"sym": "AAPL", "listed": True, "why": ["not in play yet"]},
]}

STORIES = [
    {"syms": ["NVDA"], "tag": "Earnings", "title": "Nvidia beats", "url": "https://x/1",
     "provider": "Stocktwits", "age_min": 44.7},
    {"syms": ["MSFT"], "tag": "News", "title": "Microsoft 365 outage", "url": "https://x/2",
     "provider": "dpa-AFX", "age_min": 91.7},
]


def _facts() -> dict[str, Any]:
    return ov.build_facts(_scan(), _snap(), TODAY, STORIES)


# --------------------------------------------------------------------------- facts


def test_indexes_are_read_against_their_own_levels() -> None:
    f = _facts()
    assert [x["sym"] for x in f["index"]] == ["SPY", "QQQ", "IWM"]
    spy = f["index"][0]
    assert spy["where"] == "inside the previous day's range" and spy["ema200_10m"] == "above"
    assert f["index"][1]["where"] == "below the previous day's low"
    assert f["index"][1]["ema200_10m"] == "below"
    assert f["index"][2]["where"] == "above the previous day's high"
    assert ov.where_word(600.01, {"pdh": 600.0, "pdl": 590.0}) == "above the previous day's high"
    assert ov.where_word(None, {"pdh": 600.0, "pdl": 590.0}) is None


def test_sectors_rank_against_spy_with_drivers_and_names() -> None:
    s = _facts()["sectors"]
    # A leader beat SPY and a laggard trailed it; SPY itself is neither.
    assert [x["key"] for x in s["leaders"]] == ["XLK", "XLF"]
    assert [x["key"] for x in s["laggards"]] == ["XLE"]
    assert s["leaders"][0]["names"] == ["NVDA +2.31%"]
    assert s["laggards"][0]["key"] == "XLE" and s["laggards"][0]["names"] == ["XOM -1.80%"]
    # Energy answers to crude, which fell: the verdict is the driver table's.
    assert any("WTI crude" in d and "headwind" in d for d in s["laggards"][0]["drivers"])
    # Before the bell the funds' move is the last session's, and the page says so.
    assert s["basis"].startswith("the last session") and s["names_basis"] == "pre-market"


def test_the_today_rows_leave_out_the_listed_names_and_stories_are_numbered() -> None:
    f = _facts()
    assert [r["sym"] for r in f["today"]["rows"]] == ["CBRS"]
    assert f["today"]["rows"][0]["chg_pct"] == 16.53
    assert [s["id"] for s in f["stories"]] == ["s1", "s2"]
    assert f["stories"][0]["publisher"] == "Stocktwits"
    assert "names" not in f
    assert f["wide_breadth"] == {"advancers": 260, "decliners": 150, "traded": 414, "of": 2021,
                                 "basis": "pre-market"}


# --------------------------------------------------------------------------- answer


GOOD = {
    "headline": "A firm open led by tech; energy the weak spot",
    "read": "SPY sits inside the previous day's range at 595.5 with VIX 17.12 in the normal band.",
    "sectors": "Technology leads, Energy lags with crude down.",
    "macro": "No prints today.",
    "news": [{"id": "s1", "why": "Nvidia sets the tone for semis."},
             {"id": "s9", "why": "not shown"}, {"id": "s1", "why": "twice"}],
    "risks": ["QQQ is below the previous day's low."],
    "focus": "Favour longs in tech; CBRS leads the list on its report.",
}


def test_sanitize_keeps_the_picks_it_was_shown_once_with_their_own_titles() -> None:
    out = ov.sanitize(GOOD, _facts())
    assert out is not None
    assert [n["id"] for n in out["news"]] == ["s1"]
    assert out["news"][0]["title"] == "Nvidia beats" and out["news"][0]["url"] == "https://x/1"
    assert out["read"].startswith("SPY sits") and out["focus"].startswith("Favour")
    assert ov.sanitize({"read": "no lead"}, _facts()) is None
    assert ov.sanitize({"overview": GOOD}, _facts())["headline"] == GOOD["headline"]  # type: ignore[index]


def test_unverified_flags_a_number_the_model_was_not_shown() -> None:
    f = _facts()
    seen = json.dumps(ov.build_digest(f))
    body = ov.sanitize({**GOOD, "headline": "SPY to 611.25"}, f)
    assert body is not None and ov.unverified(body, seen) == ["611.25"]
    assert ov.unverified(ov.sanitize(GOOD, f) or {}, seen) == []


def test_the_schema_only_lets_a_pick_name_a_story_it_saw() -> None:
    sch = ov.schema(ov.story_ids(_facts()))
    assert sch["properties"]["news"]["items"]["properties"]["id"]["enum"] == ["s1", "s2"]


# ---------------------------------------------------------------------- the clock


def _et(h: int, m: int, s: int = 0, day: int = 13) -> datetime:
    return datetime(2026, 11, day, h, m, s, tzinfo=ET).astimezone(UTC)


def test_the_0900_write_is_due_only_in_its_half_hour_on_a_trading_day() -> None:
    assert ov.auto_due(_et(8, 59, 59), [], []) is False
    assert ov.auto_due(_et(9, 0), [], []) is True
    assert ov.auto_due(_et(9, 29, 59), [], []) is True
    assert ov.auto_due(_et(9, 30), [], []) is False
    # Saturday 14 Nov 2026.
    assert ov.auto_due(_et(9, 5, day=14), [], []) is False


def test_one_written_since_0900_satisfies_it_and_one_before_does_not() -> None:
    before = [{"kind": "overview", "created_utc": _et(8, 50).isoformat()}]
    since = [{"kind": "overview", "created_utc": _et(9, 0, 30).isoformat()}]
    old_plan = [{"kind": "plan", "created_utc": _et(9, 1).isoformat()}]
    assert ov.auto_due(_et(9, 2), before, []) is True
    assert ov.auto_due(_et(9, 2), since, []) is False
    assert ov.auto_due(_et(9, 2), old_plan, []) is True


def test_two_tries_five_minutes_apart_and_no_more() -> None:
    first = _et(9, 0, 10)
    assert ov.auto_due(_et(9, 4), [], [first]) is False
    assert ov.auto_due(_et(9, 5, 10), [], [first]) is True
    assert ov.auto_due(_et(9, 20), [], [first, _et(9, 5, 10)]) is False
    # Yesterday's tries do not count today.
    assert ov.auto_due(_et(9, 1), [], [_et(9, 0, day=12), _et(9, 6, day=12)]) is True


# ---------------------------------------------------------------------- generation


def _answer(obj: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(obj)}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 999}}


def test_generate_stores_an_overview_beside_the_plans(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    calls: list[dict[str, Any]] = []

    def fake(payload: dict[str, Any], key: str, timeout: int = 0) -> dict[str, Any]:
        calls.append(payload)
        return _answer(GOOD)

    monkeypatch.setattr(rp, "_post", fake)
    out = ov.generate(_scan(), _snap(), TODAY, STORIES, auto=True)
    assert out["ok"] is True, out["error"]
    assert out["kind"] == "overview" and out["auto"] is True
    assert out["plan"]["news"][0]["id"] == "s1" and out["unverified"] == []
    assert calls[0]["response_format"]["json_schema"]["name"] == "market_overview"
    h = sp.history()
    assert h[0]["id"] == out["id"] and h[0]["kind"] == "overview" and h[0]["auto"] is True


def test_the_dashboard_card_is_the_newest_overview_and_skips_the_old_plans(
        monkeypatch: Any, tmp_path: Any) -> None:
    """The Dashboard's card (2026-11-13, in place of In play): the headline, what it means
    for the list and three risks, the calendar's first; a game plan is not an overview."""
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    monkeypatch.setattr(ov, "_CARD", {"key": None, "card": None})
    assert ov.latest_card() is None
    sp._store({"id": "20261112-091014", "et_label": "old", "model": "m", "ok": True,
               "plan": {"headline": "a game plan", "plans": []}})
    assert ov.latest_card() is None
    body = {"headline": "Tech leads", "focus": "Favour longs in tech.", "news": [],
            "events": ["08:30 PPI — before the open."], "risks": ["QQQ under 685.01.", "b", "c"]}
    sp._store({"id": "20261113-090010", "kind": "overview", "ok": True, "auto": True,
               "et_label": "Fri 13 Nov, 09:00 ET", "created_utc": "2026-11-13T14:00:10+00:00",
               "facts": {"trading_day": "2026-11-13"}, "plan": body})
    got = ov.latest_card()
    assert got is not None and got["headline"] == "Tech leads" and got["auto"] is True
    assert got["risks"] == ["08:30 PPI — before the open.", "QQQ under 685.01.", "b"]
    assert got["trading_day"] == "2026-11-13"
    # Read again from the cache, not the file, until a new one is stored.
    assert ov.latest_card() is got


def test_generate_without_a_key_invents_nothing(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    out = ov.generate(_scan(), _snap(), TODAY, STORIES)
    assert out["ok"] is False and "OPENROUTER_API_KEY" in out["error"] and sp.history() == []
