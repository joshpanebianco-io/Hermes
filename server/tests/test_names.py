"""Per-name context on the scanner's rows: options flow, ADV, pre-market, sector peers."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

import pytest

from newsterminal import optcalc, scan, scanscore
from newsterminal.http import FetchResult
from newsterminal.optcalc import ET, Chain, Opt
from newsterminal.sources import options as opt_src
from newsterminal.sources import premarket as pm
from newsterminal.sources.scanner import SECTOR

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
TUE = date(2026, 10, 13)
WED = date(2026, 10, 14)


def et(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _doc(name: str) -> Any:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _chain(*opts: tuple[str, float, float, float]) -> Chain:
    """(right, strike, volume, oi) → a one-expiry chain."""
    return Chain("X", 100.0, 20.0, None, [TUE], {TUE: [
        Opt(symbol=f"X{r}{k}", expiry=TUE, right=r, strike=k, bid=1.0, ask=1.1, iv=0.2,
            delta=0.5, theta=-0.1, oi=oi, volume=v) for r, k, v, oi in opts]})


# --- options flow -------------------------------------------------------------------------


def test_flow_on_the_real_spy_chain() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    f = optcalc.options_flow(c)
    assert f is not None
    assert (f["call_vol"], f["put_vol"]) == (806250, 702040)
    assert (f["call_oi"], f["put_oi"]) == (753958, 596048)
    assert f["pc_vol"] == pytest.approx(0.871) and f["lean"] == "balanced"
    assert f["vol_oi"] == pytest.approx(1.117)
    # The busiest three, by volume: today's 0DTE straddle round spot.
    assert [(t["strike"], t["right"], t["expiry"]) for t in f["top"]] == [
        (777.0, "P", "2026-10-13"), (778.0, "P", "2026-10-13"), (778.0, "C", "2026-10-13")]
    assert f["top"][0] == {"strike": 777.0, "right": "P", "expiry": "2026-10-13",
                           "volume": 84852, "oi": 12096, "oi_chg": None}


def test_flow_on_the_real_aapl_chain_leans_to_calls() -> None:
    c = optcalc.parse_chain(_doc("cboe_aapl_trim.json"), "AAPL", TUE)
    f = optcalc.options_flow(c)
    assert f is not None and f["lean"] == "calls"
    assert f["pc_vol"] == pytest.approx(0.425) and f["vol_oi"] == pytest.approx(0.63)
    assert f["top"][0]["strike"] == 345.0 and f["top"][0]["right"] == "C"
    assert len(f["top"]) == 3


@pytest.mark.parametrize(("calls", "puts", "lean", "pc"), [
    (1000, 600, "calls", 0.6), (1000, 700, "balanced", 0.7), (1000, 1300, "balanced", 1.3),
    (1000, 1400, "puts", 1.4), (0, 500, "puts", None), (40, 40, None, 1.0), (0, 0, None, None),
])
def test_flow_lean_bands(calls: float, puts: float, lean: str | None, pc: float | None) -> None:
    f = optcalc.options_flow(_chain(("C", 100.0, calls, 5000.0), ("P", 100.0, puts, 5000.0)))
    assert f is not None and f["lean"] == lean and f["pc_vol"] == pc
    assert f["top"] == sorted(f["top"], key=lambda t: -t["volume"])
    assert all(t["volume"] > 0 for t in f["top"])


def test_flow_needs_contracts_and_open_interest() -> None:
    assert optcalc.options_flow(Chain("X", 100.0, None, None, [])) is None
    f = optcalc.options_flow(_chain(("C", 100.0, 500.0, 0.0), ("P", 100.0, 500.0, 0.0)))
    assert f is not None and f["vol_oi"] is None


def test_flow_rides_on_the_ctx_and_survives_a_restart() -> None:
    c = optcalc.parse_chain(_doc("cboe_spy_trim.json"), "SPY", TUE)
    row: dict[str, Any] = {"last": c.spot, "setup": {"side": "long"}, "score": {},
                           "levels": {}, "signals": []}
    ctx = optcalc.options_ctx(c, row, [], [], TUE, et(2026, 10, 13, 10, 0), 1.0)
    assert ctx["flow"] == optcalc.options_flow(c)
    # The compact summary already carried volume and OI per contract: an old file,
    # written before flow existed, gives the same flow once loaded.
    back = opt_src.load_chain(opt_src.dump_chain(c))
    assert back is not None and optcalc.options_flow(back) == ctx["flow"]
    assert optcalc.unavailable("x")["flow"] is None


def test_an_old_summary_on_disk_still_loads_with_its_flow() -> None:
    old = (b'{"sym":"QQQ","spot":600.0,"iv30":18.0,"asof":"2026-10-12T20:00:00+00:00",'
           b'"expiries":["2026-10-13"],"opts":{"2026-10-13":['
           b'["QQQ261013C00600000","C",600.0,1.0,1.1,0.2,0.5,-0.3,4000,3000],'
           b'["QQQ261013P00600000","P",600.0,1.0,1.1,0.2,-0.5,-0.3,6000,1500]]}}')
    c = opt_src.load_chain(old)
    assert c is not None
    f = optcalc.options_flow(c)
    assert f is not None and f["pc_vol"] == 0.5 and f["lean"] == "calls"
    assert f["vol_oi"] == pytest.approx(0.45)


# --- average daily volume -----------------------------------------------------------------


def test_adv20_averages_the_last_twenty_completed_sessions() -> None:
    vols = [1e6] * 5 + [2e6] * 20
    assert scanscore.adv20(vols) == 2e6
    assert scanscore.adv20([0.0, 3e6] + [1e6] * 19) == pytest.approx((3e6 + 19e6) / 20)
    assert scanscore.adv20([5e5] * 10) == 5e5
    assert scanscore.adv20([5e5] * 9) is None
    assert scanscore.adv20([5e5] * 9 + [0.0] * 5) is None


# --- pre-market: Nasdaq's page ------------------------------------------------------------


def test_parse_the_real_aapl_and_spy_pages() -> None:
    read, err = pm.parse(_doc("nasdaq_pre_aapl.json"))
    assert err is None and read == {
        "day": "2026-10-13", "asof": "2026-10-13T09:30:00-04:00", "volume": 690259,
        "high": 345.3, "low": 340.118, "last": 345.27}
    read, err = pm.parse(_doc("nasdaq_pre_spy.json"))
    assert err is None and read is not None
    assert (read["volume"], read["high"], read["low"], read["last"]) == (
        777110, 778.82, 776.51, 778.0117)


def test_parse_the_wrong_asset_class_and_broken_pages() -> None:
    assert pm.parse(_doc("nasdaq_pre_nosym.json")) == (None, pm.NOSYM)
    assert pm.parse([])[1] is not None
    page = _doc("nasdaq_pre_aapl.json")
    page["data"]["lastUpdateInfo"] = ["This page will resume updating soon."]
    read, err = pm.parse(page)
    assert read is None and err is not None and "which session" in err
    # A session with no prints yet is not an error and not a read.
    page = _doc("nasdaq_pre_aapl.json")
    page["data"]["infoTable"]["rows"] = [
        {"consolidated": "N/A", "volume": "", "highPrice": "N/A", "lowPrice": "N/A"}]
    assert pm.parse(page) == (None, None)
    page = _doc("nasdaq_pre_aapl.json")
    page["data"]["infoTable"]["rows"][0]["highPrice"] = "$300 (08:00:00 AM)"
    assert "below its low" in str(pm.parse(page)[1])


@pytest.mark.parametrize(("text", "want"), [
    ("Data last updated Oct 13, 2026 09:30 AM ET.", et(2026, 10, 13, 9, 30)),
    ("Data last updated Oct 14, 2026 12:05 PM ET.", et(2026, 10, 14, 12, 5)),
    ("Data last updated Oct 14, 2026 12:05 AM ET.", et(2026, 10, 14, 0, 5)),
    ("Data last updated Sept 2, 2026 4:01 AM ET.", et(2026, 9, 2, 4, 1)),
    ("nothing here", None),
])
def test_parse_updated(text: str, want: datetime | None) -> None:
    assert pm.parse_updated(text) == want


@pytest.mark.parametrize(("when", "phase"), [
    (et(2026, 10, 13, 3, 59), "idle"), (et(2026, 10, 13, 4, 0), "window"),
    (et(2026, 10, 13, 9, 34), "window"), (et(2026, 10, 13, 9, 35), "late"),
    (et(2026, 10, 13, 19, 59), "late"), (et(2026, 10, 13, 20, 0), "idle"),
    (et(2026, 11, 26, 7, 0), "idle"),     # Thanksgiving
    (et(2026, 11, 27, 16, 59), "late"), (et(2026, 11, 27, 17, 0), "idle"),  # half day
    (et(2026, 10, 17, 7, 0), "idle"),     # Saturday
])
def test_phase(when: datetime, phase: str) -> None:
    assert pm.phase(when) == phase


class _Cache:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def read(self, key: str) -> bytes | None:
        return self.blobs.get(key)

    def write(self, key: str, blob: bytes) -> None:
        self.blobs[key] = blob


def _page(day: date, hhmm: str = "09:30 AM", volume: str = "690,259") -> bytes:
    d = _doc("nasdaq_pre_aapl.json")
    d["data"]["lastUpdateInfo"][0] = f"Data last updated {day:%b} {day.day}, {day.year} {hhmm} ET."
    d["data"]["infoTable"]["rows"][0]["volume"] = volume
    return json.dumps(d).encode()


@pytest.fixture
def store(monkeypatch: Any) -> tuple[pm.PremarketStore, list[str], dict[str, Any]]:
    """A store whose fetch answers from `pages[sym]` — bytes, an int status, or NOSYM-by-class."""
    calls: list[str] = []
    pages: dict[str, Any] = {}

    def fake(url: str, **_kw: Any) -> FetchResult:
        calls.append(url)
        sym = url.split("/quote/")[1].split("/")[0]
        p = pages.get(sym)
        if isinstance(p, int):
            return FetchResult(False, None, "unavailable", None, f"HTTP {p}", p)
        if isinstance(p, dict):  # by asset class
            p = p.get(url.rsplit("assetclass=", 1)[1])
        if p is None:
            with open(os.path.join(FIX, "nasdaq_pre_nosym.json"), "rb") as f:
                return FetchResult(True, f.read(), "live", 0.0, None, 200)
        return FetchResult(True, p, "live", 0.0, None, 200)

    monkeypatch.setattr(pm, "fetch", fake)
    monkeypatch.setattr(pm, "CACHE", _Cache())
    return pm.PremarketStore(), calls, pages


def test_cadence_early_then_fast_then_the_final_read(store: Any) -> None:
    s, calls, pages = store
    pages["AAPL"] = _page(TUE, "06:00 AM")
    # 03:59: nothing. 04:00: due.
    assert s.tick(["AAPL"], et(2026, 10, 13, 3, 59)).ok and calls == []
    st = s.tick(["AAPL"], et(2026, 10, 13, 6, 0))
    assert st.ok and st.items == 1 and len(calls) == 1
    assert s.view(TUE)["AAPL"]["volume"] == 690259
    # Before 08:00 every ten minutes; after it every five.
    assert s.due(["AAPL"], et(2026, 10, 13, 6, 9)) == []
    assert s.due(["AAPL"], et(2026, 10, 13, 6, 10)) == ["AAPL"]
    s.tick(["AAPL"], et(2026, 10, 13, 8, 0))
    assert s.due(["AAPL"], et(2026, 10, 13, 8, 4)) == []
    assert s.due(["AAPL"], et(2026, 10, 13, 8, 5)) == ["AAPL"]
    # Read at 09:28: at 09:30 it is due again at once for the final figures.
    s.tick(["AAPL"], et(2026, 10, 13, 9, 28))
    assert s.due(["AAPL"], et(2026, 10, 13, 9, 29)) == []
    assert s.due(["AAPL"], et(2026, 10, 13, 9, 30)) == ["AAPL"]
    pages["AAPL"] = _page(TUE, "09:30 AM", "1,000,000")
    s.tick(["AAPL"], et(2026, 10, 13, 9, 31))
    assert s.view(TUE)["AAPL"]["volume"] == 1_000_000
    # Final: nothing more today, in the window or after it.
    assert s.due(["AAPL"], et(2026, 10, 13, 9, 34)) == []
    assert s.due(["AAPL"], et(2026, 10, 13, 12, 0)) == []


def test_kept_for_the_day_and_cleared_when_the_day_rolls(store: Any) -> None:
    s, calls, pages = store
    pages["AAPL"] = _page(TUE)
    s.tick(["AAPL"], et(2026, 10, 13, 9, 31))
    # The rest of Tuesday: held, and the scanner's day is still Tuesday.
    for when in (et(2026, 10, 13, 12, 0), et(2026, 10, 13, 19, 59)):
        assert scan.clock_at(when).trading_day == TUE and "AAPL" in s.view(TUE)
    # 20:00 rolls the scanner to Wednesday: no Tuesday pre-market on Wednesday's row.
    assert scan.clock_at(et(2026, 10, 13, 20, 0)).trading_day == WED
    assert s.view(WED) == {}
    st = s.tick(["AAPL"], et(2026, 10, 14, 3, 0))
    assert st.ok and st.items == 0 and "idle" in st.notes[0] and len(calls) == 1
    # 04:01 Wednesday: Nasdaq still serving Tuesday — not Wednesday's read.
    st = s.tick(["AAPL"], et(2026, 10, 14, 4, 1))
    assert len(calls) == 2 and s.view(WED) == {} and st.ok
    assert any("still serving 2026-10-13" in n for n in st.notes)
    # Its first Wednesday page is.
    pages["AAPL"] = _page(WED, "04:12 AM", "5,000")
    s.tick(["AAPL"], et(2026, 10, 14, 4, 12))
    assert s.view(WED)["AAPL"]["volume"] == 5000 and s.view(TUE) == {}


def test_holiday_and_weekend_read_nothing(store: Any) -> None:
    s, calls, pages = store
    pages["AAPL"] = _page(date(2026, 11, 25))
    st = s.tick(["AAPL"], et(2026, 11, 26, 8, 0))  # Thanksgiving
    assert calls == [] and st.ok
    s.tick(["AAPL"], et(2026, 10, 17, 8, 0))  # Saturday
    assert calls == []


def test_a_late_start_catches_up_a_few_times_at_most(store: Any) -> None:
    s, calls, pages = store
    pages["AAPL"] = _page(TUE, "09:16 AM")  # not final: Nasdaq a little behind
    s.tick(["AAPL"], et(2026, 10, 13, 12, 0))
    assert s.view(TUE)["AAPL"]["asof"] == "2026-10-13T09:16:00-04:00"
    for m in (5, 10, 15, 20, 25):
        s.tick(["AAPL"], et(2026, 10, 13, 12, m))
    assert len(calls) == pm.LATE_TRIES


def test_etf_class_and_the_flip(store: Any) -> None:
    s, calls, pages = store
    spy = json.dumps(_doc("nasdaq_pre_spy.json")).encode()
    pages["SPY"] = {"etf": spy}
    pages["NEWETF"] = {"etf": spy}
    s.tick(["SPY"], et(2026, 10, 13, 9, 31))
    assert calls[-1].endswith("assetclass=etf") and "SPY" in s.view(TUE)
    # An ETF the table does not know: stocks first, then etf on the next tick.
    st = s.tick(["NEWETF"], et(2026, 10, 13, 9, 31))
    assert calls[-1].endswith("assetclass=stocks") and st.error is None
    s.tick(["NEWETF"], et(2026, 10, 13, 9, 31))
    assert calls[-1].endswith("assetclass=etf") and "NEWETF" in s.view(TUE)
    # A symbol neither class knows backs off for good and says so.
    s.tick(["NOPE"], et(2026, 10, 13, 9, 31))
    st = s.tick(["NOPE"], et(2026, 10, 13, 9, 31))
    assert "lists no pre-market" in str(st.error) and s.due(["NOPE"], et(2026, 10, 13, 9, 32)) == []


def test_failures_back_off_and_a_429_pauses(store: Any) -> None:
    s, calls, pages = store
    pages["AAPL"] = 503
    st = s.tick(["AAPL"], et(2026, 10, 13, 8, 0))
    assert not st.ok and "Nasdaq" in str(st.error)
    assert s.due(["AAPL"], et(2026, 10, 13, 8, 0)) == []
    pages["MSFT"] = 429
    s.tick(["MSFT"], et(2026, 10, 13, 8, 0))
    n = len(calls)
    st = s.tick(["NVDA"], et(2026, 10, 13, 8, 1))
    assert len(calls) == n and any("paused" in x for x in st.notes)


def test_reads_persist_across_a_restart(store: Any, monkeypatch: Any) -> None:
    s, _calls, pages = store
    pages["AAPL"] = _page(TUE)
    s.tick(["AAPL"], et(2026, 10, 13, 9, 31))
    again = pm.PremarketStore()
    again.tick([], et(2026, 10, 13, 12, 0))
    assert again.view(TUE) == s.view(TUE)


# --- peers --------------------------------------------------------------------------------


def _earn(sym: str, day: str, when: str = "after", **kw: Any) -> dict[str, Any]:
    return {"symbol": sym, "date": day, "when": when, "market_cap": 1e12, **kw}


def test_peers_same_sector_big_caps_through_three_trading_days() -> None:
    rows = [
        _earn("TSM", "2026-10-15", "pre"),           # XLK, Thu: a peer
        _earn("ASML", "2026-10-14", "pre"),          # XLK, Wed: a peer, sooner
        _earn("NVDA", "2026-10-14"),                 # the name itself
        _earn("IONQ", "2026-10-14", watch_only=True),  # a small watchlist name: not a peer
        _earn("JPM", "2026-10-14", "pre"),           # another sector
        _earn("ZZZZ", "2026-10-14"),                 # no sector known
        _earn("INTC", "2026-10-19"),                 # Mon: four trading days on
        _earn("IBM", "2026-10-12"),                  # already past
    ]
    peers = scanscore.peers_for("NVDA", "XLK", rows, TUE, SECTOR)
    assert peers == [
        {"sym": "ASML", "date": "2026-10-14", "when": "pre", "days": 1},
        {"sym": "TSM", "date": "2026-10-15", "when": "pre", "days": 2},
    ]
    assert scanscore.peers_for("SPY", None, rows, TUE, SECTOR) == []
    assert scanscore.peers_for("GOOGL", "XLC", [_earn("GOOG", "2026-10-14")], TUE, SECTOR) == []


def test_peer_window_counts_trading_days_over_a_holiday() -> None:
    # Wed 25 Nov 2026: Thu is Thanksgiving, so +3 trading days is Tue 1 Dec.
    rows = [_earn("AMD", "2026-12-01"), _earn("AVGO", "2026-12-02")]
    peers = scanscore.peers_for("NVDA", "XLK", rows, date(2026, 11, 25), SECTOR)
    assert [p["sym"] for p in peers] == ["AMD"] and peers[0]["days"] == 6


def test_peer_flag_text() -> None:
    def p(sym: str, d: str) -> dict[str, Any]:
        return {"sym": sym, "date": d, "when": "pre", "days": 0}

    def text(peers: list[dict[str, Any]], td: date = TUE) -> str:
        f = scanscore.peer_flag(peers, td)
        assert f is not None and f["kind"] == "earnings" and f["tone"] == "info"
        return str(f["text"])

    assert scanscore.peer_flag([], TUE) is None
    assert text([p("TSM", "2026-10-15")]) == "Peer TSM reports Thu"
    assert text([p("TSM", "2026-10-13")]) == "Peer TSM reports today"
    assert text([p("ASML", "2026-10-14"), p("TSM", "2026-10-15")]) == \
        "Peer ASML reports tomorrow +1"
    # Friday → Monday is "Mon", not "tomorrow".
    assert text([p("TSM", "2026-10-19")], date(2026, 10, 16)) == "Peer TSM reports Mon"


# --- the join -----------------------------------------------------------------------------


def _ok_row(sym: str, sector: str | None) -> dict[str, Any]:
    r = scanscore._empty(sym, 1.0, "test")
    r.update({"ok": True, "error": None, "sector": sector, "last": 100.0})
    r.pop("adv20")
    return r


def _common(watch: list[str]) -> dict[str, Any]:
    now = et(2026, 10, 13, 8, 0)
    return dict(quotes=[], sectors=[], calendar=[], wire=[], news={}, filings={}, aliases={},
                status=None, watchlist=watch, clock=scan.clock_at(now), now=now)


def test_join_with_every_new_field_absent() -> None:
    p = scanscore.build({"rows": {"NVDA": _ok_row("NVDA", "XLK")}}, earnings=[],
                        **_common(["NVDA", "AAPL"]))
    rows = {r["sym"]: r for r in p["rows"]}
    nv = rows["NVDA"]
    assert nv["adv20"] is None and nv["premkt"] is None and nv["peers"] == []
    assert nv["options"] is None and not any(f["text"].startswith("Peer") for f in nv["flags"])
    # A name with no bars yet still carries the keys.
    assert rows["AAPL"]["adv20"] is None and rows["AAPL"]["premkt"] is None
    assert rows["AAPL"]["peers"] == []


def test_join_with_every_new_field_present() -> None:
    base = _ok_row("NVDA", "XLK")
    base["adv20"] = 200_000_000.0
    read = {"volume": 5_000_000, "high": 190.0, "low": 185.0, "last": 189.0,
            "asof": "2026-10-13T07:55:00-04:00"}
    p = scanscore.build({"rows": {"NVDA": base}}, earnings=[_earn("TSM", "2026-10-15", "pre")],
                        premkt={"NVDA": read}, sector_map=SECTOR, **_common(["NVDA"]))
    nv = p["rows"][0]
    assert nv["adv20"] == 200_000_000.0
    assert nv["premkt"] == {**read, "pct_adv": 2.5}
    assert nv["peers"] == [{"sym": "TSM", "date": "2026-10-15", "when": "pre", "days": 2}]
    assert nv["flags"][-1] == {"kind": "earnings", "tone": "info", "text": "Peer TSM reports Thu"}


def test_premkt_without_an_adv_has_no_share() -> None:
    read = {"volume": 1000, "high": 1.0, "low": 1.0, "last": 1.0, "asof": "x"}
    assert scanscore.premkt_for(read, None) == {**read, "pct_adv": None}
    assert scanscore.premkt_for(None, 1e6) is None
    none = scanscore.premkt_for({**read, "volume": None}, 1e6)
    assert none is not None and none["pct_adv"] is None
