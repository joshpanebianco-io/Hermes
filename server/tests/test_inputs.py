"""The driver board's new inputs, parsed and read: the CFTC rows, Cboe's daily
ratios, Yahoo's short interest, EDGAR's report history — and the print read
with its per-book implication, and the profile's sentence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from newsterminal import profile, releases
from newsterminal.sources import cboepc, cot, earnhist, shortint

# ----------------------------------------------------------------------- COT


def _cot_rows(nets: list[float], oi: float = 1_000_000.0) -> list[dict[str, Any]]:
    """Weekly rows, newest first, with leveraged funds net at each value."""
    out = []
    d = date(2026, 10, 13)
    for i, net in enumerate(nets):
        day = date.fromordinal(d.toordinal() - 7 * i)
        out.append({"report_date_as_yyyy_mm_dd": f"{day.isoformat()}T00:00:00.000",
                    "open_interest_all": str(oi),
                    "lev_money_positions_long": str(200_000 + net),
                    "lev_money_positions_short": "200000",
                    "asset_mgr_positions_long": "900000", "asset_mgr_positions_short": "100000"})
    return out


def test_cot_summary_net_change_percentile_and_word() -> None:
    nets = [-48_000.0] + [float(x) for x in range(-40_000, 60_000, 2_000)]  # 51 weeks
    s = cot.summarise(_cot_rows(nets), cot.MARKETS["ES"]["spec"], cot.MARKETS["ES"]["other"])
    assert s is not None
    assert s["as_of"] == "2026-10-13"
    assert s["net"] == -48_000 and s["chg"] == -8_000
    assert s["pctile"] == 2 and s["word"] == "crowded short"
    assert s["read"].startswith("Leveraged funds net short 48,000 contracts (5% of open interest)")
    assert "forced buyers" in s["read"]
    assert s["other"] == {"label": "Asset managers", "net": 800_000}


def test_cot_summary_handles_missing_rows_and_middling() -> None:
    assert cot.summarise([], cot.MARKETS["GC"]["spec"], cot.MARKETS["GC"]["other"]) is None
    s = cot.summarise(_cot_rows([0.0, 10_000.0, -10_000.0]), cot.MARKETS["ES"]["spec"],
                      cot.MARKETS["ES"]["other"])
    assert s is not None and s["word"] == "middling" and "No positioning edge" in s["read"]


# ------------------------------------------------------------------ put/call


def test_cboe_parse_and_reads() -> None:
    doc = {"ratios": [{"name": "TOTAL PUT/CALL RATIO", "value": "0.87"},
                      {"name": "EQUITY PUT/CALL RATIO", "value": "0.52"},
                      {"name": "INDEX PUT/CALL RATIO", "value": "1.02"},
                      {"name": "KPI BINARY OPTIONS PUT/CALL RATIO", "value": "0.00"}]}
    r = cboepc.parse(doc)
    assert r == {"total": 0.87, "equity": 0.52, "index": 1.02}
    assert cboepc.parse({"ratios": []}) is None
    assert "complacent" in (cboepc.equity_read(0.52) or "")
    assert "hedged" in (cboepc.equity_read(0.85) or "")
    assert "normal" in (cboepc.equity_read(0.65) or "")


def test_cboe_summary_averages_and_percentile_over_the_log() -> None:
    log = {f"2026-10-{d:02d}": {"equity": 0.5 + d * 0.01, "total": 0.9} for d in range(1, 22)}
    s = cboepc.summarise(log)
    assert s is not None
    assert s["date"] == "2026-10-21" and s["days"] == 21
    assert s["avg20"]["equity"] == round(sum(0.5 + d * 0.01 for d in range(2, 22)) / 20, 2)
    assert s["pctile"]["equity"] == 100
    assert s["read"]["equity"] is not None
    assert cboepc.summarise({}) is None


def test_cboe_latest_day_waits_for_the_file() -> None:
    # Wednesday 2026-10-21, 10:00 ET: today's is not out — yesterday's.
    assert cboepc.latest_day(datetime(2026, 10, 21, 14, 0, tzinfo=UTC)) == date(2026, 10, 20)
    # 16:45 ET: today's.
    assert cboepc.latest_day(datetime(2026, 10, 21, 20, 45, tzinfo=UTC)) == date(2026, 10, 21)
    # Saturday: Friday's.
    assert cboepc.latest_day(datetime(2026, 10, 24, 15, 0, tzinfo=UTC)) == date(2026, 10, 23)


# ------------------------------------------------------------ short interest


def test_short_interest_parse_and_flag() -> None:
    doc = {"quoteSummary": {"result": [{"defaultKeyStatistics": {
        "sharesShort": {"raw": 39_281_942}, "shortRatio": {"raw": 1.83},
        "shortPercentOfFloat": {"raw": 0.0242}, "floatShares": {"raw": 1_623_529_079},
        "dateShortInterest": {"raw": 1790726400, "fmt": "2026-09-30"},
        "sharesShortPriorMonth": {"raw": 41_712_630}}}]}}
    s = shortint.parse(doc)
    assert s == {"pct_float": 2.42, "days_to_cover": 1.83, "shares_short": 39_281_942.0,
                 "prior_month": 41_712_630.0, "float_shares": 1_623_529_079.0,
                 "as_of": "2026-09-30"}
    assert shortint.squeeze_flag(s, "short") is None
    heavy = {"pct_float": 22.0, "days_to_cover": 4.1}
    f = shortint.squeeze_flag(heavy, "short")
    assert f is not None and f["tone"] == "warn"
    assert f["text"] == ("Squeeze risk: 22% of the float is short, 4.1 days to cover — a failed "
                         "retest can run")
    g = shortint.squeeze_flag(heavy, "long")
    assert g is not None and g["tone"] == "info" and "fuel for a squeeze" in g["text"]
    assert shortint.squeeze_flag(heavy, None) is None
    assert shortint.parse({"quoteSummary": {"result": [{"defaultKeyStatistics": {}}]}}) is None


# ---------------------------------------------------------- report history


def _edgar(rows: list[tuple[str, ...]]) -> dict[str, Any]:
    """A submissions JSON from (form, items, acceptanceDateTime[, filingDate]),
    newest first; the filing date is the stamp's own day unless given."""
    return {"filings": {"recent": {
        "form": [r[0] for r in rows], "items": [r[1] for r in rows],
        "acceptanceDateTime": [r[2] for r in rows],
        "filingDate": [r[3] if len(r) > 3 else r[2][:10] for r in rows],
    }}}


def test_edgar_202_after_the_1730_cutoff_is_the_next_days_pre_market() -> None:
    doc = _edgar([
        # PepsiCo's real stamp: 17:57 ET on the 7th, public (and filed) on the 8th.
        ("8-K", "2.02,9.01", "2026-10-07T21:57:44.000Z", "2026-10-08"),
        # Duke's: 17:56 EST on the 4th, filed the 5th.
        ("8-K", "2.02,9.01", "2026-11-04T22:56:27.000Z", "2026-11-05"),
        # 17:40 ET with the same filing date (bad data): the stamp's own day stands.
        ("8-K", "2.02", "2026-06-10T21:40:00.000Z", "2026-06-10"),
    ])
    assert earnhist.parse_edgar(doc) == [
        {"date": "2026-11-05", "when": "pre"},
        {"date": "2026-10-08", "when": "pre"},
        {"date": "2026-06-10", "when": "after"},
    ]


def test_edgar_202s_are_dated_by_the_et_acceptance() -> None:
    doc = _edgar([
        # 16:30 ET in winter is 21:30 UTC; in summer 20:30 UTC (AAPL's real stamps).
        ("8-K", "2.02,9.01", "2026-11-02T21:30:23.000Z"),
        ("8-K/A", "2.02,9.01", "2026-10-31T13:00:00.000Z"),   # an amendment: skipped
        ("10-Q", "", "2026-10-31T12:00:00.000Z"),
        ("8-K", "5.02", "2026-10-15T20:00:00.000Z"),           # not results
        # 21:10 ET on the 21st is 01:10 UTC on the 22nd: the ET day is the day (with a
        # filing date that does not move it on; past 17:30 it usually would).
        ("8-K", "2.02", "2026-07-22T01:10:00.000Z", "2026-07-21"),
        ("8-K", "2.02,9.01", "2026-07-21T17:00:00.000Z"),     # same ET day, older: one a day
        ("8-K", "2.02,7.01,9.01", "2026-05-06T12:59:53.000Z"),  # 08:59 EDT
        ("8-K", "1.01, 2.02", "2026-02-03T17:00:00.000Z"),      # 12:00 EST, spaced items
    ])
    rows = earnhist.parse_edgar(doc)
    assert rows == [
        {"date": "2026-11-02", "when": "after"},
        {"date": "2026-07-21", "when": "after"},
        {"date": "2026-05-06", "when": "pre"},
        {"date": "2026-02-03", "when": "during"},
    ]
    assert earnhist.parse_edgar({}) == []
    missing = _edgar([("8-K", "2.02", "")])
    missing["filings"]["recent"]["filingDate"] = ["2026-08-04"]
    assert earnhist.parse_edgar(missing) == [{"date": "2026-08-04", "when": "unspecified"}]


def test_reports_pass_over_a_202_that_previews_a_later_one() -> None:
    # Tesla: deliveries under 2.02 on the 2nd, results three weeks later.
    filed = [{"date": d, "when": w} for d, w in (
        ("2027-01-02", "pre"), ("2026-10-21", "after"), ("2026-10-02", "pre"),
        ("2026-07-22", "after"), ("2026-07-02", "pre"), ("2026-04-22", "after"))]
    dates = [r["date"] for r in earnhist.reports(filed, "2027-02-03")]
    assert dates == ["2026-10-21", "2026-07-22", "2026-04-22"]
    # With no next report known, the newest 2.02 stands until its results land.
    assert earnhist.reports(filed)[0]["date"] == "2027-01-02"
    # A next date not rolled on yet is the newest report itself, not a later one.
    same = [{"date": "2026-11-17", "when": "after"}, {"date": "2026-08-26", "when": "after"}]
    assert [r["date"] for r in earnhist.reports(same, "2026-11-17")] == ["2026-11-17",
                                                                          "2026-08-26"]
    assert len(earnhist.reports([{"date": f"20{y:02d}-01-15", "when": "pre"}
                                 for y in range(10, 26)])) == earnhist.KEEP


def _tv_reply() -> dict[str, Any]:
    noon = int(datetime(2027, 2, 4, 12, tzinfo=UTC).timestamp())        # placeholder
    pre = int(datetime(2026, 11, 19, 12, tzinfo=UTC).timestamp())
    last = int(datetime(2026, 10, 21, 20, 6, tzinfo=UTC).timestamp())   # 16:06 ET
    return {"totalCount": 4, "data": [
        {"s": "NASDAQ:AAPL", "d": ["AAPL", "stock", ["common"], noon, 0, last, 1]},
        {"s": "NASDAQ:WMT", "d": ["WMT", "stock", ["common"], pre, -1, None, None]},
        {"s": "AMEX:SPY", "d": ["SPY", "fund", ["etf"], None, None, None, None]},
        {"s": "NYSE:JPM/PC", "d": ["JPM/PC", "stock", ["preferred"], pre, -1, last, 1]},
        {"s": "NYSE:BAD", "d": ["BAD", "stock"]},
    ]}


def test_tradingview_reply_gives_next_and_last() -> None:
    got = earnhist.parse_tv(_tv_reply())
    assert got["AAPL"] == {"next": {"date": "2027-02-04", "when": "unspecified"},
                           "last": {"date": "2026-10-21", "when": "after"}}
    assert got["WMT"] == {"next": {"date": "2026-11-19", "when": "pre"}, "last": None}
    assert got["SPY"] == {"next": None, "last": None}
    assert "JPM/PC" not in got and "BAD" not in got
    q = earnhist.next_query(["MSFT", "AAPL"])
    assert q["filter"][0] == {"left": "name", "operation": "in_range", "right": ["AAPL", "MSFT"]}
    assert q["columns"] == earnhist.NEXT_COLUMNS


def test_store_joins_edgar_and_tradingview(monkeypatch: Any) -> None:
    import json as _json

    from newsterminal.http import FetchResult
    asked: list[str] = []

    def fake_fetch(url: str, **kw: Any) -> FetchResult:
        asked.append(kw["key"])
        return FetchResult(True, _json.dumps(_tv_reply()).encode(), "live", 0.0, None)

    monkeypatch.setattr(earnhist, "fetch", fake_fetch)
    store = earnhist.EarnHistStore()
    filed = {"AAPL": [{"date": "2026-11-02", "when": "after"},
                      {"date": "2026-07-30", "when": "after"}],
             "TSM": []}                    # read, no 2.02: a foreign filer
    now = datetime(2026, 11, 17, 14, tzinfo=UTC)
    st = store.tick(["AAPL", "TSM", "WMT", "MSFT"], filed, now)
    assert store.view()["AAPL"] == filed["AAPL"]
    assert "TSM" not in store.view()           # no TradingView row for it either
    assert "WMT" not in store.view()           # not read yet, no last report on TradingView
    assert store.view_next() == {"AAPL": {"date": "2027-02-04", "when": "unspecified"},
                                 "WMT": {"date": "2026-11-19", "when": "pre"}}
    assert st.ok and st.items == 1 and st.error is None
    assert "waiting on EDGAR: WMT, MSFT" in st.notes
    assert "no report found: TSM" in st.notes
    # The same list inside NEXT_SEC asks nothing; a new name asks at once.
    store.tick(["AAPL", "TSM", "WMT", "MSFT"], filed, now)
    assert len(asked) == 1
    store.tick(["AAPL", "TSM", "WMT", "MSFT", "NVDA"], filed, now)
    assert len(asked) == 2 and asked[0] != asked[1]


def test_store_stands_in_tradingviews_last_and_keeps_its_error(monkeypatch: Any) -> None:
    import json as _json

    from newsterminal.http import FetchResult
    reply = _tv_reply()
    reply["data"][1]["d"][5:7] = [int(datetime(2026, 8, 20, 11, tzinfo=UTC).timestamp()), -1]
    good = FetchResult(True, _json.dumps(reply).encode(), "live", 0.0, None)
    results = [good, FetchResult(False, None, "unavailable", None, "HTTP 429")]
    monkeypatch.setattr(earnhist, "fetch", lambda url, **kw: results.pop(0))
    store = earnhist.EarnHistStore()
    now = datetime(2026, 11, 17, 14, tzinfo=UTC)
    # WMT has no 2.02 at all; AAPL's stop a year short of TradingView's last (Oklo's case).
    old = [{"date": "2025-03-24", "when": "after"}, {"date": "2024-11-14", "when": "after"}]
    st = store.tick(["WMT", "AAPL"], {"WMT": [], "AAPL": old}, now)
    assert store.view()["WMT"] == [{"date": "2026-08-20", "when": "pre"}]
    assert store.view()["AAPL"] == [{"date": "2026-10-21", "when": "after"}]
    assert st.notes[0] == "0 of 2 from EDGAR's 8-Ks, 2 from TradingView's last report"
    # A week's difference or less is the same report, and EDGAR's stays.
    close = [{"date": "2026-10-15", "when": "after"}, *old]
    store.tick(["WMT", "AAPL"], {"WMT": [], "AAPL": close}, now)
    assert store.view()["AAPL"] == close
    results.insert(0, good)                       # the list changes below: one more read
    st = store.tick(["WMT"], {"WMT": []}, now)
    # A failed read keeps the last good one and says why, on every tick until it heals.
    later = datetime.fromtimestamp(now.timestamp() + earnhist.NEXT_SEC + 1, UTC)
    st = store.tick(["WMT"], {"WMT": []}, later)
    assert st.ok and st.error == "TradingView: HTTP 429"
    st = store.tick(["WMT"], {"WMT": []}, later)
    assert st.error == "TradingView: HTTP 429" and results == []


# ------------------------------------------------------- the print's meaning


def test_read_of_is_the_economys_word() -> None:
    assert releases.read_of("CPI m/m", 0.1, 0.3) == "hot"
    assert releases.read_of("Initial Jobless Claims", 10.0, 220.0) == "cold"
    assert releases.read_of("Core CPI m/m", 0.0004, 0.3) == "inline"
    assert releases.read_of("CPI", None, 0.3) is None


def test_implication_per_book_by_theme() -> None:
    hot = releases.implication("hot", ["inflation"])
    assert hot is not None
    assert "headwind for the index" in hot["NQ"] and hot["NQ"] == hot["ES"]
    assert "real yields up" in hot["GC"]
    cold_jobs = releases.implication("cold", ["jobs"])
    assert cold_jobs is not None and "cuts come forward" in cold_jobs["GC"]
    inline = releases.implication("inline", ["growth"])
    assert inline is not None and inline["NQ"].startswith("In line")
    assert releases.implication("hot", ["rates"]) is None
    assert releases.implication(None, ["inflation"]) is None


# -------------------------------------------------------- the profile's words


def _asset(open_: float | None, last: float | None,
           shape: str = "D (balanced)") -> dict[str, Any]:
    return {"last": last, "rows": [
        {"key": "prev_rth", "vah": 110.0, "val": 100.0, "poc": 105.0, "shape": shape},
        {"key": "overnight", "vah": 108.0, "val": 103.0, "poc": 106.0, "shape": "D (balanced)"},
        {"key": "dev", "open": open_, "start_et": "18:00", "bars": 10,
         "shape": "P (accepted high)"},
    ]}


def test_profile_reads_carry_the_digest_facts_and_a_sentence() -> None:
    r = profile.reads(_asset(112.0, 113.0, "P (accepted high)"))
    assert r["developing_profile_open"]["vs_prev_rth_value"] == "above_value"
    assert r["price_now"]["vs_prev_rth_value"] == "above_value"
    assert r["price_now"]["vs_overnight_value"] == "above_value"
    assert r["text"] == ("Opened above prior value and trades above it: acceptance higher, trend "
                         "odds up. The prior POC 105 is the magnet. Prior RTH was a P: buyers "
                         "accepted the highs.")


def test_profile_reads_name_the_failed_break_and_the_rotation() -> None:
    back = profile.reads(_asset(98.0, 104.0))
    assert "back inside it" in back["text"] and "80% rule" in back["text"]
    rot = profile.reads(_asset(104.0, 106.0))
    assert rot["text"].startswith("Opened inside prior value and trades inside it: a rotation day.")
    assert profile.reads({"rows": [], "last": None}) == {"text": None}


def test_next_report_row_shape() -> None:
    from newsterminal.scanscore import next_report
    row = next_report({"date": "2026-11-03", "when": "after"}, date(2026, 10, 22))
    assert row == {"date": "2026-11-03", "when": "after", "days": 12, "eps_forecast": None,
                   "eps_actual": None, "surprise_pct": None}
    assert next_report({"date": "2026-10-01", "when": "pre"}, date(2026, 10, 22)) is None
    assert next_report(None, date(2026, 10, 22)) is None
