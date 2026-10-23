"""The driver board's new inputs, parsed and read: the CFTC rows, Cboe's daily
ratios, Yahoo's short interest, Nasdaq's report history — and the print read
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


def test_earnings_history_parse_orders_newest_first() -> None:
    doc = {"data": {"earningsSurpriseTable": {"rows": [
        {"fiscalQtrEnd": "Jun 2026", "dateReported": "8/4/2026", "eps": 1.44,
         "consensusForecast": "1.35", "percentageSurprise": "6.67"},
        {"fiscalQtrEnd": "Sep 2025", "dateReported": "11/4/2025", "eps": 0.97,
         "consensusForecast": "0.97", "percentageSurprise": "0"},
        {"fiscalQtrEnd": "Mar 2026", "dateReported": "5/5/2026", "eps": 1.11,
         "consensusForecast": "1.06", "percentageSurprise": "4.72"},
    ]}}}
    rows = earnhist.parse(doc)
    assert [r["date"] for r in rows] == ["2026-08-04", "2026-05-05", "2025-11-04"]
    assert rows[0]["eps"] == 1.44 and rows[0]["consensus"] == 1.35
    assert rows[0]["surprise_pct"] == 6.67
    assert earnhist.parse({}) == []


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


def test_next_report_parse_and_row_shape() -> None:
    doc = {"data": {"reportText": "Advanced Micro Devices, Inc. Common Stock is expected* to "
                                  "report earnings on  11/03/2026 after market close.  The report "
                                  "will be for the fiscal Quarter ending Sep 2026."}}
    assert earnhist.parse_next(doc) == {"date": "2026-11-03", "when": "after"}
    assert earnhist.parse_next({"data": {"reportText": "no date here"}}) is None
    from newsterminal.scanscore import next_report
    row = next_report({"date": "2026-11-03", "when": "after"}, date(2026, 10, 22))
    assert row == {"date": "2026-11-03", "when": "after", "days": 12, "eps_forecast": None,
                   "eps_actual": None, "surprise_pct": None}
    assert next_report({"date": "2026-10-01", "when": "pre"}, date(2026, 10, 22)) is None
    assert next_report(None, date(2026, 10, 22)) is None
