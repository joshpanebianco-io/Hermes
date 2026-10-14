"""
The backend review of 2026-10-13, finding by finding — each test is the failure
that was observed, made impossible to bring back quietly.
"""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
from typing import Any

import pytest

from newsterminal import http as http_mod
from newsterminal import report
from newsterminal.collector import Collector
from newsterminal.http import DiskCache, FetchResult, SourceStatus, csv_body, feed_body, json_body
from newsterminal.sources import constituents, quotes
from newsterminal.sources import scanner as scan_src
from newsterminal.sources.wire import is_local_crime

# --- 1. stale is said, not hidden ----------------------------------------------


class _Resp(io.BytesIO):
    status = 200

    def __init__(self, body: bytes) -> None:
        super().__init__(body)
        self.headers: dict[str, str] = {}

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *a: object) -> None:
        return None


@pytest.fixture
def cache(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> DiskCache:
    c = DiskCache(str(tmp_path))
    monkeypatch.setattr(http_mod, "CACHE", c)
    return c


def _serve(monkeypatch: pytest.MonkeyPatch, body: bytes | None) -> None:
    def fake(req: Any, timeout: int = 0) -> _Resp:
        if body is None:
            raise urllib.error.URLError("down")
        return _Resp(body)
    monkeypatch.setattr(http_mod.urllib.request, "urlopen", fake)


def test_a_dead_upstream_serves_the_copy_and_says_it_is_stale(
        cache: DiskCache, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, b'{"a": 1}')
    assert http_mod.fetch("http://x", key="k", ttl_sec=0).source == "live"
    _serve(monkeypatch, None)
    r = http_mod.fetch("http://x", key="k", ttl_sec=0)
    assert (r.ok, r.source) == (True, "stale")
    st = SourceStatus("Yahoo quotes")
    st.absorb(r)
    st.settle(True, "chunk")
    assert st.source == "stale" and st.error and "unreachable" in st.error
    assert st.stale_age_min is not None


def test_the_stale_copy_has_a_maximum_age(cache: DiskCache,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, b'{"a": 1}')
    http_mod.fetch("http://x", key="k", ttl_sec=0)
    p = cache.path("k")
    old = time.time() - 3600
    import os
    os.utime(p, (old, old))
    _serve(monkeypatch, None)
    r = http_mod.fetch("http://x", key="k", ttl_sec=0, stale_max_sec=600)
    assert r.ok is False and r.error and "too old" in r.error


def test_a_partial_fallback_dates_the_block_by_its_oldest_bytes() -> None:
    st = SourceStatus("Yahoo quotes")
    st.absorb(FetchResult(True, b"{}", "live", 0.0, None))
    st.absorb(FetchResult(True, b"{}", "stale", 12.0, "HTTP 503"))
    st.settle(True, "chunk")
    assert st.source == "live" and st.age_min == 12.0
    assert st.error and st.error.startswith("1 of 2 chunks")


def test_the_brief_banners_a_stale_source() -> None:
    snap = {"status": {"quotes": {"ok": True, "source": "stale", "stale_age_min": 14.0}},
            "quotes": []}
    out = report._partial(snap, ["NQ"])
    assert any("cached copy from 14 min ago" in x for x in out)


# --- 2 + 7. a bad 200 never replaces a good copy --------------------------------


def test_a_web_page_never_overwrites_the_csv(cache: DiskCache,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    good = b'Fondsposition per,"09.Okt.2026"\nEmittententicker,Name\n"NVDA","NVIDIA"\n'
    _serve(monkeypatch, good)
    http_mod.fetch("http://h", key="h", ttl_sec=0, validate=csv_body)
    _serve(monkeypatch, b"<!DOCTYPE html><html>iShares product page</html>")
    r = http_mod.fetch("http://h", key="h", ttl_sec=0, validate=constituents._holdings_body)
    assert (r.ok, r.source, r.body) == (True, "stale", good)
    assert r.error == "iShares served a web page, not the CSV"
    assert cache.read("h") == good


def test_validators_tell_a_page_from_a_payload() -> None:
    assert json_body(b'{"x":1}') is None and json_body(b"<html>") is not None
    assert feed_body(b'<?xml version="1.0"?><rss>') is None
    assert feed_body(b"<!doctype html><html>") is not None
    assert csv_body(b"a,b\n1,2") is None and csv_body(b"<html>") is not None


# --- 8. the CEO exemption ----------------------------------------------------------


def test_violence_against_a_ceo_is_not_dropped_as_local_crime() -> None:
    assert not is_local_crime("UnitedHealthcare CEO shot dead outside Manhattan hotel")
    assert not is_local_crime("Insurer CEO shot and killed in New York")


# --- 9. the numeral guard -------------------------------------------------------------


def test_numerals_match_on_value_not_spelling() -> None:
    assert report.numerals_in("30,707 and 30707, 1.10 and 1.1") == ["30707", "30707", "1.1", "1.1"]


def test_a_third_decimal_dropped_is_quoting_but_rounding_further_is_not() -> None:
    seen = "DXY 102.228 · 10Y 5.217 · VIX 15.19 · 10Y 4.96 · VAL 4170.5"
    brief = {"thesis": "Dollar 102.23, yield 5.22%, VIX 15.2, yield 5%, wrong above 4171",
             "calls": []}
    # 102.228 → 102.23 and 5.217 → 5.22 pass; the rest are what the guard is for.
    assert report.unverified(brief, seen) == ["15.2", "5", "4171"]
    # Half up, as a person rounds: 1.125 → 1.13.
    assert "1.13" in report.known_numerals("ratio 1.125")


def test_an_index_name_is_not_a_figure_but_its_price_still_is() -> None:
    assert report.numerals_in("tech lagging S&P 500 and the Russell 2000") == []
    assert report.numerals_in("Nasdaq-100, Euro Stoxx 50, Nikkei 225") == []
    assert report.numerals_in("Nasdaq 30,794 · S&P 500 at 7,871.5") == ["30794", "7871.5"]


def test_the_guard_names_a_rounded_and_an_invented_figure() -> None:
    brief = {"thesis": "Gold at 4,329.3, up 0.25%, eyeing 5% and 4400",
             "calls": [{"why": ["10Y at 4.96%"], "rest_of_day": "", "wrong_if": "above 4345"}]}
    assert report.unverified(brief, "gold 4329.3 +0.25% · 10Y 4.96 · flip 4345") == ["5", "4400"]


def test_generate_reasks_once_and_stores_what_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def answer(payload: dict[str, Any], key: str) -> dict[str, Any]:
        calls.append(len(payload["messages"]))
        thesis = "NQ at 9999.0" if len(calls) == 1 else "NQ holds 30707"
        body = json.dumps({
            "thesis": thesis,
            "calls": [{"book": "NQ", "open_bias": "bullish", "conviction": 3,
                       "rest_of_day": "x", "wrong_if": "y", "why": []}],
            "reads": [{"book": "NQ", "regime": "r"}],
        })
        return {"choices": [{"message": {"content": body}, "finish_reason": "stop"}]}

    monkeypatch.setattr(report, "_post", answer)
    monkeypatch.setattr(report, "_key", lambda: "k")
    monkeypatch.setattr(report, "_store", lambda rep: None)
    monkeypatch.setattr(report, "build_facts", lambda *a, **k: {
        "books": ["NQ"], "headlines": [], "snapshot": [], "catalysts": [], "rotation": {},
        "partial": [], "ladders": [], "gamma": [], "as_of": "now"})
    monkeypatch.setattr(report, "build_digest", lambda *a, **k: {"NQ": {"last": 30707}})
    rep = report.generate({"clock": {}}, asset="NQ")
    assert rep["ok"] is True
    assert len(calls) == 2  # the answer, then ONE re-ask
    assert rep["report"]["thesis"] == "NQ holds 30707"
    assert rep["unverified"] == []


# --- 10. the spark key ------------------------------------------------------------------


def test_the_spark_key_is_the_same_every_run() -> None:
    a = quotes.spark_key(["NQ=F", "ES=F"], "1d", "5m")
    assert a == "spark_1d_5m_" + __import__("hashlib").sha1(b"NQ=F,ES=F").hexdigest()[:12]
    assert a != quotes.spark_key(["ES=F", "NQ=F"], "1d", "5m")


def test_prune_removes_only_old_top_level_files(tmp_path: Any) -> None:
    import os
    c = DiskCache(str(tmp_path))
    c.write("old", b"x")
    c.write("new", b"y")
    c.write("scanner_events.jsonl", b"z")
    os.makedirs(os.path.join(str(tmp_path), "reports"))
    old = time.time() - 10 * 86400
    os.utime(c.path("old"), (old, old))
    os.utime(c.path("scanner_events.jsonl"), (old, old))
    assert c.prune(7 * 86400, keep=("scanner_events.jsonl",)) == 1
    assert c.read("old") is None and c.read("new") == b"y"
    assert os.path.isdir(os.path.join(str(tmp_path), "reports"))


# --- 4. the board pre-empts ------------------------------------------------------------


def test_quotes_runs_before_the_rest_of_a_pass() -> None:
    c = Collector.__new__(Collector)
    c._status, c._log_lock, c._logged_header = {}, threading.Lock(), True
    order: list[str] = []
    jobs: dict[str, Any] = {}
    now = time.monotonic()

    def q() -> None:
        order.append("quotes")

    def w() -> None:
        order.append("wire")
        # quotes falls due while the wire is fetching
        jobs["quotes"] = (q, 20.0, time.monotonic() - 1)

    def o() -> None:
        order.append("other")

    jobs.update({"quotes": (q, 20.0, now + 99), "wire": (w, 120.0, now - 1),
                 "other": (o, 60.0, now - 1)})
    while c._run_one(jobs):
        pass
    assert order == ["wire", "quotes", "other"]


# --- 5. backoff, and the quiet news tick -------------------------------------------------


def test_a_failing_symbol_backs_off_and_a_429_pauses_everything(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = scan_src.ScanStore(str(tmp_path / "w.json"))
    monkeypatch.setattr(scan_src, "fetch", lambda *a, **k: FetchResult(
        False, None, "unavailable", None, "HTTP 404", 404))
    t0 = time.time()
    assert "does not know" in (store._fetch_bars("ZZZZQX") or "")
    n, until = store.fails["ZZZZQX"]
    assert n == 1 and 25 <= until - t0 <= 35
    store._fetch_bars("ZZZZQX")
    assert store.fails["ZZZZQX"][0] == 2
    assert scan_src.backoff(10) == scan_src.BACKOFF_MAX
    monkeypatch.setattr(scan_src, "fetch", lambda *a, **k: FetchResult(
        False, None, "unavailable", None, "HTTP 429", 429))
    store._fetch_bars("AAPL")
    assert store.pause_until > time.time() + 60


def test_a_quiet_news_tick_is_healthy(tmp_path: Any) -> None:
    store = scan_src.ScanStore(str(tmp_path / "w.json"))
    now = time.time()
    for s in store.watchlist():
        store.news_at[s] = now  # nothing due
    st = store.tick_news()
    assert st.ok is True and st.error is None
