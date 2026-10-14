"""How current a board price is (quotes.feed_state) — worked against Yahoo's
own spark meta, captured at 01:16:46 ET on Wed 14 Oct 2026 (audit)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from newsterminal.sources import quotes

ET = ZoneInfo("America/New_York")
NOW = 1791955006  # Wed 14 Oct 2026 05:16:46 UTC = 01:16:46 ET


def _et(y: int, mo: int, d: int, h: int, mi: int) -> float:
    return datetime(y, mo, d, h, mi, tzinfo=ET).timestamp()


def _meta(sym: str, t: float | None, start: int | None = None,
          end: int | None = None) -> dict[str, object]:
    m: dict[str, object] = {"symbol": sym, "regularMarketTime": t}
    if start is not None:
        m["currentTradingPeriod"] = {"regular": {"start": start, "end": end}}
    return m


# Yahoo's periods as served at NOW: a 24-hour market's is just the calendar
# day; a cash market's is the session it is waiting for.
ES_PERIOD = (1791950400, 1792036740)    # Wed 00:00 → 23:59 ET
BTC_PERIOD = (1791936000, 1792022340)   # Wed 00:00 → 23:59 UTC
TNX_PERIOD = (1791980400, 1792004400)   # Wed 08:20 → 15:00 ET
SPY_PERIOD = (1791984600, 1792008000)   # Wed 09:30 → 16:00 ET


def test_es_on_yahoo_is_ten_minutes_late() -> None:
    # Printed 01:06:41 ET.
    assert quotes.feed_state(_meta("ES=F", 1791954401, *ES_PERIOD), NOW) == ("delayed", 10.1)
    # Just past midnight with the old day's period still served, a print after
    # its end means ES traded on — the calendar day's edge is not a close.
    late = ES_PERIOD[1] + 900
    assert quotes.feed_state(_meta("ES=F", late - 300, *ES_PERIOD), late) == ("delayed", 5.0)


def test_bitcoin_trades_through_the_night() -> None:
    assert quotes.feed_state(_meta("BTC-USD", 1791954999, *BTC_PERIOD), NOW) == ("live", 0.1)


def test_the_cash_markets_are_closed_at_one_in_the_morning() -> None:
    # Tuesday's last prints — the 10-year 14:59:55 ET, SPY the 16:00:00
    # close — before Wednesday's sessions start.
    assert quotes.feed_state(_meta("^TNX", 1791917995, *TNX_PERIOD), NOW)[0] == "closed"
    assert quotes.feed_state(_meta("SPY", 1791921600, *SPY_PERIOD), NOW)[0] == "closed"
    # After Wednesday's close, the 16:00:00 print is the close itself.
    after = _et(2026, 10, 14, 16, 30)
    assert quotes.feed_state(_meta("SPY", SPY_PERIOD[1], *SPY_PERIOD), after)[0] == "closed"
    # The VIX settles a second past its stated end: still the close.
    vix = _meta("^VIX", SPY_PERIOD[1] + 1, *SPY_PERIOD)
    assert quotes.feed_state(vix, _et(2026, 10, 14, 17, 0))[0] == "closed"


def test_globex_halts_read_closed() -> None:
    fri_close = _et(2026, 10, 16, 17, 0)
    for at in (_et(2026, 10, 17, 10, 0),      # Saturday
               _et(2026, 10, 18, 17, 30),     # Sunday before the reopen
               _et(2026, 10, 16, 20, 0),      # Friday evening
               _et(2026, 10, 14, 17, 30)):    # the daily halt hour
        assert quotes.feed_state(_meta("ES=F", fri_close, *ES_PERIOD), at)[0] == "closed"
    # Sunday 18:05 with the 17:55 print ten minutes late: trading again.
    sun = _et(2026, 10, 18, 18, 5)
    assert quotes.feed_state(_meta("ES=F", sun - 600), sun) == ("delayed", 10.0)


def test_no_print_for_half_an_hour_inside_its_hours_is_stale() -> None:
    grains = _meta("ZW=F", NOW - 45 * 60, NOW - 3600, NOW + 3600)
    assert quotes.feed_state(grains, NOW) == ("stale", 45.0)
    # No trading period in the meta: the lag alone decides.
    assert quotes.feed_state(_meta("X", NOW - 60), NOW)[0] == "live"
    assert quotes.feed_state(_meta("X", None), NOW) == ("stale", None)


def test_the_row_carries_the_state() -> None:
    period = {"start": ES_PERIOD[0], "end": ES_PERIOD[1]}
    resp = {"meta": {"symbol": "ES=F", "regularMarketPrice": 6000.0,
                     "chartPreviousClose": 5990.0, "regularMarketTime": 1791954401,
                     "currentTradingPeriod": {"regular": period}}}
    row = quotes._row("ES", "S&P 500 fut", "core", "px", resp, now=NOW)
    assert row is not None and (row["feed"], row["lag_min"]) == ("delayed", 10.1)
