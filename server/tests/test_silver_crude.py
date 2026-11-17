"""
Silver and crude on the driver board, and in the brief (2026-11-15).

Owner: "implement the silver and oil bias calculation and weightings and rules too",
for a Market Report page that writes about Indexes, Gold, Silver or Oil. What is pinned
here: each book's own hundred (a family a book has no read in carries no weight), what
each of the two new books reads and which way each read votes, and that the brief's
facts are built for them and for the two indexes as one subject.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import bias, drivers, report

NOW = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)  # Wed 11:00 ET, after the 10:30 inventories
ET_1030 = datetime(2026, 11, 18, 15, 30, tzinfo=UTC).timestamp()


def _q(key: str, last: float, pct: float = 0.0, chg: float = 0.0,
       feed: str = "live") -> dict[str, Any]:
    return {"key": key, "last": last, "pct": pct, "chg": chg, "feed": feed, "prev": last}


def _votes(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {v["key"]: v for v in board["votes"]}


def _inventories(actual: float | None, consensus: float | None = None,
                 released: bool = True, ts: float = ET_1030) -> dict[str, Any]:
    return {"event": "Crude Oil Inventories", "region": "us", "country": "United States",
            "score": 3, "themes": ["energy"], "core": False, "ts": ts, "released": released,
            "actual": actual, "consensus": consensus}


def _snap(quotes: list[dict[str, Any]], calendar: list[dict[str, Any]] | None = None
          ) -> dict[str, Any]:
    return {"quotes": quotes, "calendar": calendar or [], "sectors": [],
            "constituents": {"indices": {}}, "gex": {"assets": {}}, "profiles": {"assets": {}},
            "ranges": {"assets": {}}, "history": {"books": {}}, "volterm": {"books": []},
            "cot": {"books": {}}, "putcall": None, "expiry": {}, "policy_meetings": {}}


BASE = [_q("NQ", 28_000.0), _q("ES", 7_600.0), _q("GC", 3_900.0), _q("SILVER", 49.0),
        _q("WTI", 88.0), _q("US10Y", 5.1), _q("DXY", 103.0), _q("HYG", 77.0),
        _q("COPPER", 6.0), _q("RBOB", 2.6), _q("HEATOIL", 4.2), _q("BRENT", 95.0)]


def _with(**moves: float) -> list[dict[str, Any]]:
    """The base board with these day moves (percent; the 10-year's in points of yield)."""
    out = []
    for q in BASE:
        if q["key"] in moves:
            q = {**q, ("chg" if q["key"] == "US10Y" else "pct"): moves[q["key"]]}
        out.append(q)
    return out


# ---- every book has its own hundred ----------------------------------------------------


def test_every_book_weighs_to_a_hundred_in_every_session() -> None:
    for book in drivers.BOOKS:
        for session in bias.BOARD_WEIGHTS:
            w = bias.board_weights(book, session)
            assert sum(w.values()) == 100, (book, session)
            # A family the book has no read in carries nothing.
            keep = bias.BOOK_FAMILIES.get(book)
            if keep is not None:
                assert {k for k, v in w.items() if v} <= set(keep), (book, session)


def test_an_index_books_weights_are_the_sessions_own() -> None:
    for session, base in bias.BOARD_WEIGHTS.items():
        assert bias.board_weights("NQ", session) == base
        assert bias.board_weights("ES", session) == base


def test_gold_no_longer_carries_two_families_it_cannot_vote_in() -> None:
    # In the New York session risk appetite and participation were a third of gold's
    # hundred that no gold read could earn: over the whole weight its score topped out
    # well short of the end. The families gold has a read in are shared out in proportion:
    # three of them since the daily trend left the score (2026-11-15), 33 / 21 / 13 of the
    # session's hundred becoming 49 / 31 / 20.
    assert bias.board_weights("GC", "ny_live") == {
        "structure": 49, "rates": 31, "risk": 0, "catalysts": 20, "participation": 0}
    assert bias.board_weights("GC", "asia") == {
        "structure": 57, "rates": 22, "catalysts": 21, "risk": 0, "participation": 0}
    # Every gold read on one side now reaches the end of the scale.
    votes = [{"key": k, "label": k, "value": "v", "vote": "short", "note": "n", "live": True}
             for k in ("yields", "dollar", "silver", "prints", "value", "session")]
    r = bias.board_read("GC", votes, "ny_live", regime=None, ny_open=True)
    assert (r["score"], r["coverage"], r["grade"]) == (-100, 100, "strong")


def test_shared_out_weights_keep_their_order_and_break_a_tie_by_the_first_named() -> None:
    # 62.5 and 37.5: the half point goes to the family named first.
    assert bias.share_out({"a": 50, "b": 30, "c": 20}, ("a", "b")) == {"a": 63, "b": 37, "c": 0}
    assert bias.share_out({"a": 50, "b": 30, "c": 20}, ("b", "a")) == {"a": 62, "b": 38, "c": 0}
    # Crude in the New York session: 33, 21, 20 and 13 of 87 (participation is not its).
    assert bias.board_weights("CL", "ny_live") == {
        "structure": 38, "rates": 24, "risk": 23, "catalysts": 15, "participation": 0}
    # No book has a daily-trend family to weigh, in any session.
    assert all("daily" not in bias.board_weights(b, s)
               for b in ("NQ", "GC", "SIL", "CL") for s in bias.BOARD_WEIGHTS)
    assert bias.share_out({"a": 0, "b": 0}, ("a",)) == {"a": 0, "b": 0}


def test_silver_and_crude_name_their_families_for_what_is_in_them() -> None:
    board = drivers.build(_snap(_with()), "rth", NOW)["books"]
    names = lambda b: {f["key"]: f["label"] for f in board[b]["families"]}  # noqa: E731
    assert names("SIL")["rates"] == "Rates, dollar & metals"
    assert names("CL")["rates"] == "Dollar & products"
    assert names("CL")["risk"] == "Demand"
    assert names("CL")["catalysts"] == "Inventories"
    assert names("GC")["rates"] == "Rates & dollar"       # gold's are as they were


# ---- silver --------------------------------------------------------------------------------


def test_the_board_scores_five_books_and_finds_silver_and_crude_under_their_board_keys() -> None:
    board = drivers.build(_snap(_with()), "rth", NOW)["books"]
    assert list(board) == ["NQ", "ES", "GC", "SIL", "CL"]
    assert board["SIL"]["last"] == 49.0 and board["CL"]["last"] == 88.0


def test_silver_reads_rates_the_dollar_gold_and_copper_as_one_voice() -> None:
    quotes = _with(US10Y=-0.06, DXY=-0.4, GC=0.9, COPPER=1.2)
    sil = drivers.build(_snap(quotes), "rth", NOW)["books"]["SIL"]
    v = _votes(sil)
    assert [v[k]["vote"] for k in ("yields", "dollar", "gold", "copper")] == ["long"] * 4
    assert "silver follows it" in v["gold"]["note"]
    assert "industrial half" in v["copper"]["note"]
    # No equity vol read, no credit, no sectors: they are not silver's.
    assert not {"vix_dir", "vix_curve", "credit", "sectors", "leaders", "hw_prints"} & set(v)
    fam = {f["key"]: f for f in sil["families"]}
    assert (fam["rates"]["score"], fam["rates"]["live"], fam["rates"]["total"]) == (100, 4, 4)
    # 31 of the session's hundred, all of it long, and nothing else live.
    assert (sil["bias"], sil["score"], sil["coverage"]) == ("long", 31, 31)


@pytest.mark.parametrize(("pct", "vote"), [(0.4, "long"), (0.39, "neutral"), (-0.4, "short")])
def test_gold_votes_for_silver_from_four_tenths_of_a_percent(pct: float, vote: str) -> None:
    v = _votes(drivers.build(_snap(_with(GC=pct)), "rth", NOW)["books"]["SIL"])
    assert v["gold"]["vote"] == vote


def test_gold_falling_and_copper_rising_cancel_inside_silvers_family() -> None:
    sil = drivers.build(_snap(_with(GC=-1.0, COPPER=1.0)), "rth", NOW)["books"]["SIL"]
    fam = {f["key"]: f for f in sil["families"]}
    assert fam["rates"]["score"] == 0 and sil["bias"] is None


# ---- crude ---------------------------------------------------------------------------------


def test_crude_reads_the_dollar_the_products_credit_and_copper_and_not_the_ten_year() -> None:
    quotes = _with(DXY=0.5, RBOB=-1.5, HEATOIL=-0.5, HYG=-0.3, COPPER=-0.9, US10Y=0.10)
    cl = drivers.build(_snap(quotes), "rth", NOW)["books"]["CL"]
    v = _votes(cl)
    assert [v[k]["vote"] for k in ("dollar", "products", "credit", "copper")] == ["short"] * 4
    assert v["products"]["value"] == "gasoline -1.50% · heating oil -0.50%"
    assert "demand" in v["copper"]["note"]
    # The 10-year moved ten basis points and crude has no row for it; nor the VIX.
    assert not {"yields", "vix_dir", "vix_curve", "sectors", "leaders"} & set(v)
    fam = {f["key"]: f["score"] for f in cl["families"]}
    assert (fam["rates"], fam["risk"]) == (-100, -100)      # dollar & products; demand
    # Copper speaks in crude's demand family, and in silver's metals family.
    assert bias.board_family("CL")["copper"] == "risk"
    assert bias.board_family("SIL")["copper"] == "rates"


@pytest.mark.parametrize(
    ("rbob", "heat", "vote"),
    [(1.0, 0.5, "long"), (1.0, 0.4, "neutral"), (-2.0, 0.5, "short"), (0.7, 0.7, "neutral")],
)
def test_the_products_vote_on_their_average(rbob: float, heat: float, vote: str) -> None:
    v = _votes(drivers.build(_snap(_with(RBOB=rbob, HEATOIL=heat)), "rth", NOW)["books"]["CL"])
    assert v["products"]["vote"] == vote


def test_a_build_is_short_and_a_draw_is_long_against_consensus_where_there_is_one() -> None:
    def inv(actual: float | None, consensus: float | None = None, **kw: Any) -> dict[str, Any]:
        snap = _snap(_with(), [_inventories(actual, consensus, **kw)])
        return _votes(drivers.build(snap, "rth", NOW)["books"]["CL"])["inventories"]

    # A 4.7M build against a 1.5M forecast: 3.2M more in store than expected.
    build = inv(4_657_000.0, 1_500_000.0)
    assert build["vote"] == "short" and build["value"] == "+4.7M bbl vs +1.5M bbl expected"
    assert "+3.2M bbl against consensus" in build["note"]
    # A build smaller than forecast is a miss the other way: long.
    assert inv(500_000.0, 2_000_000.0)["vote"] == "long"
    # Inside a million barrels of the forecast is no read.
    assert inv(2_400_000.0, 2_000_000.0)["vote"] == "neutral"
    # The stand-in feed carries no forecast: the week's change itself is the fact.
    bare = inv(-3_100_000.0)
    assert bare["vote"] == "long" and "no consensus on the feed" in bare["note"]
    assert inv(4_657_000.0)["vote"] == "short"
    assert inv(600_000.0)["vote"] == "neutral"


def test_inventories_vote_on_their_day_only_and_say_when_they_are_due() -> None:
    def inv(calendar: list[dict[str, Any]], now: datetime = NOW) -> dict[str, Any]:
        return _votes(drivers.build(_snap(_with(), calendar), "rth", now)["books"]["CL"])[
            "inventories"]

    # Due later today: it cannot vote yet.
    early = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)       # 09:00 ET
    due = inv([_inventories(None, released=False)], early)
    assert due["live"] is False and due["note"] == "due 10:30 ET today"
    # The day after: last week's figure is not today's read, and the next one is named.
    next_wed = ET_1030 + 7 * 86400
    thursday = datetime(2026, 11, 19, 16, 0, tzinfo=UTC)
    stale = inv([_inventories(4_657_000.0), _inventories(None, released=False, ts=next_wed)],
                thursday)
    assert stale["live"] is False and "next Wed 10:30 ET" in stale["note"]
    # The private survey the evening before is not the report.
    api = {**_inventories(-5_000_000.0), "event": "API Weekly Crude Oil Stock"}
    assert inv([api])["live"] is False
    assert inv([])["note"] == "no inventories report today — none on the calendar"


def test_a_growth_print_is_demand_for_crude_and_is_only_read_on_an_index_book() -> None:
    def retail(actual: float) -> dict[str, Any]:
        # The read is the collector's, off the surprise: 0.3 was expected.
        ts = datetime(2026, 11, 18, 13, 30, tzinfo=UTC).timestamp()     # 08:30 ET
        return {"event": "Retail Sales m/m", "region": "us", "country": "United States",
                "score": 5, "themes": ["growth"], "core": True, "ts": ts, "released": True,
                "actual": actual, "consensus": 0.3}

    board = drivers.build(_snap(_with(), [retail(0.9)]), "rth", NOW)["books"]
    cl, nq = _votes(board["CL"])["prints"], _votes(board["NQ"])["prints"]
    assert cl["vote"] == "long" and cl["label"] == "US growth prints"
    assert "more demand for the barrel" in cl["note"]
    # The same print on NQ is named and not counted, as it always was.
    assert nq["vote"] == "neutral" and nq["live"] is False
    cold = drivers.build(_snap(_with(), [retail(-0.4)]), "rth", NOW)["books"]["CL"]
    assert _votes(cold)["prints"]["vote"] == "short"


def test_silver_and_crude_have_no_positioning_row_that_says_a_feed_is_down() -> None:
    board = drivers.build(_snap(_with()), "rth", NOW)["books"]
    assert board["SIL"]["context"] == [] and board["CL"]["context"] == []
    # NQ's still says so when the CFTC has not answered.
    assert board["NQ"]["context"][0]["key"] == "cot"


def test_a_price_under_a_thousand_keeps_its_cents_and_a_distance_its_prices_terms() -> None:
    assert drivers._px(49.121) == "49.12" and drivers._px(28_034.75) == "28,035"
    # 200 points off an NQ flip is "200"; 0.88 off silver's is "0.88".
    assert drivers._px(200.0, 28_298.0) == "200" and drivers._px(0.879, 50.0) == "0.88"


# ---- the brief ---------------------------------------------------------------------------


def test_the_reports_four_subjects_and_the_books_behind_each() -> None:
    assert report.books_for("indexes") == ["NQ", "ES"]
    assert report.books_for("GC") == ["GC"]
    assert report.books_for("SIL") == ["SIL"]
    assert report.books_for("CL") == ["CL"]
    # What a note stored before the page was written about still resolves.
    assert report.books_for("all") == ["NQ", "ES", "GC"]
    assert report.books_for("NQ") == ["NQ"]
    assert report.resolve_asset("nonsense") == "all"
    for a in ("indexes", "GC", "SIL", "CL"):
        assert report.ASSETS[a]["label"] and report.ASSETS[a]["drivers"]
    assert report.ASSETS["indexes"]["instruments"] == "NQ/QQQ and ES/SPY"


def test_a_silver_or_crude_brief_is_scoped_to_its_book_and_told_what_drives_it() -> None:
    snap = _snap(_with(GC=0.9), [_inventories(None, released=False,
                                              ts=NOW.timestamp() + 3600)])
    snap["clock"] = {"et": "2026-11-18T11:00:00-05:00"}
    snap["drivers"] = drivers.build(snap, "rth", NOW)
    for asset, key, word in (("SIL", "SI_silver_futures", "SILVER"),
                             ("CL", "CL_crude_futures", "CRUDE")):
        facts = report.build_facts(snap, "ny", asset)
        assert facts["books"] == [asset]
        assert facts["snapshot"][0]["key"] == asset
        assert list(facts["drivers"]) == [asset] and facts["heavyweights"] == {}
        digest = report.build_digest(snap, "ny", asset, facts)
        assert list(digest["the_book_this_note_is_about"]) == [key]
        assert list(digest["engine_driver_board"]) == [asset]
        assert "cboe_put_call" not in digest["positioning"]
        prompt = report.system_prompt("ny", asset)
        assert f"THIS BRIEF IS ABOUT {report.ASSETS[asset]['instruments'].upper()}" in prompt
        assert word in prompt and "NOT an equity index" in prompt
    # Silver's snapshot carries gold and copper beside it; crude's, Brent and the products.
    sil = [r["key"] for r in report.build_facts(snap, "ny", "SIL")["snapshot"]]
    assert {"GOLD", "COPPER"} <= set(sil) and "SILVER" not in sil
    cl = report.build_facts(snap, "ny", "CL")
    assert {"BRENT", "RBOB", "HEATOIL", "COPPER"} <= {r["key"] for r in cl["snapshot"]}
    assert "WTI" not in {r["key"] for r in cl["snapshot"]}          # it is the book, not context
    # Crude's own release is on its catalyst list though the calendar does not call it core.
    assert "Crude Oil Inventories" in [c["title"] for c in cl["catalysts"]]
    assert "Crude Oil Inventories" not in [
        c["title"] for c in report.build_facts(snap, "ny", "indexes")["catalysts"]]


def test_the_indexes_are_one_subject_with_both_futures_and_both_funds_in_focus() -> None:
    snap = _snap([*_with(), _q("QQQ", 680.0), _q("SPY", 750.0)])
    snap["clock"] = {"et": "2026-11-18T11:00:00-05:00"}
    snap["drivers"] = drivers.build(snap, "rth", NOW)
    facts = report.build_facts(snap, "ny", "indexes")
    digest = report.build_digest(snap, "ny", "indexes", facts)
    assert list(digest["the_book_this_note_is_about"]) == ["NQ_futures", "QQQ", "ES_futures", "SPY"]
    assert "GC_gold_futures" in digest["other_books_context_only"]
    assert list(digest["engine_driver_board"]) == ["NQ", "ES"]
    assert "Calls and reads are issued for NQ, ES and nothing else" in report.system_prompt(
        "ny", "indexes").replace("\n", " ").replace("  ", " ")


def test_a_model_naming_a_book_in_words_is_understood() -> None:
    assert report._BOOK_WORDS["SILVER"] == "SIL"
    assert {report._BOOK_WORDS[w] for w in ("CRUDE", "OIL", "WTI", "CRUDE OIL")} == {"CL"}
    assert set(report.SCHEMA["properties"]["calls"]["items"]["properties"]["book"]["enum"]) == set(
        drivers.BOOKS)
