"""The catalyst read for direction, the clock and tape penalties from the
record, and the record line under a row's score (2026-10-23)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from newsterminal import scanlog, scanscore


def _h(title: str, age_min: float = 90.0, pub: str = "Reuters") -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": pub, "kind": "news"}


@pytest.mark.parametrize(
    ("title", "want"),
    [("Jefferies downgrades Alphabet to Hold, cuts target to 240", "bear"),
     ("Morgan Stanley upgrades AMD to Overweight", "bull"),
     ("Intel raises full-year guidance on data centre demand", "bull"),
     ("Nike cuts outlook as China sales slow", "bear"),
     ("Meta beats on revenue, raises capex forecast", "bull"),
     ("Tesla misses on deliveries", "bear"),
     ("Meta sell-off drags US tech stocks lower as AI spending fears flare up", None),
     ("Stock Market Today: Nasdaq Hit As Meta, Alphabet Slide Below Key Level", None),
     ("Coinbase upgraded despite earnings miss", None),  # both ways: ambiguous
     ("Palantir announces secondary offering of 12m shares", "bear"),
     ("DOJ opens probe into Robinhood's prediction markets", "bear")],
)
def test_headline_direction(title: str, want: str | None) -> None:
    assert scanscore.headline_direction(title) == want


def test_catalyst_with_the_side_earns_and_against_it_costs_and_flags() -> None:
    hit = scanscore.catalyst_read("short", None, [_h("Jefferies downgrades X to Hold")], None)
    assert hit["pts"] == 6 and hit["against"] is None
    assert hit["note"] == ('with the short · Reuters: "Jefferies downgrades X to Hold" '
                           "(2h)")
    miss = scanscore.catalyst_read("long", None, [_h("Jefferies downgrades X to Hold")], None)
    assert miss["pts"] == -6
    assert miss["against"] == 'Reuters: "Jefferies downgrades X to Hold" (2h)'
    assert miss["note"].startswith("against the long · Reuters:")
    flags = scanscore.flags_for({"setup": {"side": "long"}, "score": {"side": "long"}}, None,
                                None, [], [], "rth", catalyst=miss)
    assert flags[0] == {"kind": "catalyst", "tone": "warn",
                        "text": 'Against: Reuters: "Jefferies downgrades X to Hold" (2h)'}


def test_catalyst_reads_the_report_surprise_and_filings() -> None:
    beat = {"days": -1, "when": "after", "surprise_pct": 3.2}
    r = scanscore.catalyst_read("long", beat, [], None)
    assert r["pts"] == 6
    assert r["note"] == "with the long · reported after the close, EPS +3.2% vs estimate"
    r = scanscore.catalyst_read("short", beat, [], None)
    assert r["pts"] == -6
    # No surprise figure: the report alone carries no direction.
    unknown = {"days": -1, "when": "after", "surprise_pct": None}
    assert scanscore.catalyst_read("long", unknown, [], None)["pts"] == 0
    off = scanscore.catalyst_read("long", None, [], [{"form": "424B5", "desc": "Prospectus"}])
    assert off["pts"] == -6 and off["against"] == "offering filed: Prospectus"
    off_short = scanscore.catalyst_read("short", None, [], [{"form": "S-3", "desc": "Shelf"}])
    assert off_short["pts"] == 3


def test_catalyst_against_wins_a_tie_and_stale_headlines_do_not_count() -> None:
    both = scanscore.catalyst_read("long", None,
                                   [_h("Barclays upgrades X to Buy"), _h("UBS downgrades X")], None)
    assert both["pts"] == -6 and "with it:" in both["note"]
    old = scanscore.catalyst_read("long", None, [_h("Barclays upgrades X to Buy", age_min=20 * 60)],
                                  None)
    assert old["pts"] == 0
    assert old["note"] == "no directional catalyst · no headlines since the close"
    none = scanscore.catalyst_read("long", None, [_h("X launches a new phone")], None)
    assert none["note"] == "no directional catalyst · 1 headline since the close"
    assert scanscore.catalyst_read(None, None, [_h("X upgraded")], None)["note"] == "no side"


@pytest.mark.parametrize(
    ("at", "want"),
    [("09:40", -10), ("09:59", -10), ("10:00", None), ("12:30", None), ("14:59", None),
     ("15:00", -10), ("15:50", -10)],
)
def test_clock_penalty_windows(at: str, want: int | None) -> None:
    got = scanscore.clock_penalty([{"kind": "L", "at_et": at, "side": "long"}])
    assert (got[0] if got else None) == want
    if want:
        assert "% of such signals reached +1R" in got[1]
    assert scanscore.clock_penalty([{"kind": "BO", "at_et": "09:40"}]) is None
    assert scanscore.clock_penalty([]) is None


def test_tape_penalty_needs_a_moderate_lean_against_the_side() -> None:
    mod = {"bias": "short", "grade": "moderate", "agree": 6, "total": 11}
    assert scanscore.tape_penalty("long", mod) == (
        -10, "long against a moderate short tape, 6 of 11 agree")
    assert scanscore.tape_penalty("short", mod) is None
    assert scanscore.tape_penalty("long", {"bias": "short", "grade": "weak"}) is None
    assert scanscore.tape_penalty("long", None) is None


def _ev(day: str, kind: str, side: str, score: int | None, hit: bool,
        close_r: float) -> dict[str, Any]:
    return {"kind": kind, "side": side, "day": day, "score": score,
            "outcome": {"final": True, "r": 1.0, "hit_1r": hit, "ret_close_r": close_r}}


def test_record_table_and_the_row_line() -> None:
    evs = [_ev("2026-10-20", "L", "short", 45, True, 2.0),
           _ev("2026-10-21", "L", "short", 55, False, -1.0),
           _ev("2026-10-21", "L", "short", 70, True, 3.0),
           _ev("2026-10-21", "E", "long", None, True, 1.0)]
    t = scanlog.record_table(evs, 30, date(2026, 10, 23))
    assert t == {"40-59|L|short": {"n": 2, "win_1r": 0.5, "avg_close_r": 0.5, "sessions": 2},
                 "60+|L|short": {"n": 1, "win_1r": 1.0, "avg_close_r": 3.0, "sessions": 1}}
    big = {"40-59|L|short": {"n": 21, "win_1r": 0.571, "avg_close_r": 5.92, "sessions": 7}}
    row = {"signals": [], "setup": {"state": "pullback"}}
    assert scanscore.implied_kind(row) == "L"
    rec = scanscore.record_for("L", "short", 52, big)
    assert rec == {"kind": "L", "side": "short", "band": "40-59", "n": 21, "win_1r": 0.571,
                   "avg_close_r": 5.92, "sessions": 7, "small": True}
    assert scanscore.record_for("L", "short", 65, big) is None
    assert scanscore.record_for("L", "short", 52, {"40-59|L|short": {"n": 9}}) is None
    assert scanscore.implied_kind({"signals": [{"kind": "E", "at_et": "10:10"}],
                                   "setup": {"state": "retest"}}) == "E"
    assert scanscore.implied_kind({"signals": [], "setup": {"state": "approaching"}}) is None
