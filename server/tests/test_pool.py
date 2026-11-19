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
    # The move is full at 8 and past full earns a little more (2026-11-11): 1.67 ATR is
    # 4 x ln(1.67 / 0.75) / ln(4) = 2.3 over. The volume part is RVOL since 2026-11-13,
    # and with no time-of-day figure on the row (the session is over) it is the whole
    # day against an average one: 1.15 is 8 x ln(1.15 / 0.75) / ln(2 / 0.75) = 3.5. It
    # read 20.1 when 115% of a day was the full 8 and 1.8 over.
    assert (ko["score"], ko["gap_atr"], ko["vol_pct"], ko["rvol"]) == (13.8, 1.67, 114.88, 1.15)
    assert ko["reason"] == "moved 1.67 ATR · RVOL 1.15×"
    nvda = pool.in_play(rows["NVDA"], "day", td)
    # 0.21 ATR is 1.3; RVOL 0.76 is just past the first point's 0.75: 0.1. It read 10.4
    # when 76% of an average day was the full volume part.
    assert (nvda["score"], nvda["gap_atr"]) == (1.4, 0.21)
    assert pool.in_play({**rows["NVDA"], "rvol": None}, "day", td)["reason"] == (
        "moved 0.21 ATR · no RVOL read")
    assert pool.in_play(rows["KO"], "last", td)["reason"] == (
        "moved 1.67 ATR · last session RVOL 1.15×")
    sndk = pool.in_play(rows["SNDK"], "pre", td)
    assert (sndk["score"], sndk["gap_atr"], sndk["vol_pct"]) == (9.3, 0.34, 2.25)
    assert sndk["reason"] == "gap 0.34 ATR · pre-market 2.3% of ADV"
    orcl = pool.in_play(rows["ORCL"], "pre", td)
    assert orcl["score"] == 3.4 < pool.MIN_SCORE
    # no figures, no points — and the reason says which is missing
    bare = pool.in_play({"symbol": "X"}, "pre", td)
    assert bare["score"] == 0.0 and bare["reason"] == "no gap read · no pre-market volume"


@pytest.mark.parametrize(
    ("x", "full", "far", "want"),
    [(0.5, 0.75, 3.0, 0.0),      # under the full mark: nothing more
     (0.75, 0.75, 3.0, 0.0),
     (1.5, 0.75, 3.0, 2.0),      # halfway on the log scale
     (3.0, 0.75, 3.0, 4.0),
     (9.0, 0.75, 3.0, 4.0),      # and no further than the far mark
     (40.0, 40.0, 400.0, 0.0),
     (400.0, 40.0, 400.0, 4.0),
     (2.0, 2.0, 10.0, 0.0),       # RVOL: full at 2x, the far mark 10x
     (10.0, 2.0, 10.0, 4.0)],
)
def test_past_its_full_mark_a_part_earns_up_to_four_more(x: float, full: float, far: float,
                                                         want: float) -> None:
    assert pool.beyond(x, full, far) == pytest.approx(want)


def test_the_top_of_the_rank_separates_and_the_bar_does_not_move() -> None:
    td = date(2026, 11, 10)

    def name(sym: str, move_atr: float, vol_pct: float) -> dict[str, Any]:
        # A 2.0 ATR on a 100.00 close, so the move in ATRs is the change over 2.
        close = 100.0
        prev = close - move_atr * 2.0
        return {"symbol": sym, "close": close, "change": (close / prev - 1.0) * 100.0,
                "atr": 2.0, "avg_vol": 1e6, "volume": vol_pct * 1e4}

    # The evening of Tue 10 Nov: these three read 16.0 each (20 to 21 with their news
    # and levels) when both parts stopped at full. Their moves and volumes are theirs.
    # The session over, RVOL is the whole day: 4.17x, 3.12x and 0.89x. KKR's 0.89x was
    # the full 8 when 40% of an average day was full (17.6 then); now it is 1.4.
    gfl = pool.in_play(name("GFL", 2.21, 416.5), "day", td)["score"]
    nvda = pool.in_play(name("NVDA", 1.12, 311.7), "day", td)["score"]
    kkr = pool.in_play(name("KKR", 0.80, 88.5), "day", td)["score"]
    assert (gfl, nvda, kkr) == (20.9, 18.3, 9.5)
    # Under both full marks nothing changes, so who clears the bar is who cleared it:
    # a 0.4-ATR move alone is still 3.7, one short of MIN_SCORE.
    quiet = pool.in_play(name("Q", 0.40, 1.0), "day", td)["score"]
    assert quiet == 3.7 < pool.MIN_SCORE


def test_rank_reads_the_pre_market_before_the_bell_and_the_day_after() -> None:
    from newsterminal import scan

    q = pool.qualify(pool.parse(fixture())[0])
    pre = pool.rank(q, scan.clock_at(et(2026, 10, 23, 8, 0)))
    assert [r["symbol"] for r in pre[:3]] == ["KO", "SNDK", "MU"]
    assert pre[0]["reason"].startswith("gap ")
    day = pool.rank(q, scan.clock_at(et(2026, 10, 23, 11, 0)))
    # In the session the volume part reads the screener's time-of-day RVOL (the
    # fixture's column is the whole day's: the reply was taken after the close).
    assert [r["symbol"] for r in day[:3]] == ["KO", "SPCX", "TSM"]
    assert day[0]["rvol"] == 1.15
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
        # 06:00 and 07:00 since the Today list (2026-11-13): it ranks from 04:00.
        (et(2026, 10, 20, 5, 59), [], [], "06:00"),
        (et(2026, 10, 20, 6, 0), [], ["06:00"], "07:00"),
        (et(2026, 10, 20, 7, 59), ["06:00", "07:00"], [], "08:00"),
        (et(2026, 10, 20, 8, 0), ["06:00", "07:00"], ["08:00"], "09:00"),
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
    pinned = [f"P{i}" for i in range(28)]  # with the three benchmarks, nine slots
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
    pinned = [f"P{i}" for i in range(35)]  # with the three benchmarks, two slots
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
    # 05:50 Friday: a read and a rank, no mark yet
    st, read, changed = store.tick(pinned, et(2026, 10, 23, 5, 50))
    assert read and st.ok and st.items == 9 and not changed
    assert calls[0]["data"] and calls[0]["key"] == pool.CACHE_KEY
    assert store.for_scan() == (date(2026, 10, 23), [], {}, None)
    # 05:52: inside the cadence, no second read
    _st, read, _ = store.tick(pinned, et(2026, 10, 23, 5, 52))
    assert not read and len(calls) == 1
    # 06:01: the mark — the pre-market rank, pinned names and the quiet excluded
    st, read, changed = store.tick(pinned, et(2026, 10, 23, 6, 1))
    assert read and changed
    day, syms, sectors, favs = store.for_scan()
    assert day == date(2026, 10, 23)
    assert syms == ["KO", "SNDK", "MU", "TSM", "SPCX", "NBIS"]  # ORCL 3.4 under the bar
    # Both pins are tracked today (two of FAV_SLOTS), the more in play first.
    assert sorted(favs or []) == ["AAPL", "NVDA"]
    rows = {r["symbol"]: r for r in pool.parse(fixture())[0]}
    assert sectors == {s: pool.TV_SECTOR[rows[s]["tv_sector"]] for s in syms
                       if rows[s]["tv_sector"] in pool.TV_SECTOR}
    assert store.marks_done == ["06:00"]
    assert st.notes[0] == "14 screened · 9 qualified · 6 promoted · marks 06:00"
    v = store.view(pinned, et(2026, 10, 23, 6, 1))
    # The room: forty less the three benchmarks and the two favourites tracked today.
    assert v["on"] and v["slots"] == 35 and v["next_mark"] == "07:00" and v["basis"] == "pre"
    assert [p["symbol"] for p in v["promoted"]] == syms
    assert (v["promoted"][0]["mark"], v["promoted"][0]["at"]) == ("06:00", "06:01")
    assert [t["symbol"] for t in v["top"] if t["promoted"]] == syms
    assert "AAPL" not in [t["symbol"] for t in v["top"]]  # pinned names are never "not listed"
    # a restart keeps today's promotions
    again = pool.PoolStore(str(tmp_path / "pool.json"))
    assert again.for_scan()[1] == syms
    # the next trading day rolls them off
    _st, _read, changed = again.tick(pinned, et(2026, 10, 26, 5, 0))
    assert changed and again.for_scan() == (date(2026, 10, 26), [], {}, None)


def test_store_post_open_mark_fills_and_then_holds(monkeypatch: Any, tmp_path: Any) -> None:
    body = json.dumps(fixture()).encode()
    monkeypatch.setattr(pool, "fetch", lambda url, **kw: _live(body))
    store = pool.PoolStore(str(tmp_path / "pool.json"))
    # Thirty-one favourites tracked and the three benchmarks: six slots, two pre-market
    # and four at 10:00 (FAV_SLOTS is fifteen; raised here to pin the room down).
    monkeypatch.setattr(pool, "FAV_SLOTS", 31)
    pinned = [f"P{i}" for i in range(34)]
    store.tick(pinned, et(2026, 10, 23, 9, 26))
    assert store.for_scan()[1] == ["KO", "SNDK"]
    assert store.for_scan()[3] == pinned[:31]  # none in play, so the pinned order
    store.tick(pinned, et(2026, 10, 23, 10, 1))
    # The day-basis rank at 10:00 on RVOL (2026-11-13): SPCX 6.1, TSM 5.7, MU 4.8 clear
    # MIN_SCORE; NVDA, flat on 0.76x, does not (9.3 when a whole average day was the
    # yardstick), so the fourth slot stays empty.
    assert store.for_scan()[1] == ["KO", "SNDK", "SPCX", "TSM", "MU"]
    assert store.marks_done == ["06:00", "07:00", "08:00", "09:00", "09:25", "10:00"]
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
    assert store.for_scan()[1] and store.marks_done == ["06:00", "07:00", "08:00", "09:00"]
    assert store.set_enabled(False)
    assert store.for_scan()[1] == [] and not store.view([])["on"]
    assert not store.set_enabled(False)
    # back on: the next tick reads at once, inside the cadence, and re-runs today's latest mark
    assert store.set_enabled(True)
    _st, read, changed = store.tick([], et(2026, 10, 23, 9, 1))
    assert read and changed and store.marks_done == ["06:00", "07:00", "08:00", "09:00"]
    assert store.for_scan()[1]
    # and it survives a restart
    assert pool.PoolStore(str(tmp_path / "pool.json")).enabled


# --- the scanner's list takes them ---------------------------------------------


def test_scan_store_watchlist_is_pinned_plus_todays_promotions(tmp_path: Any) -> None:
    s = scan_src.ScanStore(str(tmp_path / "wl.json"))
    s.set_watchlist(["AAPL", "NVDA"])
    now = et(2026, 10, 23, 9, 0)
    bench = list(scan_src.BENCHMARKS)
    assert s.set_promoted(date(2026, 10, 23), ["KO", "AAPL", "SNDK"], {"SNDK": "XLK"})
    assert s.pinned() == ["AAPL", "NVDA"]
    # the benchmarks always head the list (2026-11-13); a favourite is not listed twice
    assert s.watchlist(now) == [*bench, "AAPL", "NVDA", "KO", "SNDK"]
    assert s.pool_sectors == {"SNDK": "XLK"}
    # at 20:00 the levels are Monday's, and Friday's promotions are not on the list
    assert s.watchlist(et(2026, 10, 23, 20, 0)) == [*bench, "AAPL", "NVDA"]
    # the cap holds: the benchmarks and thirty-six favourites leave one slot
    s.set_watchlist([f"A{i}" for i in range(36)])
    assert s.watchlist(now) == [*bench, *[f"A{i}" for i in range(36)], "KO"]
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


# --- Track: a name put on today's list by hand ------------------------------------


def _hand_store(tmp_path: Any) -> pool.PoolStore:
    return pool.PoolStore(path=str(tmp_path / "pool.json"))


def test_track_puts_a_name_on_todays_list_ahead_of_the_marks(tmp_path: Any) -> None:
    s = _hand_store(tmp_path)
    s.day = "2026-11-09"
    s.promoted = [{"symbol": "AAA", "score": 9.0, "reason": "gap", "at": "08:00", "mark": "08:00"}]
    assert s.track("ZZZ", "Zed", "XLK", "11:40", room=3) is None
    assert s.for_scan() == (date(2026, 11, 9), ["ZZZ", "AAA"], {"ZZZ": "XLK"}, None)
    # Tracking it again changes nothing.
    assert s.track("ZZZ", "Zed", "XLK", "11:41", room=3) is None
    assert s.for_scan()[1] == ["ZZZ", "AAA"]


def test_track_says_when_the_list_is_full(tmp_path: Any) -> None:
    s = _hand_store(tmp_path)
    assert "full" in str(s.track("ZZZ", None, None, "11:40", room=0))
    assert s.for_scan()[1] == []


def test_a_tracked_name_survives_the_marks_and_rolls_off_with_the_day(tmp_path: Any) -> None:
    s = _hand_store(tmp_path)
    s.day = "2026-11-09"
    s.track("ZZZ", None, None, "08:30", room=3)
    s.promoted = []                  # what a pre-market mark does: replaced whole
    assert s.for_scan()[1] == ["ZZZ"]
    assert s.view(["AAPL"])["promoted"][0]["mark"] == "hand"
    # And it is on disk, for a restart.
    assert pool.PoolStore(path=s._path).manual[0]["symbol"] == "ZZZ"
    assert s._roll(date(2026, 11, 10)) is True
    assert s.for_scan()[1] == []


# --- the funnel (2026-11-10) -----------------------------------------------------


def _row(sym: str = "X", **kw: Any) -> dict[str, Any]:
    base = {"symbol": sym, "close": 50.0, "change": 0.0, "volume": 1e6, "avg_vol": 1e6,
            "atr": 2.0, "cap": 3e9, "pm_change": 0.0, "pm_volume": 0.0, "pm_close": 50.0,
            "earn_next": None, "earn_last": None, "earn_last_when": None,
            "high": 51.0, "low": 49.0, "h1": 51.0, "l1": 49.0, "dollar_vol": 5e7,
            "atr_pct": 4.0, "delayed": True}
    return {**base, **kw}


def test_the_turnover_gate_reads_today_and_lets_a_strong_day_2_3_through() -> None:
    thin = _row("THIN")  # $50m on an average day: out on its average alone
    assert pool.qualify([thin], "pre") == []
    # $50m traded before the bell is in play today whatever the average says.
    busy = _row("BUSY", pm_volume=1.2e6, pm_close=50.0)
    assert [r["symbol"] for r in pool.qualify([thin, busy], "pre")] == ["BUSY"]
    # After the bell the day's turnover has to reach the full gate.
    assert pool.qualify([_row("DAY", volume=5e6)], "day") == []
    assert [r["symbol"] for r in pool.qualify([_row("DAY", volume=1.2e7)], "day")] == ["DAY"]
    # A strong Day 2/3 passes the turnover and ATR gates, never the price one.
    assert [r["symbol"] for r in pool.qualify([_row("D2", atr_pct=1.0)], "pre", {"D2"})] == ["D2"]
    assert pool.qualify([_row("CHEAP", close=9.0, pm_close=9.0)], "pre", {"CHEAP"}) == []


def test_outside_day_and_day_2_3_earn_their_points_and_say_so() -> None:
    td = date(2026, 11, 10)
    inside = pool.in_play(_row(), "pre", td)
    assert inside["score"] == 0.0 and inside["through"] is None and inside["day"] is None
    # Before the bell: the pre-market last against the last session's high and low.
    up = pool.in_play(_row(pm_close=51.5), "pre", td)
    # A 0.75-ATR gap earns the whole gap part, and the level two more.
    assert up["through"] == "PDH" and up["score"] == pytest.approx(inside["score"] + 8.0 + 2.0)
    assert up["reason"].endswith("through PDH")
    down = pool.in_play(_row(pm_close=48.5), "pre", td)
    assert down["through"] == "PDL"
    # After it: the day's last against the prior session's.
    day = pool.in_play(_row(close=52.0, change=4.0, h1=51.5), "day", td)
    assert day["through"] == "PDH"
    assert pool.in_play(_row(close=52.0, change=4.0, h1=52.5), "day", td)["through"] is None
    # A strong Day 2 earns three, a Day 3+ two, with the move in the reason.
    d2 = pool.in_play(_row(), "pre", td, stage={"stage": 2, "move": 24.3, "side": "long"})
    assert d2["score"] == 3.0 and d2["day"] == 2 and d2["reason"].endswith("day 2 of a +24% move")
    d3 = pool.in_play(_row(), "pre", td, stage={"stage": 4, "move": -31.0, "side": "short"})
    assert d3["score"] == 2.0 and d3["reason"].endswith("day 4 of a -31% move")


def test_rank_reads_the_strong_tracks_and_the_fixture_rows_are_all_inside() -> None:
    from newsterminal import scan

    q = pool.qualify(pool.parse(fixture())[0], "pre")
    strong = {"ORCL": {"stage": 2, "move": 22.0, "side": "long"}}
    ranked = pool.rank(q, scan.clock_at(et(2026, 10, 23, 8, 0)), strong=strong)
    orcl = next(r for r in ranked if r["symbol"] == "ORCL")
    # 3.4 on its own (under the bar), 6.4 as a Day 2: promoted.
    assert orcl["score"] == 6.4 and orcl["day"] == 2 and "day 2 of a +22% move" in orcl["reason"]
    assert all(r["through"] is None for r in ranked)


def test_the_verdict_says_what_the_engine_does_with_a_name_today() -> None:
    v = pool.verdict
    assert v(None, True, True)["state"] == "pinned"
    assert v({"score": 6.1, "reason": "r", "mark": "hand", "at": "08:12"}, False, True) == {
        "state": "hand", "score": 6.1, "reason": "r", "mark": None, "at": "08:12"}
    prom = v({"score": 7.0, "reason": "gap 1.2 ATR", "mark": "09:00", "at": "09:00"}, False, True)
    assert (prom["state"], prom["mark"]) == ("promoted", "09:00")
    assert v({"score": 7.0, "reason": "r"}, False, True)["state"] == "tracked"
    assert v({"score": 5.0, "reason": "r"}, False, False)["state"] == "inplay"
    assert v({"score": 3.9, "reason": "r"}, False, False)["state"] == "quiet"
    assert v(None, False, False) == {"state": "out", "score": None, "reason": None, "mark": None,
                                     "at": None}


def test_the_store_knows_each_names_place(monkeypatch: Any, tmp_path: Any) -> None:
    store = pool.PoolStore(path=str(tmp_path / "pool.json"))
    store.ranked = [{"symbol": "KO", "score": 16.0, "reason": "moved"}]
    store.by_sym = {r["symbol"]: r for r in store.ranked}
    store.promoted = [{"symbol": "KO", "score": 16.0, "reason": "moved", "mark": "09:00",
                       "at": "09:00"}]
    store.manual = [{"symbol": "GME", "score": 0.0, "reason": "tracked by hand", "mark": "hand",
                     "at": "08:12"}]
    assert store.entry("KO") == {"symbol": "KO", "score": 16.0, "reason": "moved",
                                 "mark": "09:00", "at": "09:00"}
    assert store.entry("GME")["mark"] == "hand" and store.entry("GME")["score"] == 0.0
    assert store.entry("NOPE") is None


# ---- one ticker a company (owner, 2026-11-19: "why do i see GOOG and GOOGL?") ----------


def test_share_classes_of_one_company_have_one_key_and_two_companies_two() -> None:
    assert pool.company_key("Alphabet Inc. Class C") == pool.company_key("Alphabet Inc. Class A")
    fox = pool.company_key("Fox Corporation Class B")
    assert fox == pool.company_key("Fox Corporation Class A")
    assert pool.company_key("Berkshire Hathaway Inc. Class B") == "berkshire hathaway inc"
    # A tracking stock keeps its tracker's name: Live and Formula One are two companies.
    live = pool.company_key("Liberty Media Corporation Series C Liberty Live")
    f1 = pool.company_key("Liberty Media Corporation Series C Liberty Formula One")
    assert live != f1
    assert live == pool.company_key("Liberty Media Corporation Series A Liberty Live")
    assert pool.company_key("Classic Rock Inc.") == "classic rock inc"   # a word, not a class
    assert pool.company_key(None) is None and pool.company_key("  ") is None


def _ranked(*rows: tuple[str, str, float]) -> list[dict[str, Any]]:
    return [{"symbol": s, "name": n, "score": sc, "gap_atr": 1.0} for s, n, sc in rows]


def test_the_pool_never_promotes_a_share_class_of_a_name_already_on_the_list() -> None:
    # 19 Nov 2026, 07:00 ET: GOOG ranked fourth (15.9) and was promoted beside GOOGL, which
    # the core holds for good. One company, two slots.
    ranked = _ranked(("PANW", "Palo Alto Networks, Inc.", 16.3),
                     ("GOOG", "Alphabet Inc. Class C", 15.9),
                     ("GOOGL", "Alphabet Inc. Class A", 15.7),
                     ("FOXA", "Fox Corporation Class A", 9.0),
                     ("FOX", "Fox Corporation Class B", 8.5))
    got = pool.promote(ranked, [], [], "07:00", favs=[], core=scan_src.CORE)
    assert [r["symbol"] for r in got] == ["PANW", "FOXA"]


def test_the_list_keeps_one_row_a_company_and_the_one_held_for_good() -> None:
    rows = [{"sym": "PANW", "name": "Palo Alto Networks, Inc."},
            {"sym": "GOOG", "name": "Alphabet Inc. Class C"},
            {"sym": "GOOGL", "name": "Alphabet Inc. Class A"},
            {"sym": "XYZ", "name": None}, {"sym": "XYZ2", "name": None}]
    got = pool.one_per_company(rows, sym_of=lambda r: r["sym"], prefer=set(scan_src.CORE))
    # GOOGL takes GOOG's place (fourth on the list, not fifth); unnamed rows are kept.
    assert [r["sym"] for r in got] == ["PANW", "GOOGL", "XYZ", "XYZ2"]
    # With neither held, the first of the two stays.
    assert [r["sym"] for r in pool.one_per_company(rows, sym_of=lambda r: r["sym"])][:2] == [
        "PANW", "GOOG"]
