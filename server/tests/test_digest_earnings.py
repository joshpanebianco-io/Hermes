"""
The digest's earnings are anchored on now, not on the top of the week.

The collector keeps two days back and four ahead, oldest first, and the digest
used to hand the model the first fourteen rows of that — always the oldest
day. On 2026-10-30 that meant Hermes knew Visa's Monday beat and nothing of
Alphabet's Wednesday miss (owner: "yesterday we had all these GOOG ... MSFT").
So the slice is now two lists around the snapshot's clock: the latest prints,
and what is still to come.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import report

ET = ZoneInfo("America/New_York")

# Thursday 29 October 2026, 21:25 ET — after the close, before Asia.
NOW = datetime(2026, 10, 29, 21, 25, tzinfo=ET)


def _e(sym: str, date: str, when: str, cap_bn: float, actual: str | None = None,
       forecast: str = "$1.00", surprise: float | None = None) -> dict[str, Any]:
    return {"symbol": sym, "name": sym, "date": date, "when": when, "eps_forecast": forecast,
            "eps_actual": actual, "surprise_pct": surprise, "market_cap": cap_bn * 1e9}


ROWS = [
    # Tuesday's prints — the oldest day, which used to be the whole slice.
    _e("V", "2026-10-27", "unspecified", 715, actual="$3.48", forecast="$3.43", surprise=1.46),
    _e("KO", "2026-10-27", "unspecified", 394, actual="$0.91", forecast="$0.87", surprise=4.6),
    # Wednesday's prints, with a no-show that never got an actual.
    _e("GOOG", "2026-10-28", "unspecified", 3973, actual="$2.12", forecast="$2.94",
       surprise=-27.89),
    _e("MSFT", "2026-10-28", "unspecified", 3943, actual="$4.89", forecast="$4.71", surprise=3.82),
    _e("SAN", "2026-10-28", "unspecified", 183, actual="$0.26", forecast="$0.26"),
    _e("NOSHOW", "2026-10-28", "after", 90),
    # Today: a pre-market print that landed, and tonight's names still unprinted.
    _e("CAT", "2026-10-29", "pre", 210, actual="$5.10", forecast="$4.80", surprise=6.25),
    _e("AMZN", "2026-10-29", "after", 2400),
    _e("INTC", "2026-10-29", "after", 160),
    # Tomorrow and Monday.
    _e("AAPL", "2026-10-30", "pre", 3800),
    _e("XOM", "2026-11-02", "pre", 480),
    # A row the feed mangled.
    _e("BAD", "not a date", "pre", 999, actual="$1.00"),
]


def test_the_latest_prints_lead_and_the_oldest_day_is_last() -> None:
    d = report.digest_earnings(ROWS, NOW)
    assert [r["symbol"] for r in d["reported"]] == ["CAT", "GOOG", "MSFT", "SAN", "V", "KO"]
    goog = d["reported"][1]
    assert goog["eps_actual"] == "$2.12" and goog["eps_forecast"] == "$2.94"
    assert goog["surprise_pct"] == -27.89


def test_ahead_starts_tonight_and_drops_past_no_shows() -> None:
    d = report.digest_earnings(ROWS, NOW)
    assert [r["symbol"] for r in d["ahead"]] == ["AMZN", "INTC", "AAPL", "XOM"]
    # Unprinted rows carry no actual at all, rather than a null the model might read as a miss.
    assert all("eps_actual" not in r for r in d["ahead"])
    assert d["ahead"][0]["when"] == "after"


def test_a_row_without_a_readable_date_is_skipped() -> None:
    d = report.digest_earnings(ROWS, NOW)
    assert "BAD" not in {r["symbol"] for r in d["reported"] + d["ahead"]}


def test_each_side_is_capped_at_its_budget_biggest_kept() -> None:
    printed = [_e(f"P{i}", "2026-10-28", "after", 100 + i, actual="$1") for i in range(12)]
    due = [_e(f"D{i}", "2026-10-30", "pre", 100 + i) for i in range(12)]
    d = report.digest_earnings(printed + due, NOW)
    assert len(d["reported"]) == report.EARNINGS_REPORTED == 8
    assert len(d["ahead"]) == report.EARNINGS_AHEAD == 8
    assert d["reported"][0]["symbol"] == "P11" and d["ahead"][0]["symbol"] == "D11"
    assert "P0" not in {r["symbol"] for r in d["reported"]}


def test_the_digest_hands_the_model_both_lists_off_the_snapshots_clock() -> None:
    snap = {"clock": {"et": NOW.isoformat()}, "earnings": ROWS}
    d = report.build_digest(snap, "asia", "all")
    assert d["earnings"]["reported"][0]["symbol"] == "CAT"
    assert d["earnings"]["ahead"][0]["symbol"] == "AMZN"


def test_the_moment_a_report_prints_follows_its_timing_field() -> None:
    pre = report._earnings_moment(_e("X", "2026-10-29", "pre", 1))
    after = report._earnings_moment(_e("X", "2026-10-29", "after", 1))
    tbc = report._earnings_moment(_e("X", "2026-10-29", "unspecified", 1))
    assert pre is not None and (pre.hour, pre.minute) == (8, 0)
    assert after is not None and (after.hour, after.minute) == (16, 5)
    assert tbc is not None and (tbc.hour, tbc.minute) == (16, 5)  # untimed = after the close
    assert report._earnings_moment(_e("X", "29/10/2026", "pre", 1)) is None
