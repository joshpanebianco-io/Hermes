"""
What the theme funds hold: the parser, the budget, and the American lines added by hand.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from newsterminal.sources import holdings as h
from newsterminal.sources.shortint import YahooSession

START = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)


def doc(*syms: str) -> dict[str, Any]:
    rows = [{"symbol": s, "holdingName": s, "holdingPercent": {"raw": 0.1}} for s in syms]
    return {"quoteSummary": {"result": [{"topHoldings": {"holdings": rows}}]}}


def test_the_parser_speaks_the_screeners_symbols() -> None:
    # A class share's dash becomes the screener's dot; a foreign line keeps its suffix,
    # which is why it can never match a US name.
    assert h.parse(doc("NVDA", "BRK-B", "3443.TW", "TECK-B.TO")) == [
        "NVDA", "BRK.B", "3443.TW", "TECK-B.TO"]


@pytest.mark.parametrize("bad", [{}, None, {"quoteSummary": {"result": []}}, doc()])
def test_a_reply_with_no_holdings_is_none(bad: Any) -> None:
    assert h.parse(bad) is None


class Disk:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def read(self, key: str) -> bytes | None:
        return self.blobs.get(key)

    def age_sec(self, key: str) -> float | None:
        return 60.0 if key in self.blobs else None

    def write(self, key: str, blob: bytes) -> None:
        self.blobs[key] = blob


class Session:
    def __init__(self) -> None:
        self.asked: list[str] = []
        self.answer: tuple[int, bytes] = (200, json.dumps(doc("AAA", "BBB")).encode())

    def summary(self, sym: str, module: str) -> tuple[int, bytes]:
        assert module == "topHoldings"
        self.asked.append(sym)
        return self.answer


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> h.HoldingsStore:
    monkeypatch.setattr(h, "CACHE", Disk())
    s = h.HoldingsStore()
    s.session = Session()  # type: ignore[assignment]
    return s


def test_one_fund_a_tick_then_nothing_for_a_week(store: h.HoldingsStore) -> None:
    for i in range(len(h.FUNDS)):
        st, read = store.tick(START + timedelta(seconds=30 * i))
        assert read and st.ok
    session: Any = store.session
    assert sorted(session.asked) == sorted(h.FUNDS)       # each once, none twice
    _, read = store.tick(START + timedelta(days=6))
    assert not read
    _, read = store.tick(START + timedelta(days=7, hours=1))
    assert read


def test_a_restart_reads_nothing_it_has_on_disk(store: h.HoldingsStore,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    disk = Disk()
    for f in h.FUNDS:
        disk.write(f"holdings_{f}", json.dumps(["AAA"]).encode())
    monkeypatch.setattr(h, "CACHE", disk)
    st, read = store.tick()
    session: Any = store.session
    assert not read and st.ok and st.items == len(h.FUNDS) and session.asked == []


def test_a_refusal_waits_and_a_rate_limit_pauses_everything(store: h.HoldingsStore) -> None:
    session: Any = store.session
    session.answer = (500, b"")
    st, read = store.tick(START)
    first = session.asked[-1]
    assert read and not st.ok and st.error and first in st.error
    # The next tick moves on to another fund rather than hammering the one that failed.
    store.tick(START + timedelta(seconds=30))
    assert session.asked[-1] != first
    session.answer = (429, b"")
    store.tick(START + timedelta(seconds=60))
    _, read = store.tick(START + timedelta(seconds=90))
    assert not read


def test_the_members_are_the_top_ten_and_the_american_lines(store: h.HoldingsStore) -> None:
    store.data = {"DRAM": ["005930.KQ", "000660.KQ"], "BOTZ": ["NVDA", "ISRG"]}
    got = store.members()
    assert got["BOTZ"] == {"NVDA", "ISRG"}
    assert {"MU", "WDC", "STX", "SNDK"} <= got["DRAM"]
    # A hand-listed fund has names before its first read; a plain one has none.
    assert "FXI" in got and "SKYY" not in got


def test_e_and_p_is_written_by_hand_and_never_asks_yahoo(store: h.HoldingsStore) -> None:
    got = store.members()["XOP"]
    assert {"COP", "EOG", "OXY", "DVN", "APA", "OVV", "PR"} <= got
    assert not got & {"XOM", "CVX", "MPC", "WDS", "PTEN"}     # majors, a refiner, foreign, services
    assert "XOP" not in h.FUNDS


def test_solar_reads_the_fund(store: h.HoldingsStore) -> None:
    assert "TAN" in h.FUNDS and "TAN" not in store.members()
    store.data = {"TAN": ["FSLR", "ENPH", "3800.HK"]}
    assert store.members()["TAN"] == {"FSLR", "ENPH", "3800.HK"}


def test_the_names_below_a_top_ten_wait_for_the_read(store: h.HoldingsStore) -> None:
    assert "QTUM" not in store.members()
    store.data = {"QTUM": ["IONQ"]}
    assert store.members()["QTUM"] == {"IONQ", "NVDA", "AMD", "MU", "INTC"}


class Pair(YahooSession):
    """The cookie and crumb, scripted."""

    def __init__(self, replies: list[tuple[int, bytes]], crumbs: list[str | None]) -> None:
        super().__init__()
        self.replies, self.crumbs, self.urls = replies, crumbs, []  # type: list[str]

    def crumb(self, refresh: bool = False) -> str | None:
        return self.crumbs.pop(0)

    def _get(self, url: str) -> tuple[int, bytes]:
        self.urls.append(url)
        return self.replies.pop(0)


def test_an_expired_crumb_is_fetched_again_once() -> None:
    s = Pair([(401, b""), (200, b"{}")], ["old", "new"])
    s._crumb = "new"
    assert s.summary("BRK.B", "topHoldings") == (200, b"{}")
    assert "BRK-B?modules=topHoldings&crumb=old" in s.urls[0]
    assert "crumb=new" in s.urls[1]


def test_no_crumb_is_no_request() -> None:
    s = Pair([], [None])
    assert s.summary("CIBR", "topHoldings") == (0, b"")
    assert s.urls == []
