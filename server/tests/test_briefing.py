"""
The market report as a briefing (brief_version 4, 2026-11-19).

Owner: "format the market report to look like a professional market report that would
be given to a ceo ... list what things can impact prices going into a session, eg news,
macro events, headlines, earnings, geopolitics, vix, economic calender events on the day
or earlier in the week that have an impact and then a brief summary on why each thing has
an impact", then "do what you recommend best".

Held here: the calendar reaches back to the week's Monday for what printed and is high
impact; the list's rows that are no calendar row or headline (rates, the VIX,
positioning) are the collector's words; the model's list is cleaned to rows that exist,
the VIX is always on it and never a side; a list that leaves out a high-impact release of
the session is sent back, and filled with the server's line if it still does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import report, tools

ET = ZoneInfo("America/New_York")
#: Thursday 19 November 2026, 08:00 ET: the New York pre-open.
THU = datetime(2026, 11, 19, 8, 0, tzinfo=ET)


def _row(day: int, hm: str, event: str, score: int, released: bool,
         actual: str | None = None) -> dict[str, Any]:
    h, m = (int(x) for x in hm.split(":"))
    ts = datetime(2026, 11, day, h, m, tzinfo=ET).timestamp()
    return {"ts": ts, "event": event, "score": score, "core": True, "released": released,
            "country": "United States", "session": "premkt", "actual_raw": actual,
            "consensus_raw": None, "previous_raw": None}


# ------------------------------------------------------------- earlier this week


def test_the_calendar_reaches_back_to_monday_for_what_printed_and_matters() -> None:
    snap = {"calendar": [
        _row(12, "08:30", "CPI YoY", 5, True, "3.1%"),             # last week: out
        _row(17, "08:30", "Retail Sales MoM", 5, True, "0.2%"),    # Tuesday, high: in
        _row(17, "10:00", "Business Inventories", 3, True, "0.1%"),  # Tuesday, low: out
        _row(19, "08:30", "Initial Jobless Claims", 5, False),     # this morning, ahead
    ], "fed": [
        {"ts": datetime(2026, 11, 18, 14, 0, tzinfo=ET).timestamp(), "kind": "FOMC",
         "title": "FOMC rate decision", "major": True, "date": "2026-11-18"},
        {"ts": datetime(2026, 11, 17, 12, 0, tzinfo=ET).timestamp(), "kind": "Speech",
         "title": "Speech - Governor Lisa D. Cook", "major": False, "date": "2026-11-17"},
    ]}
    cats = report._catalysts(snap, ["NQ"], THU)
    got = {c["title"]: c for c in cats}
    assert set(got) == {"Retail Sales MoM", "FOMC rate decision", "Initial Jobless Claims"}
    assert got["Retail Sales MoM"]["earlier"] is True and got["Retail Sales MoM"]["released"]
    assert got["FOMC rate decision"]["earlier"] is True
    assert "earlier" not in got["Initial Jobless Claims"]
    assert got["Retail Sales MoM"]["when"] == "Tue 08:30 ET"


def test_the_calendar_keeps_only_the_weeks_big_prints_before_yesterday() -> None:
    from newsterminal.sources import calendar as cal

    def at(day: int, score: int, released: bool, region: str = "us",
           core: bool = False) -> dict[str, Any]:
        return {"ts": datetime(2026, 11, day, 8, 30, tzinfo=ET).timestamp(), "score": score,
                "released": released, "region": region, "core": core}

    tue_big, tue_small = at(17, 5, True), at(17, 2, True)
    tue_foreign = at(17, 4, True, region="eu")              # reaches nothing here
    tue_ecb = at(17, 4, True, region="eu", core=True)       # reaches the books
    wed_small, thu_due = at(18, 1, True), at(19, 5, False)  # yesterday on: whole
    kept = cal.thin_past([tue_big, tue_small, tue_foreign, tue_ecb, wed_small, thu_due],
                         THU.date())
    assert kept == [tue_big, tue_ecb, wed_small, thu_due]
    assert cal.DAYS_BACK == 4


def test_on_a_monday_the_week_reaches_back_to_friday() -> None:
    mon = datetime(2026, 11, 16, 7, 0, tzinfo=ET)
    assert report._week_lo(mon) == datetime(2026, 11, 13, 7, 0, tzinfo=ET).timestamp()
    assert report._week_lo(THU) == datetime(2026, 11, 16, 0, 0, tzinfo=ET).timestamp()


# ------------------------------------------------------------- the rows of its own


def _snap(**over: Any) -> dict[str, Any]:
    s: dict[str, Any] = {
        "quotes": [{"key": "US10Y", "last": 5.145, "chg": 0.024, "feed": "live"},
                   {"key": "DXY", "last": 103.61, "pct": 0.06, "feed": "live"},
                   {"key": "VIX", "last": 22.92, "pct": 0.04, "feed": "live"}],
        "volterm": {"ratio": 1.0, "shape": "flat"},
    }
    s.update(over)
    return s


COT = {"NQ": {"context": [{"label": "COT · Leveraged funds",
                           "value": "net long 12,889 · 100th pct"}]}}


def test_rates_the_vix_and_positioning_are_the_collectors_words() -> None:
    rows = {m["id"]: m for m in report.context_movers(_snap(), ["NQ"], COT, THU)}
    assert rows["rates"]["what"] == "10Y 5.145% (+2.4bp) · Dollar 103.61 (+0.06%)"
    assert rows["vix"]["what"] == "VIX 22.9 (+0.0%) · curve 1.00, flat"
    # 22.9 is the elevated band: weather, said as the ranges it makes.
    assert rows["vix"]["regime"] == "Wider ranges" and "Size down" in rows["vix"]["why"]
    assert rows["positioning"]["what"] == "Leveraged funds: NQ net long 12,889 · 100th pct"


def test_crude_reads_the_dollar_not_the_ten_year_and_a_calm_vix_is_small_ranges() -> None:
    calm = _snap(quotes=[{"key": "US10Y", "last": 4.1, "chg": 0.05},
                         {"key": "DXY", "last": 99.0, "pct": -0.3},
                         {"key": "VIX", "last": 12.1, "pct": -2.0}])
    rows = {m["id"]: m for m in report.context_movers(calm, ["CL"], {}, THU)}
    assert rows["rates"]["what"] == "Dollar 99.00 (-0.30%)"
    assert rows["vix"]["regime"] == "Small ranges"
    assert "positioning" not in rows


def test_the_model_is_handed_the_ids_it_may_pick() -> None:
    facts = {"context_movers": report.context_movers(_snap(), ["NQ"], COT, THU)}
    menu = report.movers_menu(facts)["other_movers"]
    assert [m["id"] for m in menu] == ["rates", "vix", "positioning"]
    # The VIX's band word goes with it, so the why agrees with what the page prints.
    assert menu[1]["ranges"] == "Wider ranges" and "ranges" not in menu[0]


# ------------------------------------------------------------- the list, cleaned


def _facts() -> dict[str, Any]:
    return {
        "books": ["NQ"],
        "catalysts": [
            {"id": "c1", "kind": "data", "high": True, "released": False,
             "lands_in_session": "premkt", "title": "Initial Jobless Claims",
             "when": "Today 08:30 ET"},
            {"id": "c2", "kind": "data", "high": True, "released": True, "earlier": True,
             "lands_in_session": "premkt", "title": "Retail Sales MoM",
             "when": "Tue 08:30 ET"},
            {"id": "c3", "kind": "earnings", "high": False, "released": True,
             "title": "NVDA earnings", "when": "Wed after the close"},
        ],
        "headlines": [{"id": "h1", "title": "Tariffs on chips"}],
        "context_movers": report.context_movers(_snap(), ["NQ"], COT, THU),
    }


def test_the_list_keeps_rows_that_exist_in_the_schemas_words() -> None:
    out = report._movers([
        {"id": "c1", "impact": "High", "effect": "Bearish",
         "why": "A low claims print keeps yields up, which weighs on tech."},
        {"id": "h9", "impact": "high", "effect": "pressure", "why": "No such story."},
        {"id": "rates", "impact": "medium", "effect": "priced in", "why": ""},
        {"id": "h1", "impact": "bogus", "effect": "weird", "why": "Chip tariffs hit margins."},
        {"id": "c1", "impact": "low", "effect": "supportive", "why": "Said twice."},
    ], _facts())
    assert [(m["id"], m["impact"], m["effect"]) for m in out] == [
        ("c1", "high", "pressure"), ("h1", "medium", "two-way"), ("vix", "medium", "regime")]


def test_the_vix_is_always_on_the_list_and_never_a_side() -> None:
    mine = report._movers([{"id": "VIX", "impact": "low", "effect": "bearish",
                            "why": "Protection bid into the print."}], _facts())
    assert mine == [{"id": "vix", "impact": "low", "effect": "regime",
                     "why": "Protection bid into the print."}]
    # Left off, it is added with the server's line, which the guard and the word count skip.
    added = report._movers([], _facts())
    assert added[0]["id"] == "vix" and added[0]["why"].startswith("Elevated")
    assert report.brief_prose({"thesis": "t", "movers": added}) == ["t"]


def test_a_list_short_of_the_sessions_high_impact_prints_is_sent_back_then_filled() -> None:
    b = {"movers": report._movers([{"id": "h1", "impact": "high", "effect": "pressure",
                                    "why": "Chip tariffs hit margins."}], _facts())}
    faults = report.list_faults(b, _facts(), "ny")
    assert faults == ["the list has 1 items besides the VIX (at least 3)",
                      "the list leaves out c1 (Initial Jobless Claims), high impact this session"]
    # This week's earlier print is not demanded: it is the model's to judge.
    assert not any("c2" in f for f in faults)
    # A London note does not owe New York's 08:30 print a line.
    assert not any("c1" in f for f in report.list_faults(b, _facts(), "london"))
    report.fill_missed(b, _facts(), "ny")
    filled = next(m for m in b["movers"] if m["id"] == "c1")
    assert filled["server"] is True and filled["effect"] == "two-way"
    assert filled["why"].startswith("Due this session")
    assert "Due this session" not in " ".join(report.brief_prose({"thesis": "t", **b}))


def test_an_older_answer_has_no_list_to_hold_to() -> None:
    assert report.list_faults({"thesis": "t"}, _facts(), "ny") == []


def test_two_items_that_say_one_thing_are_a_repeat() -> None:
    b = {"movers": [
        {"id": "c1", "why": "Strong data keeps yields high and presses tech multiples"},
        {"id": "c2", "why": "Strong data keeps yields high and presses tech multiples again"}]}
    assert report.repeats(b) == ["item c2 repeats item c1"]


def test_hermes_reads_the_list_joined_to_what_each_item_is() -> None:
    note = {"thesis": "t", "calls": [], "movers": [
        {"id": "c1", "impact": "high", "effect": "two-way", "why": "Claims reprice the Fed."},
        {"id": "vix", "impact": "medium", "effect": "regime", "why": "Size down."}]}
    got = tools._note({"note": note}, "brief", None, _facts())
    lines = got["note"]["what_can_move_prices"]
    assert lines[0] == ("Today 08:30 ET Initial Jobless Claims — high impact, two-way: "
                        "Claims reprice the Fed.")
    assert lines[1].startswith("VIX 22.9 (+0.0%)")


# ------------------------------------------------------------- how each feeds the bias


def _factor(key: str, name: str, weight: int | None, tag: str, lean: str) -> dict[str, Any]:
    return {"key": key, "name": name, "sub": None, "weight": weight, "lean": lean, "tag": tag,
            "reads": []}


NQ_PRE = [_factor("structure", "Volume profile & structure", 35, "Bullish", "bull"),
          _factor("catalysts", "News & data", 35, "Nothing yet", "none"),
          _factor("rates", "Macro", 30, "Not live yet", "none"),
          _factor("event", "Geopolitics & events", None, "3 stories", "damp")]


def _cat(cid: str, kind: str, title: str, *, themes: list[str] | None = None,
         country: str | None = "United States", earlier: bool = False) -> dict[str, Any]:
    return {"id": cid, "kind": kind, "title": title, "themes": themes or [], "country": country,
            **({"earlier": True} if earlier else {})}


CATS = [_cat("c1", "data", "Initial Jobless Claims", themes=["jobs"]),
        _cat("c2", "data", "CPI m/m", themes=["inflation"]),
        _cat("c3", "data", "Retail Sales m/m", themes=["growth"], earlier=True),
        _cat("c4", "fed", "Speech - Governor Waller"),
        _cat("c5", "earnings", "NVDA earnings"),
        _cat("c6", "data", "UK CPI y/y", themes=["inflation"], country="United Kingdom"),
        _cat("c7", "data", "Crude Oil Inventories", themes=["energy"])]


def test_each_item_names_the_factor_of_the_bias_that_counts_it_or_why_none_does() -> None:
    # Owner, 2026-11-19: "you didnt do what i said in regards to explaining how each thing
    # impacts the market or contributes to the bias". The engine's arithmetic, not the
    # model's: an index book counts US inflation prints alone.
    facts = {"books": ["NQ"], "factors": {"NQ": NQ_PRE}, "catalysts": CATS,
             "headlines": [{"id": "h1"}],
             "context_movers": report.context_movers(_snap(), ["NQ"], COT, THU)}
    links = report.bias_links(facts)
    assert links["c2"] == {"key": "catalysts", "name": "News & data", "weight": 35,
                           "tag": "Nothing yet", "lean": "none"}
    assert links["c1"]["key"] is None and "only US inflation prints vote" in links["c1"]["note"]
    assert (links["c3"]["name"], links["c3"]["note"]) == ("In the price", "it voted on its day")
    assert "through yields" in links["c4"]["note"]
    assert "already in the index" in links["c5"]["note"]
    assert "reads US prints" in links["c6"]["note"]
    assert links["h1"]["name"] == "Geopolitics & events" and links["h1"]["tag"] == "3 stories"
    assert (links["rates"]["name"], links["rates"]["weight"]) == ("Macro", 30)
    assert links["vix"]["name"] == "Not in the bias" and "never a side" in links["vix"]["note"]
    assert links["positioning"]["key"] is None
    # The model reads the same, in words, beside the ids it may pick.
    menu = report.movers_menu({**facts, "bias_links": links})["feeds_the_bias"]
    assert menu["rates"] == "Macro, 30% of the bias, Not live yet"
    assert menu["c1"] == "Read, not counted: only US inflation prints vote"


def test_crude_counts_its_inventories_and_growth_prints_and_the_tape_counts_none() -> None:
    cl = report.bias_links({"books": ["CL"], "catalysts": CATS, "factors": {"CL": [
        _factor("catalysts", "Inventories & data", 25, "Bearish", "bear")]}})
    assert cl["c7"]["key"] == "catalysts" and cl["c7"]["lean"] == "bear"
    assert cl["c2"]["key"] is None and "inventories" in cl["c2"]["note"]
    # A factor with no weight in the session is said so, not left blank.
    asia = report.bias_links({"books": ["NQ"], "catalysts": CATS,
                              "factors": {"NQ": [NQ_PRE[0]]}})
    assert (asia["c2"]["name"], asia["c2"]["note"]) == ("Not weighed",
                                                      "its factor has no weight in this session")
    # The Stocks report: the tape reads prices, not the calendar.
    tape = report.bias_links({"books": ["SPY", "QQQ", "IWM"], "catalysts": CATS,
                              "market_factors": [_factor("rates", "Macro", 35, "Neutral",
                                                         "neutral")],
                              "context_movers": [{"id": "rates", "what": "x"}]})
    assert "the tape reads prices" in tape["c2"]["note"]
    assert tape["rates"]["name"] == "Macro"
