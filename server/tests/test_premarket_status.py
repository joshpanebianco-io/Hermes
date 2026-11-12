"""
What the status rail says of the pre-market source when Nasdaq is not answering
(sources/premarket.py `covered_by_screener`).

Worked on Wed 11 Nov 2026: Nasdaq refused every read from the collector's start, the
rail said "PREMARKET never" in red all morning, and every figure that source feeds
was on the page from TradingView's screener.
"""

from __future__ import annotations

from newsterminal.http import SourceStatus
from newsterminal.sources import premarket


def _refused() -> SourceStatus:
    """The status `PremarketStore.tick` returned that morning."""
    st = SourceStatus("Nasdaq pre-market")
    st.error = "SPY: HTTP 403"
    st.settle(False, what="read")
    st.notes = ["0 of 34 read for 2026-11-11 · 0 fetched, 33 due",
                "no read yet: SPY, QQQ, IWM, AMD, SPCX…",
                "Nasdaq refused (403/429) — paused until 07:09:11 ET"]
    return st


def test_refused_by_nasdaq_but_covered_by_the_screener_is_a_live_source() -> None:
    st = premarket.covered_by_screener(_refused(), covered=32, total=34)
    d = st.as_dict()
    # What the rail folds into "N of N sources live": ok, and not a stale copy.
    assert (d["ok"], d["source"], d["items"]) == (True, "live", 32)
    assert d["last_ok_utc"] is not None
    # No error to print beside a live source; whose figures they are comes first,
    # and Nasdaq's own account of itself is still there to read.
    assert d["error"] is None
    assert d["notes"][0] == ("32 of 34 from TradingView's screener, 15 min delayed: "
                             "Nasdaq is not answering")
    assert "Nasdaq refused (403/429) — paused until 07:09:11 ET" in d["notes"]


def test_neither_answering_is_still_the_failure_it_was() -> None:
    st = premarket.covered_by_screener(_refused(), covered=0, total=34)
    d = st.as_dict()
    assert (d["ok"], d["source"], d["items"]) == (False, "unavailable", 0)
    assert d["error"] == "SPY: HTTP 403"
    assert d["last_ok_utc"] is None
    assert len(d["notes"]) == 3


def test_a_source_that_answered_is_left_as_it_is() -> None:
    st = SourceStatus("Nasdaq pre-market")
    st.items = 34
    st.settle(True, what="read")
    st.notes = ["34 of 34 read for 2026-11-11 · 1 fetched, 0 due"]
    before = st.as_dict()
    after = premarket.covered_by_screener(st, covered=30, total=34).as_dict()
    assert after == before
