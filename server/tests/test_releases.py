"""One release, one row (releases.py) — the family rule and the brief's catalysts.

The names are the calendar's own, from the 2026-10-14 feed. src/lib/releases.ts
carries the same rule for the panels; its check runs the same cases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal.releases import family, group, is_level
from newsterminal.report import build_facts

ET = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    ("event", "fam"),
    [
        ("Core CPI m/m", "cpi"), ("CPI y/y", "cpi"), ("Core CPI Index", "cpi"),
        ("CPI Index, n.s.a.", "cpi"), ("CPI, n.s.a", "cpi"), ("German CPI y/y", "cpi"),
        ("French CPI NSA m/m", "cpi"), ("Spanish HICP y/y", "cpi"),
        ("Core PPI m/m", "ppi"), ("PPI ex. Food/Energy/Transport y/y", "ppi"),
        ("Initial Jobless Claims", "claims"), ("Jobless Claims 4-Week Avg.", "claims"),
        ("Nonfarm Payrolls", "jobs"), ("Unemployment Rate", "jobs"),
        ("Average Hourly Earnings m/m", "jobs"),
        ("Core Retail Sales", "retail sales"), ("Retail Control", "retail sales"),
        ("Retail Sales Ex Gas/Autos", "retail sales"),
        ("Core PCE Price Index m/m", "pce"), ("Personal Spending", "pce"),
        # Their own families: a different index, a different release.
        ("Cleveland CPI", "cleveland cpi"), ("Real Earnings", "real earnings"),
        ("Import Price Index m/m", "import price"),
    ],
)
def test_family(event: str, fam: str) -> None:
    assert family(event) == fam


def test_index_levels_and_unadjusted_twins_are_levels_and_nothing_else_is() -> None:
    assert is_level("Core CPI Index", None, None, "337.77")
    assert is_level("CPI Index, s.a", None, None, "334.13")
    assert is_level("CPI, n.s.a", None, None, "0.32%")
    assert not is_level("PCE Price Index m/m", None, "0.3%", "0.2%")
    # A diffusion index IS the number that is traded.
    assert not is_level("NY Empire State Manufacturing Index", "11.2", "14.8", None)
    assert not is_level("Core CPI m/m", None, "0.2%", "0.3%")


def _row(event: str, at: int, score: int = 5, country: str = "United States",
         cons: str | None = "0.2%", prev: str | None = "0.3%") -> dict[str, Any]:
    return {"event": event, "country": country, "ts": at, "score": score, "core": True,
            "released": False, "actual_raw": None, "consensus_raw": cons,
            "previous_raw": prev, "surprise": None, "session": "preny"}


CPI_AT = int(datetime(2026, 10, 14, 8, 30, tzinfo=ET).timestamp())
CPI_DAY = [  # the feed's order on the morning
    _row("Core CPI y/y", CPI_AT, cons="2.5%", prev="2.4%"),
    _row("Core CPI m/m", CPI_AT),
    _row("Core CPI Index", CPI_AT, cons=None, prev="337.77"),
    _row("CPI y/y", CPI_AT, cons="3.6%", prev="3.4%"),
    _row("CPI m/m", CPI_AT, cons="0.6%", prev="0.4%"),
    _row("CPI Index, n.s.a.", CPI_AT, cons="336.65", prev="334.98"),
    _row("CPI Index, s.a", CPI_AT, cons=None, prev="334.13"),
    _row("CPI, n.s.a", CPI_AT, cons=None, prev="0.32%"),
    _row("Real Earnings", CPI_AT, score=2, cons=None, prev="0.2%"),
]


def _group(rows: list[dict[str, Any]]) -> list[Any]:
    return group(rows, event=lambda r: r["event"], when=lambda r: r["ts"],
                 country=lambda r: r["country"], score=lambda r: r["score"],
                 figures=lambda r: (r["actual_raw"], r["consensus_raw"], r["previous_raw"]))


def test_cpi_morning_is_one_release_led_by_core_monthly() -> None:
    cpi, real = _group(CPI_DAY)
    assert cpi.lead["event"] == "Core CPI m/m"
    assert [r["event"] for r in cpi.subs] == ["Core CPI y/y", "CPI m/m", "CPI y/y"]
    assert {r["event"] for r in cpi.levels} == {
        "Core CPI Index", "CPI Index, n.s.a.", "CPI Index, s.a", "CPI, n.s.a"}
    # Real Earnings prints in the same minute and is not CPI.
    assert real.lead["event"] == "Real Earnings" and not real.subs


def test_releases_that_share_a_minute_but_not_a_family_stay_apart() -> None:
    thu = int(datetime(2026, 10, 15, 8, 30, tzinfo=ET).timestamp())
    rows = [_row("Initial Jobless Claims", thu, cons="195K", prev="197K"),
            _row("Core PPI m/m", thu), _row("Continuing Jobless Claims", thu, score=2),
            _row("PPI m/m", thu), _row("Retail Sales m/m", thu), _row("Core Retail Sales", thu),
            _row("Jobless Claims 4-Week Avg.", thu, score=2)]
    got = {g.lead["event"]: [r["event"] for r in g.subs] for g in _group(rows)}
    assert got == {
        "Initial Jobless Claims": ["Continuing Jobless Claims", "Jobless Claims 4-Week Avg."],
        "Core PPI m/m": ["PPI m/m"],
        "Retail Sales m/m": ["Core Retail Sales"],
    }


def test_same_family_different_country_or_minute_is_not_one_release() -> None:
    rows = [_row("CPI m/m", CPI_AT), _row("CPI m/m", CPI_AT, country="Canada"),
            _row("Cleveland CPI", CPI_AT + 9000), _row("CPI y/y", CPI_AT + 60)]
    assert len(_group(rows)) == 4


def test_a_jobs_report_leads_on_payrolls() -> None:
    at = int(datetime(2026, 11, 6, 8, 30, tzinfo=ET).timestamp())
    rows = [_row("Unemployment Rate", at), _row("Average Hourly Earnings m/m", at),
            _row("Nonfarm Payrolls", at)]
    (jobs,) = _group(rows)
    assert jobs.lead["event"] == "Nonfarm Payrolls"


def test_the_brief_carries_one_catalyst_per_release() -> None:
    snap = {"clock": {"et": "2026-10-14T05:18:00-04:00"}, "status": {}, "quotes": [],
            "calendar": CPI_DAY}
    cats = [c for c in build_facts(snap, "london", "NQ")["catalysts"] if c["kind"] == "data"]
    # Real Earnings scores 2, under the brief's bar; CPI is one row.
    assert [c["title"] for c in cats] == ["Core CPI m/m"]
    cpi = cats[0]
    assert cpi["consensus"] == "0.2%" and cpi["high"]
    assert [a["title"] for a in cpi["also"]] == ["Core CPI y/y", "CPI m/m", "CPI y/y"]
    assert cpi["also"][0] == {"title": "Core CPI y/y", "actual": None,
                              "consensus": "2.5%", "previous": "2.4%"}
    # The index levels never reach the model.
    assert "337.77" not in str(cats)


def test_the_leads_own_series_come_before_the_releases_other_names() -> None:
    thu = int(datetime(2026, 10, 15, 8, 30, tzinfo=ET).timestamp())
    rows = [_row("Core PPI m/m", thu), _row("Core PPI y/y", thu),
            _row("PPI ex. Food/Energy/Transport m/m", thu), _row("PPI m/m", thu),
            _row("PPI ex. Food/Energy/Transport y/y", thu), _row("PPI y/y", thu)]
    (ppi,) = _group(rows)
    assert [r["event"] for r in ppi.subs] == [
        "Core PPI y/y", "PPI m/m", "PPI y/y",
        "PPI ex. Food/Energy/Transport m/m", "PPI ex. Food/Energy/Transport y/y"]


def test_the_scanners_next_event_names_the_release_lead() -> None:
    from newsterminal.scanscore import next_event

    rows = [dict(r, region="us") for r in CPI_DAY]
    rows.insert(0, rows.pop(7))  # "CPI, n.s.a" first, as the snapshot had it
    ev = next_event(rows, datetime(2026, 10, 14, 6, 14, tzinfo=ET))
    assert ev is not None and ev["title"] == "Core CPI m/m" and ev["in_min"] == 136.0
