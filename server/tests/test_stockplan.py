"""The Game plan — facts, sanitising, the numerals guard, storage and routes.

The routes are driven through the ASGI app itself (no httpx in this venv, so
no TestClient): the same routing, validation and serialisation a request gets.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from newsterminal import report as rp
from newsterminal import stockplan as sp


def _row(sym: str, score: int, side: str | None, *, ok: bool = True,
         options: dict[str, Any] | None = None, news: int = 2) -> dict[str, Any]:
    return {
        "sym": sym, "name": f"{sym} Inc.", "ok": ok,
        "score": {"total": score, "side": side, "parts": []},
        "setup": {"side": side, "state": "retest", "level": "PMH",
                  "entry": {"kind": "PMH", "price": 101.234, "dist_atr": 0.31}, "note": ""},
        "last": 101.5678, "chg_pct": 1.234, "ext_pct": None,
        "rs": {"SPY": 0.456, "QQQ": 0.2}, "rvol": 1.87,
        "levels": {"pdh": 100.0, "pdl": 95.0, "pmh": 101.0, "pml": 99.0},
        "atr_d": 3.21, "atr_b": 0.45, "earnings": None,
        "news": [{"title": f"{sym} headline {i}", "publisher": "Yahoo Finance", "age_min": 12.4}
                 for i in range(news)],
        "options": options,
    }


OPTS = {
    "ok": True, "iv30": 31.26, "rv20": 24.0, "iv_rv": 1.3025, "premium": "rich", "iv_rank": None,
    "em": [{"key": "front", "pct": 0.9512}, {"key": "weekly", "pct": 2.4448}],
    "liquidity": {"grade": "good"}, "earnings_in": None,
    "contracts": [
        {"key": "front", "kind": "long", "expiry": "2026-10-13", "strike": 101.0, "right": "C",
         "mid": 1.234, "delta": 0.6012},
        {"key": "weekly", "kind": "long", "expiry": "2026-10-16", "strike": 100.0, "right": "C",
         "mid": 3.21, "delta": 0.6133},
        {"key": "weekly", "kind": "spread", "expiry": "2026-10-16", "strike": 100.0,
         "short_strike": 104.0, "mid": 1.75, "delta": 0.31},
    ],
}


def _scan() -> dict[str, Any]:
    return {
        "built_utc": "2026-10-13T12:00:00+00:00", "session": "pre", "trading_day": "2026-10-13",
        "regime": {"vix": {"last": 15.43, "pct": 3.97, "shape": "contango"}, "band": "normal",
                   "bias": "short", "confirm": None, "spy_em_pct": 0.972,
                   "tape": {"SPY": {"chg_pct": -0.06, "ext_pct": -0.072, "trend": 0},
                            "QQQ": {"chg_pct": -0.696, "ext_pct": -0.731, "trend": 0}}},
        "rows": [
            _row("AAA", 80, "long", options=OPTS),
            _row("BBB", 70, "short", options={"ok": False, "error": "no chain"}),
            _row("CCC", 60, "long", news=5),
            _row("DDD", 55, None),
            _row("EEE", 40, "short"),
            _row("QQQ", 30, "long"),
            _row("SPY", 10, None, options=OPTS),
            _row("XXX", 95, "long", ok=False),
        ],
    }


def _snap() -> dict[str, Any]:
    return {
        "status": {
            "scanner": {"ok": True, "source": "live"},
            "scan_news": {"ok": True, "source": "stale", "stale_age_min": 42.0},
            "quotes": {"ok": False, "error": "HTTP 429"},
            "earnings": {"ok": True, "source": "live"},
        },
        "calendar": [
            {"event": "CPI", "region": "us", "date": "2026-10-13", "et": "08:30", "score": 5,
             "released": False},
            {"event": "Minor US", "region": "us", "date": "2026-10-13", "et": "10:00", "score": 2},
            {"event": "ECB", "region": "eu", "date": "2026-10-13", "et": "08:15", "score": 5},
            {"event": "Retail Sales", "region": "us", "date": "2026-10-14", "et": "08:30",
             "score": 4},
            {"event": "Far away", "region": "us", "date": "2026-10-20", "et": "08:30", "score": 5},
            {"event": "Untimed", "region": "us", "date": "2026-10-13", "et": None, "score": 3},
        ],
    }


# --------------------------------------------------------------------------- facts


def test_pick_names_takes_the_top_with_a_side_then_the_tape() -> None:
    names = [r["sym"] for r in sp.pick_names(_scan()["rows"], 4)]
    # XXX has no data, DDD and SPY have no side; QQQ ranks 5th but is the tape.
    assert names == ["AAA", "BBB", "CCC", "EEE", "SPY", "QQQ"]


def test_top_is_clamped_to_the_contract_range() -> None:
    assert len(sp.build_facts(_scan(), _snap(), top=99)["names"]) <= sp.TOP_MAX + 2
    assert [n["sym"] for n in sp.build_facts(_scan(), _snap(), top=1)["names"]][:4] == [
        "AAA", "BBB", "CCC", "EEE"]


def test_facts_round_to_what_the_page_prints_and_cap_headlines() -> None:
    f = sp.build_facts(_scan(), _snap(), top=4)
    aaa = next(n for n in f["names"] if n["sym"] == "AAA")
    assert aaa["last"] == 101.57 and aaa["rs_spy"] == 0.46 and aaa["entry"]["price"] == 101.23
    ccc = next(n for n in f["names"] if n["sym"] == "CCC")
    # Five now, for the plan's "News:" line (owner, 2026-10-13), up from three.
    assert [h["id"] for h in ccc["headlines"]] == [f"CCC-h{i}" for i in range(1, 6)]


def test_options_summary_is_null_when_absent_or_failed_and_prefers_the_right_expiry() -> None:
    f = sp.build_facts(_scan(), _snap(), top=4)
    by = {n["sym"]: n for n in f["names"]}
    assert by["CCC"]["options"] is None          # no block at all
    assert by["BBB"]["options"] is None          # ok: false
    a = by["AAA"]["options"]
    assert a["premium"] == "rich" and a["iv30"] == 31.3 and a["em_weekly_pct"] == 2.44
    assert a["long"]["expiry"] == "2026-10-16"   # a single name takes the weekly
    assert by["SPY"]["options"]["long"]["expiry"] == "2026-10-13"  # SPY takes the same-day


def test_calendar_keeps_us_prints_scored_3_plus_on_the_plan_days_in_time_order() -> None:
    cal = sp.build_facts(_scan(), _snap(), top=4)["calendar"]
    assert [c["title"] for c in cal] == ["CPI", "Untimed", "Retail Sales"]
    assert cal[0]["et"] == "Tue 08:30" and cal[1]["et"] == "Tue (untimed)"


def test_partial_names_stale_down_missing_and_no_options() -> None:
    p = sp.build_facts(_scan(), _snap(), top=4)["partial"]
    joined = " | ".join(p)
    assert ("Per-name headlines: upstream unreachable — figures are a cached copy from 42 min ago."
            in p)
    assert "Yahoo quotes (VIX and the tape) unavailable (HTTP 429)." in p
    assert "Economic calendar: not collected yet." in p
    assert "Options chains" not in joined        # AAA carries options


def test_partial_says_when_no_row_has_options() -> None:
    scan = _scan()
    for r in scan["rows"]:
        r["options"] = None
    assert any(x.startswith("Options chains: not available yet") for x in
               sp.build_facts(scan, _snap(), top=4)["partial"])


def test_digest_carries_the_clock_and_the_strategy_figures() -> None:
    d = sp.build_digest(sp.build_facts(_scan(), _snap(), top=4))
    assert d["clock"]["open"] == "09:30" and d["clock"]["close"] == "16:00"
    assert "0.60 delta" in d["strategy"]


# ------------------------------------------------------------------------- storage


def test_persistence_round_trip_newest_first_and_path_safe(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    for i, hl in enumerate(["first", "second", "third"]):
        sp._store({"id": f"20261013-09000{i}", "et_label": f"t{i}", "model": "m",
                   "plan": {"headline": hl, "plans": [{"sym": "AAA"}] * i}})
    h = sp.history()
    assert [x["headline"] for x in h] == ["third", "second", "first"]
    assert h[0]["n"] == 2
    latest = sp.latest()
    assert latest is not None and latest["id"] == "20261013-090002"
    assert sp.load("../../20261013-090001")["plan"]["headline"] == "second"  # type: ignore[index]
    assert sp.remove("../outside") is False
    assert sp.remove("20261013-090002") is True
    assert [x["headline"] for x in sp.history()] == ["second", "first"]


# ---------------------------------------------------------------------- generation


def _answer(obj: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(obj)}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1234}}


GOOD = {
    "headline": "Shorts lead; AAA the long against the tape",
    "market": "SPY -0.06% and QQQ -0.7%; VIX 15.43 in the normal band.",
    "plans": [{"sym": "AAA", "side": "long", "conviction": 3, "plan": "Retest of PMH 101.23",
               "trigger": "Hold above 101.23 after 09:30", "invalidation": "Close below 99",
               "target": "PDH 100 already broken; weekly move 2.44%",
               "options": "Premium rich (iv_rv 1.3): the 100/104 weekly spread",
               "why": ["Structure: retest of PMH", "Options: rich premium"]}],
    "avoid": [{"sym": "EEE", "why": "No clean level."}],
    "timing": ["Tue 08:30 CPI", "09:30 open"],
    "risks": ["CPI at 08:30"],
}


# -------------------------------------------------------------------------- routes


def _asgi(method: str, path: str, query: str = "") -> tuple[int, Any]:
    from newsterminal.api import app

    status: dict[str, int] = {}
    chunks: list[bytes] = []

    async def run() -> None:
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(msg: dict[str, Any]) -> None:
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            elif msg["type"] == "http.response.body":
                chunks.append(msg.get("body", b""))

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "headers": [], "client": ("test", 1),
            "server": ("test", 80), "root_path": "",
        }
        await app(scope, receive, send)

    asyncio.run(run())
    body = b"".join(chunks)
    return status["code"], json.loads(body) if body else None


@pytest.fixture
def routed(monkeypatch: Any, tmp_path: Any) -> None:
    from newsterminal.collector import COLLECTOR

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    monkeypatch.setattr(COLLECTOR, "scanner_payload", _scan)
    monkeypatch.setattr(COLLECTOR, "snapshot", _snap)
    # The route writes the market overview since 2026-11-13 (overview.py), which also
    # reads the Today list and the stories.
    monkeypatch.setattr(COLLECTOR, "today", lambda: {"rows": []})
    monkeypatch.setattr(COLLECTOR, "top_stories", lambda: [])
    monkeypatch.setattr(rp, "_post", lambda payload, key, timeout=0: _answer(GOOD))


def _settled(path: str, tries: int = 100) -> dict[str, Any]:
    """Poll a job route until the job is no longer running (jobs.py)."""
    import time

    for _ in range(tries):
        code, body = _asgi("GET", path)
        assert code == 200
        if body["job"]["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"{path} still running")


def test_routes_generate_read_and_delete(routed: None) -> None:
    # The POST answers with the job at once; the plan arrives by polling it.
    code, body = _asgi("POST", "/api/plan", "top=4")
    assert code == 200 and body["config"]["enabled"] is True
    assert body["job"]["state"] in ("running", "done") and body["job"]["top"] == 4
    body = _settled(f"/api/plan/job/{body['job']['id']}")
    assert body["job"]["state"] == "done" and body["latest"]["ok"] is True
    assert body["latest"]["kind"] == "overview" and body["job"]["kind"] == "overview"
    pid = body["latest"]["id"]
    assert pid == body["job"]["id"]
    code, feed = _asgi("GET", "/api/plan")
    assert feed["job"] is None
    assert code == 200 and feed["history"][0]["id"] == pid and feed["latest"]["id"] == pid
    assert feed["history"][0]["kind"] == "overview"
    code, one = _asgi("GET", f"/api/plan/{pid}")
    assert code == 200 and one["latest"]["plan"]["headline"] == GOOD["headline"]
    code, gone = _asgi("DELETE", f"/api/plan/{pid}")
    assert code == 200 and gone["deleted"] is True and gone["history"] == []


def test_routes_validate_top_and_ids(routed: None) -> None:
    assert _asgi("POST", "/api/plan", "top=99")[0] == 422
    assert _asgi("POST", "/api/plan", "top=3")[0] == 422
    assert _asgi("GET", "/api/plan/not-an-id")[0] == 422
    assert _asgi("GET", "/api/plan/job/not-an-id")[0] == 422
    assert _asgi("GET", "/api/plan/job/20260101-000000")[1]["job"]["state"] == "lost"
    assert _asgi("DELETE", "/api/plan/..%2F..%2Fx")[0] in (404, 422)


# ---------------------------------------------------------------- macro per name


def _q(key: str, chg: float = 0.0, pct: float = 0.0) -> dict[str, Any]:
    return {"key": key, "chg": chg, "pct": pct}


def test_macro_moves_reads_rates_in_bp_and_the_rest_in_percent() -> None:
    m = sp.macro_moves([_q("US10Y", chg=0.031, pct=0.6), _q("WTI", pct=-1.84),
                        _q("SPY", pct=1.0)])
    assert m["US10Y"]["text"] == "+3bp" and m["US10Y"]["unit"] == "bp"
    assert m["WTI"]["text"] == "-1.84%"
    assert "SPY" not in m  # not a macro driver


def test_a_quote_that_has_stopped_gives_no_verdict() -> None:
    moves = sp.macro_moves([{**_q("US10Y", chg=-0.06), "feed": "closed"}, _q("DXY", pct=-0.5)])
    assert moves["US10Y"]["closed"] is True and "closed" not in moves["DXY"]
    tech = {d["driver"]: d for d in sp.macro_for("AAPL", "XLK", moves)}
    assert tech["US10Y"]["effect"] == "no live read"
    assert tech["US10Y"]["move"] == "-6bp at its last close"
    assert tech["DXY"]["effect"] in ("tailwind", "headwind")


def test_macro_for_gives_each_sector_its_drivers_and_the_verdict() -> None:
    moves = sp.macro_moves([_q("US10Y", chg=0.05), _q("DXY", pct=-0.1), _q("WTI", pct=-2.0),
                            _q("BTC", pct=3.5)])
    tech = {d["driver"]: d["effect"] for d in sp.macro_for("AAPL", "XLK", moves)}
    assert tech == {"US10Y": "headwind", "DXY": "flat"}  # yields up hurt; a 0.1% dollar is noise
    fin = {d["driver"]: d["effect"] for d in sp.macro_for("JPM", "XLF", moves)}
    assert fin == {"US10Y": "tailwind"}
    energy = {d["driver"]: d["effect"] for d in sp.macro_for("XOM", "XLE", moves)}
    assert energy == {"WTI": "headwind"}
    # A crypto-linked name answers to bitcoin, not to its sector.
    assert [d["driver"] for d in sp.macro_for("COIN", "XLF", moves)] == ["BTC"]
    assert sp.macro_for("COIN", "XLF", moves)[0]["effect"] == "tailwind"
    # No sector, no map — no invented driver.
    assert sp.macro_for("ZZZ", None, moves) == []


def test_macro_headlines_keeps_recent_high_impact_only() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 10, 13, 13, 0, tzinfo=UTC)
    wire = [
        {"impact": "high", "title": "Fed hikes", "publisher": "Reuters", "category": "policy",
         "utc": (now - timedelta(hours=1)).isoformat()},
        {"impact": "medium", "title": "Op-ed", "publisher": "FT", "category": "markets",
         "utc": (now - timedelta(minutes=5)).isoformat()},
        {"impact": "high", "title": "Old news", "publisher": "AP", "category": "macro",
         "utc": (now - timedelta(hours=20)).isoformat()},
    ]
    out = sp.macro_headlines(wire, now)
    assert [h["title"] for h in out] == ["Fed hikes"]
    assert out[0]["id"] == "m1" and out[0]["age_min"] == 60.0


def test_name_carries_sector_macro_headline_kinds_and_filings() -> None:
    row = {
        "sym": "AAPL", "ok": True, "sector": "XLK", "sector_rs": -1.16,
        "score": {"total": 40, "side": "long"}, "setup": {"state": "forming"}, "levels": {},
        "rs": {"SPY": 0.4},
        "news": [{"title": "Analyst upgrades Apple", "publisher": "Investing.com",
                  "kind": "rating", "url": "https://x", "age_min": 30}],
        "filings": [{"form": "8-K", "filed": "2026-10-12T20:01:00Z", "desc": "Item 2.02"}],
    }
    moves = sp.macro_moves([_q("US10Y", chg=0.03)])
    n = sp._name(row, moves, {"XLK": {"key": "XLK", "label": "Technology", "rs_day": -1.2}})
    assert n["sector"] == {"key": "XLK", "label": "Technology", "rs_day": -1.16}
    assert n["macro"][0]["driver"] == "US10Y" and n["macro"][0]["effect"] == "headwind"
    assert n["headlines"][0]["kind"] == "rating"
    assert n["filings"][0]["form"] == "8-K"


def test_index_etfs_get_their_own_drivers_not_a_guess() -> None:
    moves = sp.macro_moves([_q("US10Y", chg=-0.05), _q("DXY", pct=-0.37)])
    qqq = {d["driver"]: d["effect"] for d in sp.macro_for("QQQ", None, moves)}
    assert qqq == {"US10Y": "tailwind", "DXY": "tailwind"}
    assert [d["driver"] for d in sp.macro_for("IWM", None, moves)] == ["US10Y"]


def test_unread_news_is_flagged_not_called_quiet() -> None:
    row = {"sym": "NVDA", "ok": True, "score": {"total": 40, "side": "short"},
           "setup": {"state": "forming"}, "levels": {}, "rs": {}, "news": [],
           "news_loaded": False}
    assert sp._name(row)["news_loaded"] is False
    msgs = sp._partial({"status": {}}, [row])
    assert any("Headlines still loading" in m and "NVDA" in m for m in msgs)


# ------------------------------------------------- the tape count (conviction round)


def _tape(bias: str | None, grade: str, mx: int) -> dict[str, Any]:
    return {"bias": bias, "score": {"long": 35, "short": -35}.get(str(bias), 0), "coverage": 85,
            "agree": 0, "against": 0, "neutral": 0, "live": 8, "total": 11, "grade": grade,
            "max_conviction": mx, "votes": []}


def test_tape_line_states_the_score_and_the_caps() -> None:
    assert sp.tape_line(_tape("short", "moderate", 4)) == (
        "Tape score -35 (8 of 11 reads live, 85% of the weight): leans short, moderate — "
        "conviction is capped at 4, and at 3 for a plan against the short tape.")
    assert sp.tape_line(_tape(None, "none", 2)) == (
        "Tape score +0 (8 of 11 reads live, 85% of the weight): no lean — every plan's conviction "
        "is capped at 2.")
    assert sp.tape_line(None) == "Tape score: not available."


FLOW = {"call_vol": 5000, "put_vol": 2500, "pc_vol": 0.5, "call_oi": 40000, "put_oi": 30000,
        "vol_oi": 0.107, "lean": "calls",
        "top": [{"strike": 105.0, "right": "C", "expiry": "2026-10-16", "volume": 1800,
                 "oi": 4200}, {"strike": 100.0, "right": "P", "expiry": "2026-10-16",
                               "volume": 900, "oi": 3000}]}


def test_names_carry_flow_premarket_peers_and_adv() -> None:
    row = {**_row("AAA", 80, "long", options={**OPTS, "flow": FLOW}), "adv": 51234567.4,
           "premkt": {"volume": 812345.0, "pct_adv": 1.5856, "high": 102.0, "low": 100.0,
                      "last": 101.0, "asof": "08:45"},
           "peers": [{"sym": "BBB", "date": "2026-10-15", "when": "after", "days": 2}]}
    n = sp._name(row)
    assert n["flow"] == {"pc_vol": 0.5, "lean": "calls", "vol_oi": 0.11,
                         "top": {"strike": 105.0, "right": "C", "expiry": "2026-10-16",
                                 "volume": 1800, "oi": 4200}}
    assert n["premkt"] == {"volume": 812345, "pct_adv": 1.6} and n["adv"] == 51234567
    assert n["peers"] == [{"sym": "BBB", "date": "2026-10-15", "when": "after", "days": 2}]
    bare = sp._name(_row("CCC", 60, "long"))
    assert (bare["flow"], bare["premkt"], bare["peers"], bare["adv"]) == (None, None, [], None)


def test_facts_and_digest_carry_the_market_blocks() -> None:
    facts = sp.build_facts(_scan(), _snap(), top=4)
    for k in ("conviction", "breadth", "fuel", "prints", "fed", "gamma"):
        assert k in facts
    assert len(facts["conviction"]["votes"]) == 11
    d = sp.build_digest(facts)
    assert len(d["tape_count"]["reads"]) == 11 and d["tape_count"]["max_conviction"] == 2
    assert "note" not in json.dumps(d["tape_count"])  # the page's prose stays on the page
    assert d["gamma"] is None and d["fed"] is None


def test_a_raw_line_break_inside_a_string_still_parses_as_the_whole_plan() -> None:
    from newsterminal import report as rp
    text = '{"headline": "Short tape", "plans": [{"sym": "AAA", "why": ["Structure: a\nb"]}]}'
    assert "\n" in text
    obj = rp.extract_json(text)
    assert isinstance(obj, dict) and obj.get("headline") == "Short tape"


def test_failed_answer_keeps_both_ends() -> None:
    long = "{" + "x" * 5000 + "TAIL"
    kept = sp._ends(long)
    assert kept.startswith("{xxx") and kept.endswith("TAIL") and "chars]" in kept
    assert sp._ends("short") == "short"


def test_a_name_carries_its_side_of_the_ten_minute_200_ema() -> None:
    row = {"sym": "AMZN", "score": {"total": 77, "side": "short"}, "setup": {"state": "forming"},
           "levels": {"pdh": 249.14, "pdl": 241.24, "ema200": 243.05}, "trend200": -1,
           "ema200_slope": "falling", "rs": {}, "news": []}
    n = sp._name(row)
    assert n["ema200_10m"] == {"side": "below", "value": 243.05, "slope": "falling",
                               "with_side": "with"}                   # a short below the line
    assert sp._name({**row, "levels": {}})["ema200_10m"] is None
    assert n["ema200_daily"] is None                                   # no frame on the row
    framed = sp._name({**row, "frame_read": {"above200": True, "trend": "up", "text": "t"}})
    assert framed["ema200_daily"] == {"side": "above", "with_side": "against"}
    long_row = {**row, "score": {"total": 60, "side": "long"}}
    assert sp._name(long_row)["ema200_10m"]["with_side"] == "against"
