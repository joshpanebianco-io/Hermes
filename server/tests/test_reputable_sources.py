"""The most reputable and the most official source for each thing (owner, 2026-11-15:
"so we are getting the news and macro and everything form the most reputable sources as
possible and most official").

Three things are held here. The wire: three feeds went and the statistical agencies'
own release feeds came, each cut to the releases this desk reads. The per-stock news:
a site that reports nothing of its own is nobody's source. And the calendar: a US
release carries the agency's own figure, joined only when it is that print's and not
the last one's, filling a row the feed has not filled and correcting one it got wrong.

The payloads are the agencies' real ones, cut down, as they stood on 14 Nov 2026.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from newsterminal import catalysts
from newsterminal.sources import official, wire

# ------------------------------------------------------------------ the wire


def test_the_three_feeds_are_gone_and_the_agencies_are_on() -> None:
    names = {(pub, section) for _, _, pub, section, _ in wire.FEEDS}
    pubs = {pub for pub, _ in names}
    assert not pubs & {"ZeroHedge", "Investing.com", "Yahoo Finance"}
    assert {("BEA", "Releases"), ("Census Bureau", "Indicators"), ("EIA", "Press"),
            ("Bank of Japan", "Policy")} <= names
    assert ("ZeroHedge", "Markets") not in wire.GENERAL_FEEDS


@pytest.mark.parametrize(("publisher", "title", "kept"), [
    ("BEA", "GDP (Advance Estimate), 3rd Quarter 2026", True),
    ("BEA", "Gross Domestic Product (Second Estimate), 3rd Quarter 2026", True),
    ("BEA", "Personal Income and Outlays, September 2026", True),
    ("BEA", "U.S. International Trade in Goods and Services, September 2026", True),
    ("BEA", "Gross Domestic Product by County and Personal Income by County", False),
    ("BEA", "Outdoor Recreation Economic Statistics", False),
    ("Census Bureau", "Advance Monthly Sales for Retail and Food Services", True),
    ("Census Bureau", "New Residential Construction", True),
    ("Census Bureau", "Rental Vacancy Rate", False),
    ("Census Bureau", "Business Formation Statistics", False),
    ("Bank of Japan", "Statement on Monetary Policy", True),
    ("Bank of Japan", "Summary of Opinions at the Monetary Policy Meeting on October 29 and 30, "
                      "2026", True),
    ("Bank of Japan", "Speech by Board Member ASADA in Nagasaki (Economic Activity, Prices, and "
                      "Monetary Policy in Japan)", True),
    ("Bank of Japan", "Bank of Japan Accounts (November 10)", False),
    ("Bank of Japan", "Japanese Government Bonds Held by the Bank of Japan", False),
])
def test_an_agencys_feed_is_cut_to_the_releases_this_desk_reads(publisher: str, title: str,
                                                                kept: bool) -> None:
    why = wire.off_tape(title, publisher, "Releases")
    assert (why is None) is kept, why


def test_a_release_lands_on_the_tape_with_the_agencys_sentence() -> None:
    xml = """<rss><channel><item name="GDP">
      <title>GDP (Advance Estimate), 3rd Quarter 2026</title>
      <link>https://www.bea.gov/news/2026/gdp-advance-estimate-3rd-quarter-2026</link>
      <description><![CDATA[<p>Real gross domestic product (GDP) increased at an annual rate of
      3.4 percent in the third quarter of 2026.</p>]]></description>
      <pubDate>Thu, 29 Oct 2026 08:30:00 EDT</pubDate></item>
      <item name="Outdoor Recreation"><title>Outdoor Recreation Economic Statistics</title>
      <link>https://www.bea.gov/x</link><pubDate>Thu, 05 Mar 2026 10:00:00 EST</pubDate></item>
      </channel></rss>"""
    got = wire.parse_feed(xml, "BEA", "Releases", "macro", region="us")
    assert [g["title"] for g in got] == ["GDP (Advance Estimate), 3rd Quarter 2026"]
    assert got[0]["publisher"] == "BEA" and "annual rate of 3.4 percent" in got[0]["summary"]
    assert got[0]["url"].startswith("https://www.bea.gov/")


@pytest.mark.parametrize("outlet", ["Yahoo Finance", "Yahoo Finance UK", "Investing.com", "Forbes",
                                    "Benzinga", "TheStreet", "Business Insider", "TradingView"])
def test_a_search_result_from_these_is_no_longer_taken(outlet: str) -> None:
    assert not wire.is_newsroom(outlet)
    assert wire.off_tape("Oil falls below $90 as Trump pulls back from threat to strike Iran",
                         "Google News", "Energy", outlet) == "not a newsroom"


# ------------------------------------------------------------------ the per-stock news


@pytest.mark.parametrize("publisher", ["Zacks", "Stocktwits", "GuruFocus", "MarketBeat",
                                       "Stock Story", "Invezz", "Motley Fool", "Insider Monkey"])
def test_a_site_that_reports_nothing_of_its_own_is_nobodys_source(publisher: str) -> None:
    t = "Take-Two Q2 Earnings Beat on Lower Costs Despite Bookings Miss"
    assert catalysts.story(t, "TTWO", ["Take-Two"], "Reuters") is not None
    assert catalysts.story(t, "TTWO", ["Take-Two"], publisher) is None
    # The newswires, the company's own release and the desks that file first stay.
    for kept in ("Dow Jones Newswires", "GlobeNewswire", "Seeking Alpha", "Benzinga"):
        assert catalysts.story(t, "TTWO", ["Take-Two"], kept) is not None, kept


# ------------------------------------------------------------------ the agencies' figures

BLS = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
    {"seriesID": "WPSFD4", "data": [
        {"year": "2026", "period": "M10", "value": "160.254"},
        {"year": "2026", "period": "M09", "value": "159.699"},
        {"year": "2026", "period": "M13", "value": "158.000"}]},
    {"seriesID": "WPUFD4", "data": [
        {"year": "2026", "period": "M10", "value": "160.248"},
        {"year": "2025", "period": "M10", "value": "150.468"}]},
    {"seriesID": "CES0000000001", "data": [
        {"year": "2026", "period": "M10", "value": "159293"},
        {"year": "2026", "period": "M09", "value": "159128"}]},
    {"seriesID": "LNS14000000", "data": [{"year": "2026", "period": "M10", "value": "4.1"}]},
    {"seriesID": "JTS000000000000000JOL", "data": [
        {"year": "2026", "period": "M09", "value": "7523"}]},
    # No October 2025 to measure the year from: the figure is left out, not guessed.
    {"seriesID": "CUUR0000SA0", "data": [
        {"year": "2026", "period": "M10", "value": "337.511"},
        {"year": "2026", "period": "M09", "value": "336.900"}]},
    {"seriesID": "NOT_OURS", "data": [{"year": "2026", "period": "M10", "value": "1"}]},
]}}

CENSUS = """<rss><channel>
<item><title>Advance Monthly Sales for Retail and Food Services</title>
 <link>https://www.census.gov/retail/index.html</link>
 <description><![CDATA[U.S. retail and food services sales for September 2026 were $745.0 billion,
 up 0.8 percent (+/-0.4 percent) from the previous month.<p><br>September 2026: +0.8 % Change<br>
 August 2026 (r): +1.3 % Change<br></p>]]></description>
 <guid isPermaLink="false">retail_sales</guid>
 <pubDate>Thu, 15 Oct 2026 08:30:00 -0400</pubDate></item>
<item><title>New Residential Construction</title><link>https://www.census.gov/construction/nrc/</link>
 <description><![CDATA[Privately-owned housing starts in September 2026 were at a seasonally
 adjusted annual rate of 1,221,000. This is 5.2 percent (+/- 11.8%)* below the revised August 2026
 estimate of 1,288,000.<p><br>September 2026: -5.2* % Change<br>August 2026 (r): -5.9* % Change<br>
 </p>]]></description>
 <guid isPermaLink="false">housing_starts</guid>
 <pubDate>Tue, 20 Oct 2026 08:30:00 -0400</pubDate></item>
<item><title>Advance U.S. International Trade in Goods</title><link>https://www.census.gov/x</link>
 <description><![CDATA[The advance international trade deficit in goods increased to $134.9 billion
 in September from $132.1 billion in August as imports increased more than exports.<p><br>
 September 2026: 2.1° % Change<br></p>]]></description>
 <guid isPermaLink="false">adv_intl_trade</guid>
 <pubDate>Wed, 28 Oct 2026 08:30:00 -0400</pubDate></item>
<item><title>Rental Vacancy Rate</title><guid isPermaLink="false">rental_vacancy</guid>
 <description>x</description><pubDate>Wed, 28 Oct 2026 10:00:00 -0400</pubDate></item>
</channel></rss>"""

BEA = """<rss><channel>
<item name="U.S. International Trade in Goods and Services">
 <link>https://www.bea.gov/news/2026/trade</link>
 <data><main><current><infoDate>September 2026</infoDate>
 <percentChange>-$105.0 billion</percentChange></current></main></data>
 <pubDate>Wed, 04 Nov 2026 08:30:00 EST</pubDate></item>
<item name="GDP"><link>https://www.bea.gov/news/2026/gdp</link>
 <data><main><current><infoDate>Q3 2026</infoDate><percentChange>+3.4</percentChange></current>
 <previous><infoDate>Q2 2026</infoDate><percentChange>+2.2</percentChange></previous></main></data>
 <pubDate>Thu, 29 Oct 2026 08:30:00 EDT</pubDate></item>
<item name="Personal Income and Outlays"><link>https://www.bea.gov/news/2026/pio</link>
 <data><main><current><infoDate>September 2026</infoDate><percentChange>+0.2</percentChange>
 </current></main>
 <supplemental name="Personal Consumption Expenditures"><current><percentChange>0.5</percentChange>
 <rateChange>113.1</rateChange></current></supplemental></data>
 <pubDate>Thu, 29 Oct 2026 08:30:00 EDT</pubDate></item>
<item name="Personal Income and Outlays"><link>https://www.bea.gov/news/2026/pio-jul</link>
 <data><main><current><infoDate>July 2026</infoDate><percentChange>May 2026 +0.7%</percentChange>
 </current></main></data><pubDate>Wed, 26 Aug 2026 08:30:00 EDT</pubDate></item>
<item name="Gross Domestic Product by County and Personal Income by County">
 <data><main><current><infoDate>2024</infoDate><percentChange>+9.9</percentChange></current></main>
 </data><pubDate>Thu, 05 Feb 2026 08:30:00 EST</pubDate></item>
</channel></rss>"""

OIL = '''"STUB_1","11/6/26","10/30/26","Difference","Percent Change","11/7/25","Difference"
"Crude Oil","693.952","691.944","2.008","0.300","837.974","-144.022","-17.200"
"Commercial (Excluding SPR)","414.417","409.760","4.657","1.100","427.581","-13.164","-3.100"
"Total Motor Gasoline","210.757","208.958","1.799","0.900","205.064","5.693","2.800"
"Distillate Fuel Oil","103.330","99.259","4.071","4.100","110.909","-7.579","-6.800"
'''

GAS = {"release_date": "2026-Nov-13 00:00:00", "current_week": "2026-11-06", "series": [
    {"name": "east region", "calculated": {"net_change": 12}},
    {"name": "total lower 48 states", "calculated": {"net_change": 61}}]}


def _figures() -> dict[str, dict[str, Any]]:
    return {**official.bls_figures(BLS), **official.census_figures(CENSUS),
            **official.bea_figures(BEA), **official.eia_oil_figures(OIL),
            **official.eia_gas_figures(GAS)}


def test_the_bls_figures_are_worked_from_its_own_series() -> None:
    f = official.bls_figures(BLS)
    # 160.254 over 159.699 is 0.35 per cent: 0.3 to one place, as the release printed it.
    assert (f["ppi_mm"]["text"], f["ppi_mm"]["ref"], f["ppi_mm"]["period"]) == (
        "0.3%", [2026, 10], "October 2026")
    assert f["ppi_yy"]["text"] == "6.5%"
    assert (f["payrolls"]["text"], f["payrolls"]["value"]) == ("165K", 165000.0)
    assert f["unemployment"]["text"] == "4.1%"
    assert (f["jolts"]["text"], f["jolts"]["lag"]) == ("7.523M", 2)
    assert "cpi_yy" not in f and "cpi_mm" not in f  # nothing to measure them from here
    assert all(v["by"] == "BLS" for v in f.values())


def test_a_bls_refusal_is_not_an_answer() -> None:
    assert official._bls_ok(json.dumps(BLS).encode()) is None
    refused = {"status": "REQUEST_NOT_PROCESSED",
               "message": ["daily threshold for total number of requests allocated"]}
    assert "REQUEST_NOT_PROCESSED" in (official._bls_ok(json.dumps(refused).encode()) or "")
    assert official._bls_ok(b"<html>Access denied</html>") is not None


def test_the_census_bea_and_eia_figures_are_read_as_published() -> None:
    f = _figures()
    assert (f["retail_mm"]["text"], f["retail_mm"]["published"]) == ("0.8%", "2026-10-15")
    assert (f["starts"]["text"], f["starts"]["value"]) == ("1.221M", 1221000.0)
    assert f["starts_mm"]["text"] == "-5.2%"
    assert (f["goods_trade"]["text"], f["goods_trade"]["value"]) == ("-$134.9B", -134.9e9)
    assert (f["gdp"]["text"], f["gdp"]["period"], f["gdp"]["published"]) == (
        "3.4%", "Q3 2026", "2026-10-29")
    # The newest Personal Income release, not July's under it.
    assert (f["income_mm"]["text"], f["income_mm"]["period"]) == ("0.2%", "September 2026")
    assert f["spending_mm"]["text"] == "0.5%"
    assert (f["trade"]["text"], f["trade"]["value"]) == ("-$105.0B", -105.0e9)
    assert (f["crude"]["text"], f["crude"]["week_end"]) == ("4.657M", "2026-11-06")
    assert f["gasoline"]["text"] == "1.799M" and f["distillate"]["text"] == "4.071M"
    gas = f["gas_storage"]
    assert (gas["text"], gas["published"], gas["period"]) == (
        "61B", "2026-11-13", "week ending 6 Nov")
    assert official._bea_number("May 2026 +0.7%") == 0.7


@pytest.mark.parametrize(("event", "key"), [
    ("CPI m/m", "cpi_mm"), ("Core CPI m/m", "cpi_core_mm"), ("Core CPI y/y", "cpi_core_yy"),
    ("PPI ex. Food/Energy/Transport m/m", "ppi_xfet_mm"), ("Nonfarm Payrolls", "payrolls"),
    ("Private Nonfarm Payrolls", "payrolls_private"), ("Unemployment Rate", "unemployment"),
    ("Retail Sales m/m", "retail_mm"), ("Housing Starts", "starts"),
    ("Housing Starts m/m", "starts_mm"), ("GDP q/q", "gdp"), ("Trade Balance", "trade"),
    ("Crude Oil Inventories", "crude"), ("Natural Gas Storage", "gas_storage"),
    # Near names that are other series: the agency's figure must not land on them.
    ("CPI Index", None), ("GDP Price Index q/q", None), ("Retail Sales Ex Autos m/m", None),
    ("Retail Sales y/y", None), ("U6 Unemployment Rate", None), ("Core PCE Price Index m/m", None),
    ("API Weekly Crude Oil Stock", None), ("Initial Jobless Claims", None),
    ("Building Permits", None), ("FOMC Member Barr Speaks", None),
])
def test_a_figure_joins_only_the_release_it_is_the_print_of(event: str, key: str | None) -> None:
    assert official.key_of(event) == key


def test_this_months_figure_never_last_months() -> None:
    f = _figures()
    # The October PPI lands in November; in December the same figure is last month's.
    assert official.fits(f["ppi_mm"], date(2026, 11, 13))
    assert not official.fits(f["ppi_mm"], date(2026, 12, 11))
    assert not official.fits(f["ppi_mm"], date(2026, 10, 15))
    # Job openings report two months back.
    assert official.fits(f["jolts"], date(2026, 11, 3)) and not official.fits(
        f["jolts"], date(2026, 12, 1))
    # A release feed's figure belongs to the day the agency published it.
    assert official.fits(f["retail_mm"], date(2026, 10, 15))
    assert not official.fits(f["retail_mm"], date(2026, 11, 17))
    # The oil table's week ended three to eight days before its release.
    assert official.fits(f["crude"], date(2026, 11, 12))
    assert not official.fits(f["crude"], date(2026, 11, 18))
    assert not official.fits(f["crude"], date(2026, 11, 6))


def _row(event: str, day: str, actual: str | None, cons: str | None = None,
         prev: str | None = None, country: str = "United States") -> dict[str, Any]:
    def num(raw: str | None) -> float | None:
        st = official._style(raw)
        return st[0] if st else None

    a, c = num(actual), num(cons)
    return {"event": event, "country": country, "date": day, "et": "08:30", "ts": 1.0,
            "themes": ["inflation"], "actual": a, "actual_raw": actual, "consensus": c,
            "consensus_raw": cons, "previous": num(prev), "previous_raw": prev,
            "surprise": a - c if a is not None and c is not None else None,
            "released": a is not None, "read": None, "meaning": None, "score": 5}


def test_a_figure_the_feed_agrees_with_is_marked_and_the_row_left_alone() -> None:
    rows = [_row("PPI m/m", "2026-11-13", "0.3%", "0.4%", "1.4%"),
            _row("Natural Gas Storage", "2026-11-13", "61B", None, "77B"),
            _row("PPI m/m", "2026-11-13", "0.3%", country="Canada")]
    out = official.apply(rows, _figures(), now=10.0)
    assert out[0]["official"] == {"by": "BLS", "text": "0.3%", "period": "October 2026",
                                  "url": official.BLS_PAGE["ppi"], "agrees": True, "feed": None}
    assert (out[0]["actual"], out[0]["surprise"]) == (rows[0]["actual"], rows[0]["surprise"])
    assert out[1]["official"]["by"] == "EIA" and out[1]["official"]["agrees"] is True
    assert "official" not in out[2] and out[2] is rows[2]  # another country's PPI
    assert "official" not in rows[0]  # a new row, not the one passed in


def test_the_agencys_figure_fills_a_row_the_feed_has_not_filled() -> None:
    rows = [_row("PPI m/m", "2026-11-13", None, "0.4%", "1.4%"),
            _row("Housing Starts", "2026-10-20", None, "1.268M", "1.288M"),
            _row("Nonfarm Payrolls", "2026-11-06", None, "120K", "60K"),
            _row("Trade Balance", "2026-11-04", None, "-104B", "-105.7B")]
    out = official.apply(rows, _figures(), now=10.0)
    ppi, starts, jobs, trade = out
    assert (ppi["actual"], ppi["actual_raw"], ppi["released"]) == (0.3, "0.3%", True)
    assert ppi["surprise"] == pytest.approx(-0.1) and ppi["read"] is not None
    assert ppi["official"]["agrees"] is None
    # In the units the row's own figures are in, so the surprise is like for like.
    assert (starts["actual"], starts["actual_raw"]) == (1.221, "1.221M")
    assert (jobs["actual"], jobs["actual_raw"]) == (165.0, "165K")
    assert jobs["surprise"] == pytest.approx(45.0)
    assert (trade["actual"], trade["actual_raw"]) == (-105.0, "-105B")


def test_a_feed_that_disagrees_is_corrected_and_what_it_said_is_kept() -> None:
    rows = [_row("PPI m/m", "2026-11-13", "0.4%", "0.4%", "1.4%"),
            _row("Crude Oil Inventories", "2026-11-12", "4.7M", "1.2M", "8.9M")]
    out = official.apply(rows, _figures(), now=10.0)
    assert out[0]["official"]["agrees"] is False and out[0]["official"]["feed"] == "0.4%"
    assert (out[0]["actual"], out[0]["actual_raw"]) == (0.3, "0.3%")
    assert out[0]["surprise"] == pytest.approx(-0.1)
    # 4.7M is 4.657M to the feed's one place: the same figure, not a disagreement.
    assert out[1]["official"]["agrees"] is True and out[1]["actual_raw"] == "4.7M"


def test_a_figure_does_not_join_a_row_it_cannot_be_the_print_of() -> None:
    f = _figures()
    rows = [
        _row("Retail Sales m/m", "2026-11-17", None, "0.2%", "0.8%"),   # next month's print
        _row("Housing Starts", "2026-10-20", None, "-2.0%", "-5.9%"),   # a change, not a level
        {**_row("PPI m/m", "2026-11-13", None, "0.4%"), "ts": 9e12},    # not due yet
    ]
    out = official.apply(rows, f, now=10.0)
    assert all("official" not in r for r in out) and out == rows
    assert official.apply(rows, {}, now=10.0) is rows


def test_an_agency_is_asked_often_only_while_its_release_is_due() -> None:
    f = _figures()
    now = 1_000_000.0
    due_row = {**_row("Retail Sales m/m", "2026-11-17", None, "0.2%"), "ts": now - 120}
    assert official.due([due_row], f, now) == {"Census"}
    # Its figure in, it is no longer due; nor is a release an hour old, nor one to come.
    assert official.due([{**due_row, "date": "2026-10-15"}], f, now) == set()
    assert official.due([{**due_row, "ts": now - 3600}], f, now) == set()
    assert official.due([{**due_row, "ts": now + 600}], f, now) == set()
    assert official.due([{**due_row, "event": "ISM Manufacturing PMI"}], f, now) == set()


# ------------------------------------------------------------------ two phrasings


@pytest.mark.parametrize("title", [
    "US economy adds 165,000 jobs in October, blowing past expectations",
    "US employers added 165,000 jobs in October, more than forecast",
    "Hiring surged in October as employers added 165,000 jobs",
])
def test_a_jobs_print_written_as_a_count_is_a_print(title: str) -> None:
    """Measured 2026-11-15: the macro words were the release's own (payrolls, jobs
    report, unemployment), and a print written as what it says was dropped whoever
    filed it."""
    assert wire.off_tape(title, "CNBC", "Top") is None
    assert "macro" in wire.market_hooks(title)
    assert wire.classify("markets", title) == "macro" and wire.impact_of(title) == "high"


def test_a_companys_hiring_and_a_plants_are_not_the_jobs_print() -> None:
    amazon = "Amazon adds 100,000 jobs for the holiday season"
    assert wire.impact_of(amazon) != "high"  # hiring, not data
    for local in ("Ohio battery plant adds 300 jobs",
                  "UK to expand jobs guarantee scheme for young people"):
        assert wire.off_tape(local, "CNBC", "Top") == "names nothing a market trades on"


@pytest.mark.parametrize("title", [
    "DoorDash strikes $17B deal for rival Instacart",
    "DoorDash to buy Instacart for $17 billion",
    "DoorDash agrees to acquire Instacart in $17 billion deal",
    "Nelson Peltz-led group offers to buy Wendy's for $1.4B",
    "Digital Realty Trust to spend $10bn more on Japan data centers: CEO",
])
def test_a_deal_in_billions_stays_however_it_is_worded(title: str) -> None:
    assert wire.off_tape(title, "WSJ", "Business") is None
    assert "company" in wire.market_hooks(title)


@pytest.mark.parametrize("title", [
    "Billionaire buys $90 million mansion",
    "Hungary recovers $20 million cash in probe of Orban minister",
])
def test_millions_are_still_not_an_event_the_size_of_an_index(title: str) -> None:
    assert wire.off_tape(title, "WSJ", "Business") == "names nothing a market trades on"


def test_a_blank_cheque_companys_name_is_not_a_deal() -> None:
    spac = "Sizzle Acquisition Corp. II 3Q 2026: Net income $1.37M — 10-Q Summary"
    assert catalysts.grade(spac).tag != "Deal"
    for real in ("MaxCyte to Acquire Akron BioProducts for $125 Million in Cash",
                 "Pfizer completes acquisition of Metsera",
                 "Chevron Acquisition of Hess Clears Final Hurdle"):
        assert catalysts.grade(real) == ("Deal", catalysts.MAJOR), real
