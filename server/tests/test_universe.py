"""
The wide read: what the screener's columns mean at each minute, and the tables.

The boundary table is the point of this file. The same column is yesterday's high
before 09:45 and today's after it, and a mistake there is a wrong PDH on every row.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from newsterminal.scan import ET
from newsterminal.sources import universe as u


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


@pytest.mark.parametrize(
    ("at", "want"),
    [
        # Monday 9 Nov 2026
        (et(2026, 11, 9, 3, 59), "last"),
        (et(2026, 11, 9, 4, 14), "last"),   # 04:00's pre-market reaches a 15-minute feed at 04:15
        (et(2026, 11, 9, 4, 15), "pre"),
        (et(2026, 11, 9, 9, 30), "pre"),    # the bell has rung; the delayed feed has not seen it
        (et(2026, 11, 9, 9, 44), "pre"),
        (et(2026, 11, 9, 9, 45), "rth"),
        (et(2026, 11, 9, 16, 0), "rth"),
        (et(2026, 11, 9, 16, 14), "rth"),
        (et(2026, 11, 9, 16, 15), "post"),
        (et(2026, 11, 9, 20, 14), "post"),
        (et(2026, 11, 9, 20, 15), "last"),
        # The weekend, and Thanksgiving
        (et(2026, 11, 8, 12, 0), "last"),
        (et(2026, 11, 26, 12, 0), "last"),
        # The half day after it: the close is 13:00, the late session ends 17:00
        (et(2026, 11, 27, 13, 14), "rth"),
        (et(2026, 11, 27, 13, 15), "post"),
        (et(2026, 11, 27, 17, 14), "post"),
        (et(2026, 11, 27, 17, 15), "last"),
    ],
)
def test_which_meaning_the_columns_have(at: datetime, want: str) -> None:
    assert u.basis_at(at) == want


@pytest.mark.parametrize(
    ("at", "want"),
    [(et(2026, 11, 8, 22, 34), date(2026, 11, 6)),   # Sunday night reads Friday
     (et(2026, 11, 9, 3, 0), date(2026, 11, 6)),     # so does Monday before the pre-market
     (et(2026, 11, 9, 7, 0), date(2026, 11, 9)),
     (et(2026, 11, 9, 21, 0), date(2026, 11, 9))],
)
def test_the_session_a_read_is_about(at: datetime, want: date) -> None:
    assert u.session_day(at) == want


def test_a_weekend_page_counts_its_news_back_from_the_session_it_shows() -> None:
    fri_close = et(2026, 11, 6, 20, 0).timestamp()
    assert u.news_anchor(et(2026, 11, 8, 22, 0)) == fri_close
    assert u.news_anchor(et(2026, 11, 9, 3, 0)) == fri_close
    # With a session on, it is now.
    on = et(2026, 11, 9, 10, 0)
    assert u.news_anchor(on) == on.timestamp()
    # The half day's late session ends at 17:00.
    assert u.news_anchor(et(2026, 11, 27, 18, 0)) == et(2026, 11, 27, 17, 0).timestamp()


def row(sym: str = "X", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sym": sym, "name": f"{sym} Inc", "exch": "NASDAQ", "close": 100.0, "chg": 1.0,
        "open": 99.0, "high": 101.0, "low": 98.0, "vol": 3e6, "gap": 0.5, "atr": 2.0,
        "pm_h": 99.5, "pm_l": 98.5, "pm_c": 99.2, "pm_chg": 0.4, "pm_vol": 2e5,
        "ah_c": 100.4, "ah_chg": 0.4, "ah_vol": 1e5, "avg": 1e6, "rv5": 2.5, "cap": 5e9,
        "float": 1e8, "sector": "XLK", "industry": "Semiconductors",
        "o1": 95.0, "h1": 97.0, "l1": 94.0, "c1": 96.0, "v1": 1e6,
        "h2": 96.0, "l2": 93.0, "c2": 95.0, "v2": 1e6,
    }
    base.update(kw)
    return base


READ = 1_794_000_000.0


def ev(r: dict[str, Any], basis: str, q: dict[str, Any] | None = None,
       pm_ok: bool = True, ah_ok: bool = True) -> dict[str, Any]:
    out = u.evaluate(r, basis, READ, pm_ok=pm_ok, ah_ok=ah_ok, q=q)
    assert out is not None
    return out


def test_a_finished_session_is_read_against_the_session_before_it() -> None:
    # IRTC's real Friday 6 Nov: close 90.22, PML 103.49, PDL 128.36.
    r = row("IRTC", close=90.22, chg=-30.7, gap=-15.24, high=112.0, low=88.0, vol=5.7e6,
            pm_h=120.0, pm_l=103.49, h1=135.0, l1=128.36, c1=130.2, avg=0.7e6)
    e = ev(r, "last")
    assert (e["pdh"], e["pdl"]) == (135.0, 128.36)
    assert (e["pm_state"], e["pd_state"], e["both"]) == ("below", "below", "down")
    assert e["last"] == 90.22 and e["rvol"] == pytest.approx(8.14, abs=0.01)
    assert not e["live"]


def test_before_the_open_the_base_bar_is_yesterday() -> None:
    e = ev(row(close=100.0, high=101.0, low=98.0, pm_c=103.0, pm_chg=3.0), "pre")
    # PDH is `high`, not `high[1]`; the price is the pre-market's; no time-of-day volume.
    assert (e["pdh"], e["pdl"], e["pdc"]) == (101.0, 98.0, 100.0)
    assert e["last"] == 103.0 and e["chg"] == 3.0 and e["gap"] == 3.0 and e["rvol"] is None
    # The pre-market range cannot be through itself: both ranges is the previous day alone.
    assert (e["pm_state"], e["pd_state"], e["both"]) == ("forming", "above", "up")


def test_after_the_open_the_base_bar_is_today() -> None:
    e = ev(row(close=102.0, pm_h=101.0), "rth")
    assert (e["pdh"], e["pdl"]) == (97.0, 94.0)
    assert (e["pm_state"], e["pd_state"], e["both"]) == ("above", "above", "up")
    assert e["rvol"] == 2.5  # the screener's own time-of-day figure


def test_one_range_is_not_both() -> None:
    e = ev(row(close=98.0, pm_h=99.5, pm_l=98.5), "rth")  # above PDH 97, under PML 98.5
    assert e["pd_state"] == "above" and e["pm_state"] == "below" and e["both"] is None


def test_a_name_with_no_pre_market_today_has_no_pm_range() -> None:
    e = ev(row(close=102.0), "rth", pm_ok=False)
    assert e["pmh"] is None and e["pm_state"] is None and e["both"] is None
    p = ev(row(), "pre", pm_ok=False)
    assert p["last"] == 100.0 and p["chg"] is None and p["vol"] is None


def test_the_stream_moves_the_read_when_it_is_newer() -> None:
    r = row(close=96.5, chg=0.52, pm_h=99.5, pm_l=95.0, h1=97.0, l1=94.0, c1=96.0)
    q = {"price": 100.0, "at": READ - 60, "session": "rth"}
    e = ev(r, "rth", q)
    assert e["last"] == 100.0 and e["live"] and e["chg"] == pytest.approx(4.17, abs=0.01)
    assert e["both"] == "up"
    # Older than the read's own fifteen-minute-old data: ignored.
    old = {"price": 100.0, "at": READ - 2000, "session": "rth"}
    assert not ev(r, "rth", old)["live"]
    # A closed market is never live, and an overnight print has no session.
    assert not ev(r, "last", q)["live"]
    assert not ev(r, "rth", {"overnight": {"price": 1.0, "at": READ}})["live"]


def test_after_hours_the_price_is_the_post_market_and_the_day_keeps_its_change() -> None:
    e = ev(row(close=100.0, chg=4.0, ah_c=103.0, ah_chg=3.0), "post")
    assert e["last"] == 103.0 and e["chg"] == 4.0 and e["ext"] == 3.0


def store_with(rows: list[dict[str, Any]]) -> u.UniverseStore:
    s = u.UniverseStore(path="nul")
    s.pm_ref, s.ah_ref = {}, {}
    s.rows, s.by_sym, s.read_at = rows, {r["sym"]: r for r in rows}, READ
    return s


SUN = et(2026, 11, 8, 22, 0)


def test_the_table_ranks_both_ranges_then_fresh_major_news_then_volume() -> None:
    up = {"close": 110.0, "high": 111.0, "pm_h": 105.0, "h1": 104.0}
    rows = [row("BIG", vol=9e6, **up), row("NEWS", vol=3e6, **up),
            row("IN", close=96.0, high=96.5, low=95.0, vol=9e6),
            row("SMALL", cap=1e9, vol=9e6, **up), row("THIN", vol=1e5, **up),
            row("COLD", vol=1e6, **up)]
    deal = {"major": True, "tag": "Deal", "tier": 1}
    ctx = u.Ctx(catalyst=lambda s: deal if s == "NEWS" else None,
                pinned=frozenset({"IN"}), stage={"BIG": 2})
    got = store_with(rows).breakouts(ctx, now=SUN)
    assert got["basis"] == "last" and got["scanned"] == 5     # SMALL is under the cap
    # COLD is 1x and THIN is under the volume floor; the rest pass.
    assert [r["sym"] for r in got["rows"]] == ["NEWS", "BIG"]
    assert got["chips"] == {"all": 3, "both": 2, "news": 1, "gaps": 0, "through": 2, "inside": 1,
                            "day23": 1, "pinned": 1}
    assert got["stats"]["up"] == 2 and got["stats"]["top_rvol"]["sym"] == "BIG"
    assert got["rows"][1]["stage"] == 2


def test_the_filters_narrow_it_and_a_theme_reads_the_industry() -> None:
    up = {"close": 110.0, "pm_h": 105.0, "h1": 104.0}
    rows = [row("CHIP", **up), row("BANK", industry="Regional Banks", sector=None, **up)]
    s = store_with(rows)
    assert [r["sym"] for r in s.breakouts(u.Ctx(), theme="KRE", now=SUN)["rows"]] == ["BANK"]
    assert [r["sym"] for r in s.breakouts(u.Ctx(), sector="XLK", now=SUN)["rows"]] == ["CHIP"]
    assert s.breakouts(u.Ctx(), theme="NOPE", now=SUN)["rows"] == []


@pytest.mark.parametrize(
    ("at", "want"),
    [(et(2026, 11, 8, 22, 0), date(2026, 11, 6)),    # Sunday night: Friday's cards
     (et(2026, 11, 9, 3, 0), date(2026, 11, 6)),
     (et(2026, 11, 9, 7, 0), date(2026, 11, 6)),     # the pre-market: still Friday's ETF moves
     (et(2026, 11, 9, 9, 29), date(2026, 11, 6)),
     # From the bell (2026-11-16): the funds' moves are live and today's, and until the
     # feed reaches the open at 09:45 the counts are the stocks' pre-market, today's too.
     (et(2026, 11, 9, 9, 30), date(2026, 11, 9)),
     (et(2026, 11, 9, 9, 44), date(2026, 11, 9)),
     (et(2026, 11, 9, 9, 45), date(2026, 11, 9)),
     (et(2026, 11, 9, 17, 0), date(2026, 11, 9)),
     (et(2026, 11, 9, 21, 0), date(2026, 11, 9))],
)
def test_the_session_a_card_is_about(at: datetime, want: date) -> None:
    assert u.cards_day(at) == want


def test_one_big_winner_cannot_carry_the_median() -> None:
    rows = [row("KRMN", chg=42.0), row("A", chg=-1.0), row("B", chg=-2.0), row("C", chg=0.0),
            row("D", chg=None)]
    got = u.span_stats(rows, "chg", leaders=2)
    assert (got["up"], got["down"], got["median"]) == (1, 2, -0.5)     # the average is +9.75
    assert [x["sym"] for x in got["leaders"]] == ["KRMN", "C"]
    assert u.span_stats([row("A", chg=None)], "chg") == {"up": 0, "down": 0, "median": None,
                                                         "leaders": []}


def test_a_fund_theme_reads_its_members_and_a_row_wears_every_theme_it_is_in() -> None:
    up = {"close": 110.0, "pm_h": 105.0, "h1": 104.0}
    s = store_with([row("NVDA", **up), row("CRWD", industry="Packaged Software", **up),
                    row("AMAT", industry="Electronic Production Equipment", **up)])
    s.members = {"BOTZ": frozenset({"NVDA"}), "ARKK": frozenset({"NVDA"}),
                 "CIBR": frozenset({"CRWD"})}
    assert [r["sym"] for r in s.breakouts(u.Ctx(), theme="CIBR", now=SUN)["rows"]] == ["CRWD"]
    assert {r["sym"]: r["themes"] for r in s.breakouts(u.Ctx(), now=SUN)["rows"]} == {
        "NVDA": ["SMH", "BOTZ", "ARKK"], "CRWD": ["IGV", "CIBR"], "AMAT": ["SMH"]}
    # A theme with no list yet is left out of the filter rather than offering nothing.
    keys = {t["key"] for t in s.theme_list()}
    assert {"SMH", "CIBR", "BOTZ", "ARKK"} <= keys and "SKYY" not in keys


@pytest.mark.parametrize(
    ("sym", "industry", "country", "want"),
    [("NVDA", "Semiconductors", "United States", "SMH"),
     ("FSLR", "Semiconductors", "United States", None),         # solar, filed as a chipmaker
     ("RUN", "Semiconductors", "United States", None),
     ("MSFT", "Packaged Software", "United States", "IGV"),
     ("META", "Internet Software/Services", "United States", None),   # not software
     ("FITB", "Regional Banks", "United States", "KRE"),
     ("BPOP", "Regional Banks", "Puerto Rico", "KRE"),
     ("KEY", "Major Banks", "United States", "KRE"),            # filed with the giants
     ("JPM", "Major Banks", "United States", None),             # one of the giants
     ("HSBC", "Major Banks", "United Kingdom", None),
     ("IBN", "Regional Banks", "India", None),                  # TradingView's group is global
     ("ZZZ", "Regional Banks", None, "KRE"),                    # unknown is not foreign
     ("EOG", "Integrated Oil", "United States", None),          # E&P is a written list now
     ("TLN", "Alternative Power Generation", "United States", None)],   # and Solar the fund's
)
def test_the_theme_an_industry_gives_a_name(sym: str, industry: str, country: str | None,
                                            want: str | None) -> None:
    assert u.industry_theme(row(sym, industry=industry, country=country)) == want


def test_a_name_its_theme_leaves_out_is_off_the_list_and_wears_no_tag() -> None:
    up = {"close": 110.0, "pm_h": 105.0, "h1": 104.0}
    s = store_with([row("FITB", industry="Regional Banks", country="United States", **up),
                    row("IBN", industry="Regional Banks", country="India", **up)])
    assert [r["sym"] for r in s.breakouts(u.Ctx(), theme="KRE", now=SUN)["rows"]] == ["FITB"]
    got = {r["sym"]: (r["theme"], r["themes"]) for r in s.breakouts(u.Ctx(), now=SUN)["rows"]}
    assert got == {"FITB": ("KRE", ["KRE"]), "IBN": (None, [])}


def test_a_stocks_tags_read_in_the_order_the_themes_run() -> None:
    s = store_with([row("MU"), row("MSFT", industry="Packaged Software")])
    s.members = {"QTUM": frozenset({"MU", "MSFT"}), "DRAM": frozenset({"MU"}),
                 "SKYY": frozenset({"MSFT"}), "CIBR": frozenset({"MSFT"})}
    assert s.themes_of(s.by_sym["MU"]) == ["SMH", "DRAM", "QTUM"]
    assert s.themes_of(s.by_sym["MSFT"]) == ["IGV", "CIBR", "SKYY", "QTUM"]


def test_each_theme_sits_where_the_screenshots_run_it() -> None:
    tech = [k for k, parent in u.THEME_PARENT.items() if parent == "XLK"]
    assert tech == ["SMH", "DRAM", "IGV", "CIBR", "SKYY", "QTUM", "BOTZ", "ARKK"]
    assert u.THEME_PARENT["WGMI"] == "XLF" and u.THEME_PARENT["TAN"] == "XLE"


def test_a_groups_list_filters_on_the_last_whole_session() -> None:
    r = row(vol=3e6, v1=1e6)
    assert [u.last_session_volume(r, b) for b in ("pre", "post", "last")] == [3e6, 3e6, 3e6]
    # From the open a 15-minute feed has almost none of today, so yesterday's stands...
    assert u.last_session_volume(row(vol=2e4, v1=1e6), "rth") == 1e6
    # ...until today passes it.
    assert u.last_session_volume(row(vol=4e6, v1=1e6), "rth") == 4e6


def test_before_the_open_a_group_lists_its_stocks_and_the_hunt_still_wants_volume() -> None:
    s = store_with([row("QUIET", pm_vol=2e3, vol=3e6), row("THIN", pm_vol=2e3, vol=1e5)])
    at = et(2026, 11, 9, 7, 0)
    assert s.breakouts(u.Ctx(), chip="all", rvol=0.0, now=at)["rows"] == []
    got = s.breakouts(u.Ctx(), chip="all", rvol=0.0, listing=True, now=at)["rows"]
    assert [r["sym"] for r in got] == ["QUIET"]
    assert got[0]["vol"] == 2e3                               # the column still says what it says


def test_an_industry_lists_its_own_and_the_stats_split_the_previous_days_range() -> None:
    rows = [row("HI", close=110.0, h1=104.0), row("LO", close=90.0, l1=94.0, h1=104.0),
            row("MID", close=100.0, h1=104.0, l1=94.0), row("BANK", industry="Regional Banks")]
    s = store_with(rows)
    got = s.breakouts(u.Ctx(), chip="all", rvol=0.0, industry="Semiconductors", now=SUN)
    assert {r["sym"] for r in got["rows"]} == {"HI", "LO", "MID"}
    assert (got["stats"]["pdh"], got["stats"]["pdl"]) == (1, 1)
    assert s.industry_name("regional banks") == "Regional Banks"
    assert s.industry_name("nope") is None


def etf(key: str, day: float) -> dict[str, Any]:
    return {"key": key, "label": key.title(), "last": 10.0, "day_pct": day, "week_pct": day * 2,
            "month_pct": day * 3, "rs_day": day - 0.31, "rs_week": 0.0, "rs_month": 0.0,
            "spark": [1.0, 2.0]}


def test_the_heat_map_joins_each_etf_to_what_its_stocks_did() -> None:
    semis = [row(f"S{i}", chg=float(i), w1=-1.0, m1=2.0) for i in range(1, 6)]
    small = row("TINY", cap=1e9, chg=50.0)
    bank = row("BANK", industry="Regional Banks", sector="XLF", chg=-2.0)
    s = store_with([*semis, small, bank, row("CRWD", industry="Packaged Software", chg=-1.0)])
    s.members = {"CIBR": frozenset({"CRWD"}), "DRAM": frozenset({"S1", "S2"})}
    got = s.heatmap([etf("SPY", 0.31), etf("RSP", 0.5), etf("XLK", 1.45), etf("XLF", -0.59),
                     etf("SMH", 3.6), etf("KRE", -0.15), etf("CIBR", 0.03), etf("DRAM", 6.16),
                     etf("KWEB", 0.48)], now=SUN)
    by = {c["key"]: c for c in got["cards"]}
    assert "SPY" not in by and "RSP" not in by and got["spy"]["day"] == 0.31
    assert got["cards_day"] == "2026-11-06"
    # The floor keeps the $1bn name out of the count.
    xlk = by["XLK"]
    assert (xlk["kind"], xlk["top"], xlk["parent"], xlk["list"]) == ("sector", True, None, "sector")
    assert (xlk["names"], xlk["day"]["up"], xlk["day"]["down"]) == (6, 5, 1)
    assert xlk["day"]["median"] == 2.5 and xlk["week"]["down"] == 5 and xlk["month"]["up"] == 5
    assert (by["KRE"]["kind"], by["KRE"]["top"], by["KRE"]["parent"]) == ("theme", True, "XLF")
    assert (by["SMH"]["top"], by["SMH"]["list"], by["SMH"]["names"]) == (False, "industry", 5)
    assert (by["CIBR"]["list"], by["CIBR"]["names"]) == ("fund", 1)
    assert (by["DRAM"]["list"], by["DRAM"]["names"], by["DRAM"]["parent"]) == ("hand", 2, "XLK")
    assert by["KWEB"]["parent"] is None and by["KWEB"]["names"] == 0
    assert "spark" not in xlk
    # Five names make a group; one or two do not.
    assert [g["key"] for g in got["industries"]] == ["Semiconductors"]
    assert got["industries"][0]["sector"] == "XLK" and got["industries"][0]["names"] == 5


def test_the_gappers_table_reads_the_last_session_when_none_is_on() -> None:
    rows = [row("UP", pm_chg=12.0, pm_c=110.0, pm_vol=5e5), row("DOWN", pm_chg=-8.0, pm_vol=2e5),
            row("THIN", pm_chg=30.0, pm_vol=1e4)]
    got = store_with(rows).extended(u.Ctx(), session="pre", now=SUN)
    assert not got["active"] and [r["sym"] for r in got["rows"]] == ["UP", "DOWN"]
    assert got["stats"]["up"]["sym"] == "UP" and got["reference"][0]["sym"] == "UP"
    assert got["chips"]["through"] == 2


def test_a_quiet_name_is_not_a_gapper_while_the_session_is_on() -> None:
    r = row("STALE", pm_chg=9.0, pm_vol=5e5)
    s = store_with([r, row("FRESH", pm_chg=4.0, pm_vol=5e5)])
    s.pm_ref = {"STALE": [r["pm_h"], r["pm_l"], r["pm_vol"], 99.0, 2.0]}
    got = s.extended(u.Ctx(), session="pre", now=et(2026, 11, 9, 8, 0))
    assert got["active"] and [x["sym"] for x in got["rows"]] == ["FRESH"]


def test_the_page_has_yesterdays_gappers_while_nothing_has_traded_yet() -> None:
    r = row("OLD", pm_chg=9.0, pm_vol=5e5)
    s = store_with([r])
    s.pm_ref = {"OLD": [r["pm_h"], r["pm_l"], r["pm_vol"], 99.0, 9.0]}
    got = s.extended(u.Ctx(), session="pre", now=et(2026, 11, 9, 4, 30))
    assert got["rows"] == [] and got["reference_is_last"]
    assert got["reference"][0]["sym"] == "OLD"


def test_a_gapper_carries_both_ranges_and_the_counts_the_page_leads_with() -> None:
    rows = [row("UP", pm_chg=12.0, pm_c=110.0, pm_vol=5e5, high=101.0, low=98.0),
            row("IN", pm_chg=-8.0, pm_c=99.0, pm_vol=2e5, high=96.5, low=94.5)]
    cat = {"title": "x", "tier": 1, "major": True}
    got = store_with(rows).extended(u.Ctx(catalyst=lambda s: cat if s == "UP" else None),
                                    session="pre", now=SUN)
    up = next(r for r in got["rows"] if r["sym"] == "UP")
    assert (up["pmh"], up["pml"], up["session"]) == (99.5, 98.5, "pre")
    inside = next(r for r in got["rows"] if r["sym"] == "IN")
    assert inside["inside"] and not up["inside"]
    assert got["stats"] | {"up": None, "down": None} == {
        "up": None, "down": None, "through": 2, "inside": 1, "gap_up": 1, "gap_up_news": 1,
        "gap_down": 1, "gap_down_news": 0}
    assert got["chips"]["inside"] == 1 and got["scanned"] == 2


def test_all_sessions_lists_a_name_that_moved_in_both_once_in_the_newer() -> None:
    rows = [row("BOTH", pm_chg=9.0, pm_vol=5e5, ah_chg=-4.0, ah_c=95.0, ah_vol=2e5),
            row("AH", pm_chg=0.1, pm_vol=5e5, ah_chg=6.0, ah_c=95.0, ah_vol=2e5)]
    s = store_with(rows)
    # Mid-session the morning's pre-market is newer than last night's after-hours.
    got = s.extended(u.Ctx(), session="all", now=et(2026, 11, 9, 11, 0))
    assert {(r["sym"], r["session"]) for r in got["rows"]} == {("BOTH", "pre"), ("AH", "post")}
    # On a Sunday night the Friday evening is the newer of the two.
    got = s.extended(u.Ctx(), session="all", now=SUN)
    assert {(r["sym"], r["session"]) for r in got["rows"]} == {("BOTH", "post"), ("AH", "post")}


def test_extended_volume_is_an_estimate_until_five_sessions_are_written_down() -> None:
    s = store_with([row("X", pm_chg=9.0, pm_vol=5e5, avg=1e6)])
    r = s.extended(u.Ctx(), session="pre", now=SUN)["rows"][0]
    assert (r["adv_pct"], r["rvol"], r["rvol_est"]) == (50.0, 10.0, True)
    s.pm_hist = {"X": [100_000] * 4}
    assert s.extended(u.Ctx(), session="pre", now=SUN)["rows"][0]["rvol_est"]
    s.pm_hist = {"X": [100_000] * 5}
    r = s.extended(u.Ctx(), session="pre", now=SUN)["rows"][0]
    assert (r["rvol"], r["rvol_est"]) == (5.0, False)


def test_each_evening_books_the_extended_volume_once_and_a_quiet_name_as_none() -> None:
    a, b = row("A", pm_vol=4e5, ah_vol=1e5), row("B", pm_vol=9e5, ah_vol=3e5)
    s = store_with([a, b])
    s.pm_ref = {"B": [b["pm_h"], b["pm_l"], b["pm_vol"], 1.0, 1.0]}   # B did not trade today
    s.ah_ref = {"B": [b["ah_c"], b["ah_vol"], 1.0]}
    s.pm_ref_day = "2026-11-06"
    s._book_volumes([a, b], "2026-11-09")
    s._book_volumes([a, b], "2026-11-09")
    assert s.pm_hist == {"A": [400_000], "B": [0]} and s.ah_hist == {"A": [100_000], "B": [0]}
    # A restart after tonight's first read: the reference is tonight's, and says nothing.
    s.pm_ref_day = "2026-11-10"
    s._book_volumes([b], "2026-11-10")
    assert s.pm_hist["B"] == [0, 900_000]
    # The first night after this shipped: the reference on file has no date.
    s.pm_ref_day, s.vol_day = None, None
    s._book_volumes([b], "2026-11-12")
    assert s.pm_hist["B"] == [0, 900_000, 900_000]
    s.pm_hist = {"A": list(range(30))}
    s._book_volumes([a], "2026-11-11")
    assert len(s.pm_hist["A"]) == u.VOL_KEEP and s.pm_hist["A"][-1] == 400_000


def test_search_is_exact_then_prefix_then_name_biggest_first() -> None:
    rows = [row("AP", name="Ampco", cap=4e8), row("APP", name="Applovin", cap=1e11),
            row("MSFT", name="Microsoft", cap=3e12), row("ZZ", name="Apple Hospitality", cap=3e9)]
    s = store_with(rows)
    assert [x["sym"] for x in s.search("ap")] == ["AP", "APP", "ZZ"]
    assert [x["sym"] for x in s.search("micro")] == ["MSFT"]
    assert s.search("  ") == []


def test_breadth_buckets_every_name_and_names_the_leaders() -> None:
    rows = [row("A", chg=12.0), row("B", chg=3.0), row("C", chg=-1.0), row("D", chg=-6.0),
            row("E", chg=0.0)]
    got = store_with(rows).breadth(SUN)
    assert got is not None
    assert (got["advancers"], got["decliners"], got["names"]) == (2, 2, 5)
    by = {b["label"]: b["n"] for b in got["buckets"]}
    assert by == {"≤-10": 0, "-10": 1, "-5": 0, "-2": 1, "+2": 0, "+5": 1, "+10": 0, "≥+10": 1}
    assert [x["sym"] for x in got["leaders"]["XLK"]["up"]] == ["A", "B"]
    assert [x["sym"] for x in got["leaders"]["XLK"]["down"]] == ["D", "C"]


def test_the_parser_keeps_common_lines_and_drs_and_reads_the_offsets() -> None:
    def item(sym: str, kind: str, specs: list[str]) -> dict[str, Any]:
        d: list[Any] = [None] * len(u.COLUMNS)
        d[u.COLUMNS.index("name")] = sym
        d[u.COLUMNS.index("type")] = kind
        d[u.COLUMNS.index("typespecs")] = specs
        d[u.COLUMNS.index("high[1]")] = 12.5
        d[u.COLUMNS.index("country")] = "Taiwan" if kind == "dr" else None
        return {"s": f"NYSE:{sym}", "d": d}

    rows, err = u.parse({"data": [item("AAA", "stock", ["common"]),
                                  item("PRF", "stock", ["preferred"]),
                                  item("TSM", "dr", [""]), {"d": [1, 2]}]})
    assert err is None and [r["sym"] for r in rows] == ["AAA", "TSM"]
    assert rows[0]["h1"] == 12.5 and rows[0]["exch"] == "NYSE"
    assert (rows[0]["country"], rows[1]["country"]) == (None, "Taiwan")


@pytest.mark.parametrize(
    ("sym", "industry", "want"),
    [("LRCX", "Electronic Production Equipment", "XLK"),   # not TradingView's manufacturing
     ("KRMN", "Aerospace & Defense", "XLI"),               # not its electronic technology
     ("WFC", "Major Banks", "XLF"), ("O", "Real Estate Investment Trusts", "XLRE"),
     ("GOOGL", "Internet Software/Services", "XLC"),       # the desk's table wins
     ("TRGP", "Gas Distributors", "XLE"),                  # moves gas, filed with the utilities
     ("ATO", "Gas Distributors", "XLU"),
     ("ZZZ", "Financial Conglomerates", None)],            # mixed: none rather than wrong
)
def test_a_names_sector_comes_from_its_industry(sym: str, industry: str, want: str | None) -> None:
    d: list[Any] = [None] * len(u.COLUMNS)
    d[u.COLUMNS.index("name")] = sym
    d[u.COLUMNS.index("type")] = "stock"
    d[u.COLUMNS.index("typespecs")] = ["common"]
    d[u.COLUMNS.index("industry")] = industry
    rows, _ = u.parse({"data": [{"s": f"NYSE:{sym}", "d": d}]})
    assert rows[0]["sector"] == want
    assert u.parse({"data": "x"})[1] == "no data array in the reply"


def test_the_wide_rows_carry_the_engines_verdict() -> None:
    rows = [row("UP", pm_chg=12.0, pm_c=110.0, pm_vol=5e5)]
    said = {"state": "inplay", "score": 6.1, "reason": "gap 1.4 ATR", "mark": None, "at": None}
    ctx = u.Ctx(verdict=lambda s: said if s == "UP" else None)
    got = store_with(rows).extended(ctx, session="pre", now=SUN)
    assert got["rows"][0]["verdict"] == said
    assert store_with(rows).extended(u.Ctx(), session="pre", now=SUN)["rows"][0]["verdict"] is None


def test_the_wide_reads_pre_market_stands_in_for_nasdaqs() -> None:
    mon = date(2026, 11, 9)
    s = store_with([row("UP", pm_vol=5e5, pm_h=110.0, pm_l=104.0, pm_c=109.0),
                    row("QUIET", pm_vol=2e5)])
    # QUIET has not traded this morning: its columns are still Friday's.
    s.pm_ref = {"QUIET": [99.5, 98.5, 2e5, 99.2, 0.4]}

    def got(at: datetime, sym: str = "UP", day: date = mon) -> float | None:
        r = s.premarket_of(sym, day, at)
        return r["volume"] if r else None

    rows = [(at.strftime("%a %H:%M"), got(at)) for at in (
        et(2026, 11, 9, 4, 14), et(2026, 11, 9, 4, 15), et(2026, 11, 9, 9, 29),
        et(2026, 11, 9, 12, 0), et(2026, 11, 9, 19, 59), et(2026, 11, 9, 20, 15),
        et(2026, 11, 8, 12, 0))]
    # when it is asked → the pre-market volume it answers for Monday's row
    assert rows == [("Mon 04:14", None), ("Mon 04:15", 5e5), ("Mon 09:29", 5e5),
                    ("Mon 12:00", 5e5), ("Mon 19:59", 5e5), ("Mon 20:15", None),
                    ("Sun 12:00", None)]
    # 20:00 to 20:15 ET the scanner's day is Tuesday and the screener's is still Monday.
    assert got(et(2026, 11, 9, 20, 5), day=date(2026, 11, 10)) is None
    assert got(et(2026, 11, 9, 8, 0), "QUIET") is None
    full = s.premarket_of("UP", mon, et(2026, 11, 9, 8, 0))
    assert full is not None and full["source"] == "screener"
    assert (full["high"], full["low"], full["last"]) == (110.0, 104.0, 109.0)
