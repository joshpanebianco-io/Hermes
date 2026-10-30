"""
The pool — the wide read in front of the scanner's list (sources/pool.py).

The fixture is fifteen rows of TradingView's reply on 24 Oct 2026 (Friday the
23rd's figures), chosen for the edges: a preferred line (GOOGN), two DRs (TSM,
GGB), BRK.B, and a name under each gate. Every figure asserted here was read
off that file by hand first — the worked examples in the module are the same
numbers — so a change to the arithmetic has to say which number it moved.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, ClassVar

import pytest

from newsterminal import http as http_mod
from newsterminal.http import FetchResult
from newsterminal.scan import ET
from newsterminal.sources import pool
from newsterminal.sources import scanner as scan_src

HERE = os.path.dirname(__file__)


def fixture() -> dict[str, Any]:
    with open(os.path.join(HERE, "fixtures", "tv_pool_trim.json"), encoding="utf-8") as f:
        return json.load(f)


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# --- parsing and the gates -----------------------------------------------------


def test_parse_keeps_common_lines_and_drs_and_drops_preferred() -> None:
    rows, err = pool.parse(fixture())
    assert err is None
    syms = [r["symbol"] for r in rows]
    assert "GOOGN" not in syms  # the preferred line carrying Alphabet's cap
    assert "TSM" in syms and "GGB" in syms  # depositary receipts stay
    assert "BRK.B" in syms  # not the primary line, still a common one
    assert len(rows) == 14
    tsm = next(r for r in rows if r["symbol"] == "TSM")
    assert tsm["dr"] is True
    assert (tsm["earn_last"], tsm["earn_last_when"]) == ("2026-10-15", "pre")
    spcx = next(r for r in rows if r["symbol"] == "SPCX")
    # 1792526700 is 20 Oct 16:05 ET — the report's own instant, after the close
    assert (spcx["earn_last"], spcx["earn_last_when"]) == ("2026-10-20", "after")
    assert spcx["earn_next"] == "2027-02-25"
    assert all(r["delayed"] for r in rows)


def test_parse_refuses_the_wrong_shape() -> None:
    assert pool.parse({"data": "nope"}) == ([], "no data array in the reply")
    assert pool.parse([]) == ([], "no data array in the reply")
    rows, _ = pool.parse({"data": [{"s": "X", "d": [1, 2]}]})
    assert rows == []


def test_pool_body_validator() -> None:
    assert pool.pool_body(b"<html>") is not None
    assert pool.pool_body(b'{"x": 1}') == "not a screener reply"
    assert pool.pool_body(b'{"totalCount": 1, "data": []}') is None


def test_gates() -> None:
    q = {r["symbol"] for r in pool.qualify(pool.parse(fixture())[0])}
    assert q == {"NVDA", "AAPL", "SPCX", "TSM", "MU", "KO", "ORCL", "SNDK", "NBIS"}
    # BRK.B: ATR 1.19% · GME and HIMS: $260m and $280m a day · GGB and STLA: under $10
    assert {"BRK.B", "GME", "HIMS", "GGB", "STLA"}.isdisjoint(q)


# --- the rank ------------------------------------------------------------------


def test_in_play_worked_examples() -> None:
    rows = {r["symbol"]: r for r in pool.parse(fixture())[0]}
    td = date(2026, 10, 23)
    ko = pool.in_play(rows["KO"], "day", td)
    assert (ko["score"], ko["gap_atr"], ko["vol_pct"]) == (16.0, 1.67, 114.88)
    assert ko["reason"] == "moved 1.67 ATR · today 114.9% of ADV"
    nvda = pool.in_play(rows["NVDA"], "day", td)
    assert (nvda["score"], nvda["gap_atr"]) == (9.3, 0.21)
    sndk = pool.in_play(rows["SNDK"], "pre", td)
    assert (sndk["score"], sndk["gap_atr"], sndk["vol_pct"]) == (9.3, 0.34, 2.25)
    assert sndk["reason"] == "gap 0.34 ATR · pre-market 2.3% of ADV"
    orcl = pool.in_play(rows["ORCL"], "pre", td)
    assert orcl["score"] == 3.4 < pool.MIN_SCORE
    # no figures, no points — and the reason says which is missing
    bare = pool.in_play({"symbol": "X"}, "pre", td)
    assert bare["score"] == 0.0 and bare["reason"] == "no gap read · no pre-market volume"


def test_rank_reads_the_pre_market_before_the_bell_and_the_day_after() -> None:
    from newsterminal import scan

    q = pool.qualify(pool.parse(fixture())[0])
    pre = pool.rank(q, scan.clock_at(et(2026, 10, 23, 8, 0)))
    assert [r["symbol"] for r in pre[:3]] == ["KO", "SNDK", "MU"]
    assert pre[0]["reason"].startswith("gap ")
    day = pool.rank(q, scan.clock_at(et(2026, 10, 23, 11, 0)))
    assert [r["symbol"] for r in day[:3]] == ["KO", "TSM", "MU"]
    assert day[0]["reason"].startswith("moved ")
    # the weekend ranks for Monday, on the last session's figures
    sat = pool.rank(q, scan.clock_at(et(2026, 10, 24, 10, 0)))
    assert "last session" in sat[0]["reason"]
    nbis = next(r for r in sat if r["symbol"] == "NBIS")
    assert nbis["reports"] == "reports today"  # due Monday 26 Oct
    assert pre[0]["sector"] == "XLP"  # KO: Consumer Non-Durables
    assert next(r for r in pre if r["symbol"] == "SNDK")["sector"] == "XLK"


def test_report_read() -> None:
    td = date(2026, 10, 21)  # a Wednesday
    assert pool.report_read({"earn_last": "2026-10-20", "earn_last_when": "after"}, td) \
        == "reported last night"
    assert pool.report_read({"earn_last": "2026-10-21", "earn_last_when": "pre"}, td) \
        == "reported this morning"
    # after today's close: it gaps tomorrow, not today
    assert pool.report_read({"earn_last": "2026-10-21", "earn_last_when": "after"}, td) is None
    assert pool.report_read({"earn_next": "2026-10-21"}, td) == "reports today"
    assert pool.report_read({"earn_last": "2026-10-20", "earn_last_when": "pre"}, td) \
        == "reported yesterday"
    # Monday: Friday's after-the-close report is last night's
    assert pool.report_read({"earn_last": "2026-10-23", "earn_last_when": "after"},
                            date(2026, 10, 26)) == "reported last night"
    assert pool.report_read({}, td) is None
    assert pool.W_REPORT < pool.MIN_SCORE  # a report alone never promotes


# --- the marks and the clock ---------------------------------------------------


@pytest.mark.parametrize(
    ("instant", "done", "due", "nxt"),
    [
        (et(2026, 10, 20, 7, 59), [], [], "08:00"),
        (et(2026, 10, 20, 8, 0), [], ["08:00"], "09:00"),
        (et(2026, 10, 20, 9, 30), [], ["09:25"], "10:00"),
        (et(2026, 10, 20, 10, 5), ["08:00", "09:00", "09:25"], ["10:00"], None),
        (et(2026, 10, 20, 14, 0), [], ["09:25", "10:00"], None),
        (et(2026, 10, 20, 20, 0), [], [], None),  # the day has rolled
        (et(2026, 10, 20, 3, 30), [], [], None),  # the day's, but closed
        (et(2026, 10, 24, 9, 0), [], [], None),  # Saturday
    ],
)
def test_marks(instant: datetime, done: list[str], due: list[str], nxt: str | None) -> None:
    assert pool.marks_due(instant, done) == due
    assert pool.next_mark(instant, done) == nxt


def test_cadence() -> None:
    assert pool.cadence(et(2026, 10, 20, 4, 0)) == pool.ACTIVE_SEC
    assert pool.cadence(et(2026, 10, 20, 10, 29)) == pool.ACTIVE_SEC
    assert pool.cadence(et(2026, 10, 20, 10, 30)) == pool.IDLE_SEC
    assert pool.cadence(et(2026, 10, 24, 9, 0)) == pool.IDLE_SEC


# --- promotion -----------------------------------------------------------------


def ranked(n: int, score: float = 10.0) -> list[dict[str, Any]]:
    return [{"symbol": f"S{i:02d}", "score": round(score - i * 0.1, 1), "gap_atr": 1.0,
             "reason": "x"} for i in range(n)]


def test_promote_pre_marks_leave_room_for_the_open() -> None:
    pinned = [f"P{i}" for i in range(31)]  # nine slots
    got = pool.promote(ranked(30), pinned, [], "08:00")
    assert [g["symbol"] for g in got] == ["S00", "S01", "S02", "S03", "S04"]  # 9 − 4
    post = pool.promote(ranked(30), pinned, got, "10:00")
    assert [g["symbol"] for g in post] == [f"S{i:02d}" for i in range(9)]


def test_promote_excludes_pinned_benchmarks_and_the_quiet() -> None:
    rk = [{"symbol": "SPY", "score": 15.0, "gap_atr": 1.0, "reason": ""},
          {"symbol": "AAPL", "score": 12.0, "gap_atr": 1.0, "reason": ""},
          {"symbol": "KO", "score": 9.0, "gap_atr": 1.0, "reason": ""},
          {"symbol": "ORCL", "score": 3.4, "gap_atr": 0.1, "reason": ""}]
    assert [g["symbol"] for g in pool.promote(rk, ["AAPL"], [], "09:25")] == ["KO"]


def test_promote_post_open_never_drops_and_respects_the_cap() -> None:
    pinned = [f"P{i}" for i in range(38)]  # two slots
    cur = [{"symbol": "OLD", "score": 4.0, "gap_atr": 0.5, "reason": ""}]
    assert [g["symbol"] for g in pool.promote(ranked(5), pinned, cur, "10:00")] == ["OLD", "S00"]
    full = [f"P{i}" for i in range(40)]
    assert pool.promote(ranked(5), full, cur, "10:00") == []
    assert pool.promote(ranked(5), full, [], "08:00") == []


# --- the store, on a fake fetch ------------------------------------------------


def _live(body: bytes) -> FetchResult:
    return FetchResult(True, body, "live", 0.0, None, 200)


def test_store_reads_ranks_and_promotes_at_a_mark(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(fixture()).encode()
    calls: list[dict[str, Any]] = []

    def fake(url: str, **kw: Any) -> FetchResult:
        calls.append(kw)
        return _live(body)

    monkeypatch.setattr(pool, "fetch", fake)
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    pinned = ["AAPL", "NVDA"]
    # 07:50 Friday: a read and a rank, no mark yet
    st, read, changed = store.tick(pinned, et(2026, 10, 23, 7, 50))
    assert read and st.ok and st.items == 9 and not changed
    assert calls[0]["data"] and calls[0]["key"] == pool.CACHE_KEY
    assert store.for_scan() == (date(2026, 10, 23), [], {})
    # 07:52: inside the cadence, no second read
    _st, read, _ = store.tick(pinned, et(2026, 10, 23, 7, 52))
    assert not read and len(calls) == 1
    # 08:01: the mark — the pre-market rank, pinned names and the quiet excluded
    st, read, changed = store.tick(pinned, et(2026, 10, 23, 8, 1))
    assert read and changed
    day, syms, sectors = store.for_scan()
    assert day == date(2026, 10, 23)
    assert syms == ["KO", "SNDK", "MU", "TSM", "SPCX", "NBIS"]  # ORCL 3.4 under the bar
    rows = {r["symbol"]: r for r in pool.parse(fixture())[0]}
    assert sectors == {s: pool.TV_SECTOR[rows[s]["tv_sector"]] for s in syms
                       if rows[s]["tv_sector"] in pool.TV_SECTOR}
    assert store.marks_done == ["08:00"]
    assert st.notes[0] == "14 screened · 9 qualified · 6 promoted · marks 08:00"
    v = store.view(pinned, et(2026, 10, 23, 8, 1))
    assert v["on"] and v["slots"] == 38 and v["next_mark"] == "09:00" and v["basis"] == "pre"
    assert [p["symbol"] for p in v["promoted"]] == syms
    assert (v["promoted"][0]["mark"], v["promoted"][0]["at"]) == ("08:00", "08:01")
    assert [t["symbol"] for t in v["top"] if t["promoted"]] == syms
    assert "AAPL" not in [t["symbol"] for t in v["top"]]  # pinned names are never "not listed"
    # a restart keeps today's promotions
    again = pool.PoolStore(str(tmp_path / "pool.json"))
    assert again.for_scan()[1] == syms
    # the next trading day rolls them off
    _st, _read, changed = again.tick(pinned, et(2026, 10, 26, 5, 0))
    assert changed and again.for_scan() == (date(2026, 10, 26), [], {})


def test_store_post_open_mark_fills_and_then_holds(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(fixture()).encode()
    monkeypatch.setattr(pool, "fetch", lambda url, **kw: _live(body))
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    pinned = [f"P{i}" for i in range(34)]  # six slots: two pre-market, four at 10:00
    store.tick(pinned, et(2026, 10, 23, 9, 26))
    assert store.for_scan()[1] == ["KO", "SNDK"]
    store.tick(pinned, et(2026, 10, 23, 10, 1))
    # the day-basis rank at 10:00: TSM 12.7, MU 12.2, SPCX 10.9, then NVDA 9.3 ahead of NBIS 8.0
    assert store.for_scan()[1] == ["KO", "SNDK", "TSM", "MU", "SPCX", "NVDA"]
    assert store.marks_done == ["08:00", "09:00", "09:25", "10:00"]
    kept = [dict(p) for p in store.promoted]
    # a later read changes nothing: the list holds until the day rolls
    store.tick(pinned, et(2026, 10, 23, 14, 0))
    assert store.promoted == kept


def test_store_stale_copy_ranks_but_never_promotes(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(fixture()).encode()
    monkeypatch.setattr(pool, "fetch",
                        lambda url, **kw: FetchResult(True, body, "stale", 45.0, "HTTP 503", 503))
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    st, read, _ = store.tick([], et(2026, 10, 23, 9, 26))
    assert read and st.ok and st.source == "stale" and store.ranked
    assert store.for_scan()[1] == [] and store.marks_done == []
    assert store.view([])["source"] == "stale"


def test_store_pauses_on_a_refusal(monkeypatch: Any, tmp_path: Any) -> None:
    refused = FetchResult(False, None, "unavailable", None, "HTTP 429", 429)
    monkeypatch.setattr(pool, "fetch", lambda url, **kw: refused)
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    st, read, _ = store.tick([], et(2026, 10, 23, 8, 0))
    assert read and not st.ok and "HTTP 429" in (st.error or "")
    st, read, _ = store.tick([], et(2026, 10, 23, 8, 6))
    assert not read and any("paused" in n for n in st.notes)


def test_switching_promotion_off_and_on(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(fixture()).encode()
    monkeypatch.setattr(pool, "fetch", lambda url, **kw: _live(body))
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    store.tick([], et(2026, 10, 23, 9, 0))
    assert store.for_scan()[1] and store.marks_done == ["08:00", "09:00"]
    assert store.set_enabled(False)
    assert store.for_scan()[1] == [] and not store.view([])["on"]
    assert not store.set_enabled(False)
    # back on: the next tick reads at once, inside the cadence, and re-runs today's latest mark
    assert store.set_enabled(True)
    _st, read, changed = store.tick([], et(2026, 10, 23, 9, 1))
    assert read and changed and store.marks_done == ["08:00", "09:00"] and store.for_scan()[1]
    # and it survives a restart
    assert pool.PoolStore(str(tmp_path / "pool.json")).enabled


# --- the scanner's list takes them ---------------------------------------------


def test_scan_store_watchlist_is_pinned_plus_todays_promotions(tmp_path: Any) -> None:
    s = scan_src.ScanStore(str(tmp_path / "wl.json"))
    s.set_watchlist(["AAPL", "NVDA"])
    now = et(2026, 10, 23, 9, 0)
    assert s.set_promoted(date(2026, 10, 23), ["KO", "AAPL", "SNDK"], {"SNDK": "XLK"})
    assert s.pinned() == ["AAPL", "NVDA"]
    assert s.watchlist(now) == ["AAPL", "NVDA", "KO", "SNDK"]  # a pinned name is not listed twice
    assert s.pool_sectors == {"SNDK": "XLK"}
    # at 20:00 the levels are Monday's, and Friday's promotions are not on the list
    assert s.watchlist(et(2026, 10, 23, 20, 0)) == ["AAPL", "NVDA"]
    # the cap holds: thirty-nine pinned leaves one slot
    s.set_watchlist([f"A{i}" for i in range(39)])
    assert s.watchlist(now) == [f"A{i}" for i in range(39)] + ["KO"]
    assert not s.set_promoted(date(2026, 10, 23), ["KO", "AAPL", "SNDK"], {})  # unchanged


# --- http: a POST --------------------------------------------------------------


def test_fetch_posts_when_given_a_body(monkeypatch: Any, tmp_path: Any) -> None:
    seen: dict[str, Any] = {}

    class Reply:
        status = 200
        headers: ClassVar[dict[str, str]] = {}

        def __enter__(self) -> Reply:
            return self

        def __exit__(self, *a: Any) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"totalCount": 0, "data": []}'

    def urlopen(req: Any, timeout: int = 0) -> Reply:
        seen["method"] = req.get_method()
        seen["data"] = req.data
        seen["ct"] = req.get_header("Content-type")
        return Reply()

    monkeypatch.setattr(http_mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(http_mod, "CACHE", http_mod.DiskCache(str(tmp_path)))
    r = http_mod.fetch("https://example.invalid/scan", key="t_post", ttl_sec=0.0, data=b'{"a":1}',
                       headers={"Content-Type": "application/json"})
    assert r.ok and seen == {"method": "POST", "data": b'{"a":1}', "ct": "application/json"}
    with pytest.raises(ValueError):
        http_mod.fetch("https://example.invalid/scan", data=b"x")
