"""The Market Outlook (outlook.py): the markets read against each other as one pattern.

The worked case is Fri 20 Nov 2026, the close the card was mocked on: the S&P -3.2% and
the Nasdaq -4.9% (three usual days each), gold -4.0% and silver -7.3% (three), the
10-year note +0.7% (two), the dollar flat.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from newsterminal import outlook as ol

ET = ol.ET


def _at(*a: int) -> datetime:
    return datetime(*a, tzinfo=ET).astimezone(UTC)  # type: ignore[misc]


def _legs(**kw: float) -> dict[str, float | None]:
    base: dict[str, float | None] = dict.fromkeys(ol.LEGS, 0.0)
    return {**base, **kw}


#: That Friday's legs, in usual days.
FRIDAY = _legs(stocks=-3.0, bonds=2.1, dollar=0.2, gold=-2.9, silver=-3.1, oil=0.6, bitcoin=-0.4)


def test_the_patterns_are_read_off_stocks_bonds_and_gold() -> None:
    assert ol.classify(FRIDAY) == "forced"
    # The owner's own case: "if all drop at the same time".
    assert ol.classify(_legs(stocks=-2.0, bonds=-1.0, gold=-1.5, dollar=1.2)) == "sold"
    assert ol.classify(_legs(stocks=-1.2, bonds=-1.4, gold=0.1)) == "rates_shock"
    assert ol.classify(_legs(stocks=-1.2, bonds=1.1, gold=0.9)) == "risk_off"
    assert ol.classify(_legs(stocks=-1.2, dollar=0.8)) == "risk_off"
    assert ol.classify(_legs(stocks=1.0, bonds=-0.9)) == "risk_on"
    assert ol.classify(_legs(stocks=1.0, bonds=0.8)) == "rates_relief"
    assert ol.classify(_legs(stocks=1.0, bonds=0.8, gold=0.7)) == "rally"
    # Stocks moving and nothing else: said as that, either way.
    assert ol.classify(_legs(stocks=-1.5)) == ol.classify(_legs(stocks=1.5)) == "stocks_alone"
    # Stocks flat: mixed if anything else moved, quiet if nothing did.
    assert ol.classify(_legs(gold=1.4, oil=-0.9)) == "mixed"
    assert ol.classify(_legs(stocks=0.4, bonds=-0.4, gold=0.3)) == "quiet"
    # A move starts at half a usual day, the bias board's own mark.
    assert ol.classify(_legs(stocks=-0.5, bonds=0.5)) == "risk_off"
    assert ol.classify(_legs(stocks=-0.49, bonds=0.5)) == "mixed"
    # Without one of the three it reads, there is no pattern to give.
    assert ol.classify({**FRIDAY, "gold": None}) is None


def test_every_side_has_its_mirror() -> None:
    # Flip every sign and a down pattern is its up one: nothing is read harder one way.
    mirror = {"sold": "rally", "rates_shock": "rates_relief", "risk_off": "risk_on",
              "stocks_alone": "stocks_alone", "mixed": "mixed", "quiet": "quiet"}
    cases = [_legs(stocks=-2.0, bonds=-1.0, gold=-1.5), _legs(stocks=-1.2, bonds=-1.4),
             _legs(stocks=-1.2, bonds=1.1), _legs(stocks=-1.2, gold=0.9),
             _legs(stocks=-1.2, dollar=0.8), _legs(stocks=-1.5), _legs(gold=1.4),
             _legs(stocks=0.1), _legs(stocks=-1.0, dollar=-0.9)]
    for legs in cases:
        flipped = {k: (None if v is None else -v) for k, v in legs.items()}
        assert ol.classify(flipped) == mirror[ol.classify(legs) or ""], legs
    # The one with no mirror: gold UP with stocks, bonds not, is no pattern of its own.
    assert ol.classify(_legs(stocks=3.0, bonds=-2.1, gold=2.9)) == "risk_on"
    assert ol.classify(_legs(stocks=3.0, gold=2.9)) == "mixed"


def test_what_moved_is_said_in_words() -> None:
    assert ol.what_of(FRIDAY) == "stocks and metals sold, bonds and oil bid"
    assert ol.what_of(_legs(stocks=-2.0, bonds=-1.0, gold=-1.5, bitcoin=-1.0, dollar=1.2)) == \
        "stocks, bonds, gold and bitcoin sold, dollar up"
    assert ol.what_of(_legs(stocks=1.0, silver=0.9, dollar=-0.6)) == \
        "stocks and silver bid, dollar down"
    assert ol.what_of(_legs(stocks=0.2)) == ""


def test_the_arrows_count_usual_days() -> None:
    assert [ol.arrows(m) for m in (0.2, 0.5, 1.4, 1.5, 2.4, 2.5, 3.1)] == [0, 1, 1, 2, 2, 3, 3]
    assert [ol.arrows(m) for m in (-0.2, -0.6, -2.1, -2.9)] == [0, -1, -2, -3]
    assert ol.arrows(None) == 0


def test_the_quotes_say_which_day_they_are_about() -> None:
    shut = {"feed": "closed", "quote_time": _at(2026, 11, 20, 16, 59, 58).timestamp()}
    # A Saturday, and Sunday before the reopen: the futures are shut, Friday's close.
    assert ol.state_of(shut, _at(2026, 11, 21, 12, 0)) == ("close", date(2026, 11, 20))
    assert ol.state_of(shut, _at(2026, 11, 22, 17, 30)) == ("close", date(2026, 11, 20))
    # The daily break, 17:00 to 18:00 ET: the day just finished.
    brk = {"feed": "closed", "quote_time": _at(2026, 11, 18, 16, 59, 59).timestamp()}
    assert ol.state_of(brk, _at(2026, 11, 18, 17, 20)) == ("close", date(2026, 11, 18))
    live = {"feed": "delayed", "quote_time": _at(2026, 11, 18, 10, 30).timestamp()}
    # From the pre-market's start to the break the quotes are today's.
    assert ol.state_of(live, _at(2026, 11, 18, 4, 0)) == ("live", date(2026, 11, 18))
    assert ol.state_of(live, _at(2026, 11, 18, 16, 59)) == ("live", date(2026, 11, 18))
    # The night: a session a few hours old, for the day it runs into.
    assert ol.state_of(live, _at(2026, 11, 18, 19, 0)) == ("overnight", date(2026, 11, 19))
    assert ol.state_of(live, _at(2026, 11, 19, 3, 59)) == ("overnight", date(2026, 11, 19))
    # A US holiday with the futures trading is live, whatever the stock calendar says.
    assert ol.state_of(live, _at(2026, 11, 26, 10, 0)) == ("live", date(2026, 11, 26))


# ---- the sentiment scale ---------------------------------------------------------------------

def test_the_scale_reads_risk_and_not_the_havens() -> None:
    # Fri 20 Nov: stocks -3.0 usual days, the VIX +2.2, high yield -1.0, bitcoin -2.5.
    got = ol.sentiment({"stocks": -3.0, "vix": 2.2, "credit": -1.0, "bitcoin": -2.5})
    assert got is not None and (got["score"], got["label"]) == (-78, "Extreme fear")
    assert [(x["key"], x["weight"], x["mult"]) for x in got["legs"]] == \
        [("stocks", 40, -3.0), ("vix", 25, -2.2), ("credit", 20, -1.0), ("bitcoin", 15, -2.5)]
    # Its mirror, to the point.
    up = ol.sentiment({"stocks": 3.0, "vix": -2.2, "credit": 1.0, "bitcoin": 2.5})
    assert up is not None and (up["score"], up["label"]) == (78, "Extreme greed")
    # Every leg at the cap or past it is the end of the scale, not beyond it.
    assert (ol.sentiment({"stocks": -9.0, "vix": 9.0, "credit": -9.0, "bitcoin": -9.0})
            or {})["score"] == -100
    # A leg not read is left out and the rest carry its weight: stocks alone at -1.5 usual
    # days is -50, as it is with the three others moving in step.
    assert (ol.sentiment({"stocks": -1.5}) or {})["score"] == -50
    assert (ol.sentiment({"stocks": -1.5, "vix": 1.5, "credit": -1.5, "bitcoin": -1.5})
            or {})["score"] == -50
    # No stocks, no scale.
    assert ol.sentiment({"vix": 2.0, "bitcoin": -1.0}) is None


def test_the_scales_words_start_where_they_say() -> None:
    words = {-100: "Extreme fear", -60: "Extreme fear", -59: "Fear", -20: "Fear",
             -19: "Neutral", 0: "Neutral", 19: "Neutral", 20: "Greed", 59: "Greed",
             60: "Extreme greed", 100: "Extreme greed"}
    assert {s: ol.sentiment_word(s) for s in words} == words


def test_a_cash_quote_counts_only_when_it_is_the_days() -> None:
    fri, mon = date(2026, 11, 20), date(2026, 11, 23)
    vix = {"key": "VIX", "pct": 26.2, "quote_time": _at(2026, 11, 20, 16, 15).timestamp()}
    assert ol._dated(vix, fri) == 26.2
    # Monday 05:00 ET: the VIX and high yield still hold Friday's change. Not today's.
    assert ol._dated(vix, mon) is None
    hyg = {"key": "HYG", "pct": -0.26, "quote_time": _at(2026, 11, 20, 16, 0).timestamp(),
           "ext": {"kind": "pre", "pct": 0.12, "day": "2026-11-23"}}
    # Its pre-market trade of the day is.
    assert ol._dated(hyg, mon) == 0.12 and ol._dated(hyg, fri) == -0.26
    assert ol._dated(None, fri) is None


# ---- the card, off a snapshot ---------------------------------------------------------------

#: Each leg's usual day in the fake history (percent) and its Friday change (percent).
USUAL = {"ES": 1.07, "NQ": 1.62, "ZN": 0.33, "DXY": 0.27, "GC": 1.38, "SILVER": 2.39,
         "WTI": 2.37, "BTC": 2.5}
FRI_PCT = {"ES": -3.20, "NQ": -4.92, "ZN": 0.69, "DXY": 0.03, "GC": -3.98, "SILVER": -7.39,
           "WTI": 1.43, "BTC": -0.99}


def _context(last_day: date, last: dict[str, float], n: int = 40) -> list[dict[str, Any]]:
    """Daily closes that alternate up and down each key's usual day, so its usual day is
    exactly that, ending with `last` (percent) on `last_day`. Weekdays only."""
    days: list[date] = []
    d = last_day
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    rows = []
    for key, usual in USUAL.items():
        closes = [100.0]
        for i in range(1, n - 1):
            closes.append(closes[-1] * (1 + (usual if i % 2 else -usual) / 100.0))
        closes.append(closes[-1] * (1 + last[key] / 100.0))
        rows.append({"key": key, "hist": {"days": [x.isoformat() for x in days], "closes": closes}})
    return rows


def _snap(feed: str, quote_at: datetime, pct: dict[str, float],
          context: list[dict[str, Any]]) -> dict[str, Any]:
    quotes = [{"key": k, "pct": v, "feed": feed, "quote_time": quote_at.timestamp()}
              for k, v in pct.items()]
    quotes.append({"key": "US10Y", "chg": -0.14, "pct": -2.77, "feed": feed,
                   "quote_time": quote_at.timestamp()})
    return {"quotes": quotes, "context": context}


def test_the_card_on_the_friday_it_was_mocked_on() -> None:
    fri = date(2026, 11, 20)
    snap = _snap("closed", _at(2026, 11, 20, 16, 59, 58), FRI_PCT, _context(fri, FRI_PCT))
    out = ol.build(snap, _at(2026, 11, 21, 12, 0))
    assert out["ok"] and (out["state"], out["day"], out["label"]) == \
        ("close", "2026-11-20", "Fri 20 Nov · close")
    assert (out["key"], out["name"]) == ("forced", "Forced selling")
    assert out["what"] == "stocks and metals sold, bonds and oil bid"
    assert out["tell"] == "Unusual: gold fell with stocks."
    rows = {r["key"]: r for r in out["rows"]}
    assert [r["key"] for r in out["rows"]] == [k for k, _, _ in ol.ROWS]
    es = rows["ES"]
    assert (es["group"], es["name"], es["pct"]) == ("Stocks", "S&P 500", -3.2)
    assert (rows["ES"]["mult"], rows["ES"]["arrows"]) == (-3.0, -3)
    assert (rows["ZN"]["mult"], rows["ZN"]["arrows"]) == (2.1, 2)
    assert (rows["DXY"]["mult"], rows["DXY"]["arrows"]) == (0.1, 0)
    # The bond row: named so "10Y" cannot be read as a time span, its move the note's
    # price, and the yield's change beside it, on that row alone.
    zn = rows["ZN"]
    assert (zn["group"], zn["name"], zn["pct"]) == ("Bonds", "US 10-year", 0.69)
    assert zn["note"] == "The 10-year yield -14bp" and zn["yield_bp"] == -14.0
    assert all(r["yield_bp"] is None for r in out["rows"] if r["key"] != "ZN")
    assert all(r["sized"] for r in out["rows"])
    # The pattern on the sessions the closes hold: that Friday alone in a history of
    # ordinary days, each read in the usual day of the twenty before it.
    assert out["seen"]["n"] == 1 and out["seen"]["of"] >= 20


def test_the_yield_rides_the_bond_row_only_when_it_is_the_days() -> None:
    # Monday 05:00 ET: the note future has traded since Sunday evening, so the row's move
    # is Monday's. The cash yield has not opened and still holds Friday's -14bp: beside
    # Monday's price it would be another day's figure, so the row carries none.
    fri = date(2026, 11, 20)
    snap = _snap("delayed", _at(2026, 11, 23, 4, 59), FRI_PCT, _context(fri, FRI_PCT))
    for q in snap["quotes"]:
        if q["key"] == "US10Y":
            q["quote_time"] = _at(2026, 11, 20, 14, 59).timestamp()
    zn = next(r for r in ol.build(snap, _at(2026, 11, 23, 5, 0))["rows"] if r["key"] == "ZN")
    assert zn["pct"] == 0.69 and zn["yield_bp"] is None and zn["note"] is None
    stale = {"chg": -0.14, "quote_time": _at(2026, 11, 20, 14, 59).timestamp()}
    assert ol.yield_bp(stale, fri) == -14.0 and ol.yield_bp(stale, date(2026, 11, 23)) is None
    assert ol.yield_bp(None, fri) is None


def test_bitcoin_on_a_shut_market_is_read_for_the_same_day() -> None:
    fri = date(2026, 11, 20)
    context = _context(fri, FRI_PCT)
    # Saturday's coin is up 4% on its own day; the card is still about Friday.
    quotes = {**FRI_PCT, "BTC": 4.0}
    out = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), quotes, context),
                   _at(2026, 11, 21, 12, 0))
    btc = next(r for r in out["rows"] if r["key"] == "BTC")
    assert btc["pct"] == -0.99

    # AS YAHOO SERVED IT AT 03:40 UTC ON SAT 21 NOV: no daily bar for the 20th at all (19
    # Nov closed 61,901.82; the next bar was the 21st, still forming). Friday's close is
    # the quote's own previous close, 58,802.60: -5.0%, where the card's first build
    # printed Saturday's -2.8% under "Fri 20 Nov".
    row = {"key": "BTC", "hist": {"days": ["2026-11-18", "2026-11-19", "2026-11-21"],
                                  "closes": [62987.27, 61901.82, 57036.39]}}
    quote = {"key": "BTC", "last": 57144.1, "prev": 58802.6, "pct": -2.82}
    sat = _at(2026, 11, 21, 12, 0)
    assert round(ol.coin_change(row, quote, fri, sat) or 0.0, 2) == -5.01
    # Sunday: Friday is two days back, its bar is still missing, and nothing else has its
    # close. The row is left off the card rather than given another day's move.
    assert ol.coin_change(row, quote, fri, _at(2026, 11, 22, 12, 0)) is None
    gone = [c for c in context if c["key"] != "BTC"] + [row]
    out = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), quotes, gone),
                   _at(2026, 11, 22, 12, 0))
    assert out["ok"] and "BTC" not in {r["key"] for r in out["rows"]}
    # Unless that day's own record line has it: written on the Saturday, read on the Sunday.
    kept = {"day": "2026-11-20", "rows": [{"key": "BTC", "pct": -5.01, "mult": -2.0}]}
    out = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), quotes, gone),
                   _at(2026, 11, 22, 12, 0), last=kept)
    assert next(r for r in out["rows"] if r["key"] == "BTC")["pct"] == -5.01
    # Friday 17:20 ET, the daily break: the coin's own day is still running, so its quote
    # is that day's move.
    assert ol.coin_change(row, quote, fri, _at(2026, 11, 20, 17, 20)) == -2.82

    # With the markets trading, its quote is the day's, as every other row's is.
    out = ol.build(_snap("delayed", _at(2026, 11, 23, 10, 0), quotes, context),
                   _at(2026, 11, 23, 10, 0))
    btc = next(r for r in out["rows"] if r["key"] == "BTC")
    assert out["state"] == "live" and btc["pct"] == 4.0
    assert out["label"] == "Mon 23 Nov · live"
    assert out["tell"] == "Unusual: gold is falling with stocks."


def test_a_market_not_read_yet_is_said_and_not_guessed() -> None:
    fri = date(2026, 11, 20)
    pct = {k: v for k, v in FRI_PCT.items() if k != "GC"}
    out = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), pct, _context(fri, FRI_PCT)),
                   _at(2026, 11, 21, 12, 0))
    assert out["ok"] is False and "gold" in out["why"]
    assert ol.build({}, _at(2026, 11, 21, 12, 0))["ok"] is False


def test_too_little_history_sizes_a_move_by_the_stated_usual_day() -> None:
    out = ol.build(_snap("delayed", _at(2026, 11, 23, 10, 0), FRI_PCT, []),
                   _at(2026, 11, 23, 10, 0))
    rows = {r["key"]: r for r in out["rows"]}
    assert out["ok"] and not rows["ES"]["sized"] and not rows["BTC"]["sized"]
    assert rows["BTC"]["mult"] == round(-0.99 / ol.BTC_USUAL, 1)
    assert out["seen"] == {"n": 0, "of": 0}


def test_a_close_is_not_written_before_the_history_has_sized_it() -> None:
    # 25 seconds after a restart on Sat 21 Nov the daily closes had not been read: the
    # S&P's -3.2% was 3.6 stated usual days, not the measured 3.0, and that went on file.
    early = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), FRI_PCT, []),
                     _at(2026, 11, 21, 12, 0))
    assert early["ok"] and early["state"] == "close"
    assert next(r for r in early["rows"] if r["key"] == "ES")["mult"] == -3.6
    assert ol.record_line(early, _at(2026, 11, 21, 12, 0)) is None


# ---- the record ------------------------------------------------------------------------------

def test_a_finished_session_is_written_once_and_shown_overnight(tmp_path: Any) -> None:
    fri = date(2026, 11, 20)
    context = _context(fri, FRI_PCT)
    close = ol.build(_snap("closed", _at(2026, 11, 20, 16, 59, 58), FRI_PCT, context),
                     _at(2026, 11, 20, 17, 5))
    line = ol.record_line(close, _at(2026, 11, 20, 17, 5))
    assert line is not None and (line["day"], line["key"]) == ("2026-11-20", "forced")
    path = str(tmp_path / "outlook_record.jsonl")
    ol.append(line, path)
    assert ol.read(path) == [line] and ol.read(str(tmp_path / "none.jsonl")) == []

    # Sunday 19:00 ET: the futures are back and have barely moved. The card is Friday's
    # close as it was written, with the night in a line.
    night = {k: 0.1 for k in FRI_PCT}
    night["ES"], night["NQ"] = -0.9, -1.2
    snap = _snap("delayed", _at(2026, 11, 22, 18, 59), night, context)
    out = ol.build(snap, _at(2026, 11, 22, 19, 0), last=ol.read(path)[-1])
    assert (out["state"], out["from"]) == ("overnight", "record")
    assert out["label"] == "Fri 20 Nov · close"
    assert out["key"] == "forced" and out["tell"] == "Unusual: gold fell with stocks."
    assert out["rows"] == close["rows"]
    assert out["overnight"] == {"name": "Stocks alone", "what": "stocks sold"}
    # A read off the record, or a live one, is never written back.
    assert ol.record_line(out, _at(2026, 11, 22, 19, 0)) is None
    live = ol.build(_snap("delayed", _at(2026, 11, 23, 10, 0), FRI_PCT, context),
                    _at(2026, 11, 23, 10, 0))
    assert ol.record_line(live, _at(2026, 11, 23, 10, 0)) is None
    # No record yet: the night's own read, labelled as the night.
    bare = ol.build(snap, _at(2026, 11, 22, 19, 0))
    assert (bare["from"], bare["label"], bare["key"]) == \
        ("live", "Overnight · since 18:00 ET", "stocks_alone")
