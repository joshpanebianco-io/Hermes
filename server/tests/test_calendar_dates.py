"""The economic calendar's day: Nasdaq's `?date=` is read for the day its rows
are actually for (sources/calendar.py, `date_shift`)."""

from datetime import date

from newsterminal.sources import calendar as cal


def _doc(*events: str) -> dict:
    return {"data": {"rows": [{"country": "United States", "eventName": e, "gmt": "08:30"}
                              for e in events]}}


def test_shift_minus_one_as_seen_2026_10_13() -> None:
    # The real pass: ?date=Thu held Wednesday's MBA, ?date=Fri Thursday's claims.
    docs = [
        (date(2026, 10, 15), _doc("MBA Mortgage Applications", "Core CPI", "Beige Book")),
        (date(2026, 10, 16), _doc("Initial Jobless Claims", "Fed's Balance Sheet")),
    ]
    assert cal.date_shift(docs) == -1


def test_shift_zero_when_dates_are_honest() -> None:
    docs = [
        (date(2026, 10, 14), _doc("MBA Mortgage Applications")),
        (date(2026, 10, 15), _doc("Initial Jobless Claims", "Continuing Jobless Claims")),
    ]
    assert cal.date_shift(docs) == 0


def test_thin_or_split_vote_is_none() -> None:
    assert cal.date_shift([(date(2026, 10, 15), _doc("MBA Mortgage Applications"))]) is None
    assert cal.date_shift([(date(2026, 10, 13), _doc("Core CPI", "Redbook"))]) is None
    # A holiday week moving one release does not flip a clear majority.
    docs = [
        (date(2026, 10, 15), _doc("MBA Mortgage Applications")),
        (date(2026, 10, 16), _doc("Initial Jobless Claims", "Fed's Balance Sheet")),
        (date(2026, 10, 17), _doc("Baker Hughes Oil Rig Count")),
        (date(2026, 10, 14), _doc("Initial Jobless Claims")),  # a Wednesday claims print
    ]
    assert cal.date_shift(docs) == -1


def test_foreign_anchor_names_do_not_vote() -> None:
    doc = {"data": {"rows": [{"country": "Canada", "eventName": "Initial Jobless Claims"}] * 3}}
    assert cal.date_shift([(date(2026, 10, 16), doc)]) is None


def test_rows_are_dated_by_the_corrected_day() -> None:
    rows = cal.parse_day(_doc("Core CPI"), date(2026, 10, 14))
    assert rows[0]["date"] == "2026-10-14"
    assert rows[0]["utc"] == "2026-10-14T12:30:00+00:00"


def _row(event: str, prev: str | None, cons: str | None = None) -> dict:
    def n(x: str | None) -> float | None:
        return float(x.rstrip("%M")) if x else None
    return {"country": "United States", "event": event, "utc": "2026-10-14T12:30:00+00:00",
            "date": "2026-10-14", "previous": n(prev), "previous_raw": prev,
            "consensus": n(cons), "consensus_raw": cons, "actual": None, "actual_raw": None}


def test_paired_cpi_is_labelled_by_its_figures() -> None:
    rows = [_row("Core CPI", "2.4%", "2.5%"), _row("Core CPI", "0.3%", "0.2%"), _row("CPI", "0.4%")]
    cal.label_variants(rows)
    assert [r["event"] for r in rows] == ["Core CPI y/y", "Core CPI m/m", "CPI"]


def test_level_beside_a_change() -> None:
    rows = [_row("Existing Home Sales", "3.98M", "3.95M"), _row("Existing Home Sales", "-2.0%")]
    cal.label_variants(rows)
    assert [r["event"] for r in rows] == ["Existing Home Sales", "Existing Home Sales m/m"]


def test_pair_the_figures_cannot_separate_is_left_alone() -> None:
    rows = [_row("Fed Speaks", None), _row("Fed Speaks", None)]
    cal.label_variants(rows)
    assert [r["event"] for r in rows] == ["Fed Speaks", "Fed Speaks"]
