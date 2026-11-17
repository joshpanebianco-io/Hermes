"""Stock news from sources that name themselves (owner, 2026-11-15: "i just want to make
sure we have quality sources for the stock related news ... the ones that we use to
determine if a stock is likely to trend", then "do what you recommend").

Yahoo's per-ticker RSS named no author: four stories in five read "Yahoo Finance"
whoever wrote them, and those were a quarter of what scored. Its search answer names
the outlet on every story, so the rows are read from that, the set-aside list reaches
them, and what scores under a name is a newswire's, a newsroom's or the company's own.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from newsterminal import catalysts
from newsterminal.http import FetchResult
from newsterminal.sources import scanner as scan_src
from newsterminal.sources import wire

SEARCH = {"news": [
    {"title": "Micron raises its quarterly revenue outlook on AI memory demand",
     "publisher": "Barrons.com", "link": "https://finance.yahoo.com/m/abc/micron-raises.html",
     "providerPublishTime": 1794700000, "type": "STORY", "relatedTickers": ["MU"]},
    {"title": "Micron Technology (MU) Has More Than 75% Of 2027 Output Committed",
     "publisher": "Simply Wall St.", "link": "https://finance.yahoo.com/news/micron-75.html",
     "providerPublishTime": 1794690000, "type": "STORY", "relatedTickers": ["MU", "CRWV"]},
    {"title": "Micron CEO on the memory cycle", "publisher": "Yahoo Finance Video",
     "link": "https://finance.yahoo.com/video/micron-ceo.html", "type": "VIDEO",
     "relatedTickers": ["MU"]},
    # A list: filed under four tickers.
    {"title": "A $2.8 Billion Fund Dumps These 3 Stocks", "publisher": "TIKR",
     "link": "https://www.tikr.com/blog/fund-dumps", "type": "STORY",
     "relatedTickers": ["SNDK", "AMZN", "NVDA", "MU"]},
    # Another company's, filed where a search for the ticker finds it.
    {"title": "StoneCo Ltd. (STNE) Q3 Earnings Lag Estimates", "publisher": "Zacks",
     "link": "https://finance.yahoo.com/news/stoneco.html", "type": "STORY",
     "relatedTickers": ["STNE"]},
    {"title": "Micron Announces Record Fiscal First Quarter Results",
     "publisher": "GlobeNewswire", "link": "https://www.globenewswire.com/x/micron-results",
     "providerPublishTime": 1794680000, "type": "STORY"},
    {"title": "", "publisher": "Reuters", "link": "https://x"},
]}


def test_yahoos_search_answer_names_the_outlet_behind_each_story() -> None:
    rows = scan_src.parse_search(SEARCH, "MU")
    assert [(r["publisher"], r["title"][:24]) for r in rows] == [
        ("Barron's", "Micron raises its quarte"),
        ("Simply Wall St", "Micron Technology (MU) H"),
        ("GlobeNewswire", "Micron Announces Record "),   # no tickers given: left to the test below
    ]
    assert rows[0]["ts"] == 1794700000 and rows[0]["utc"].startswith("2026-11-1")
    assert rows[2]["url"] == "https://www.globenewswire.com/x/micron-results"
    assert scan_src.parse_search(None, "MU") == []
    assert scan_src.parse_search({"news": "x"}, "MU") == []


def test_the_rss_still_supplies_the_sentence_under_a_headline() -> None:
    named = scan_src.parse_search(SEARCH, "MU")
    rss = [{"title": "Something else", "summary": "Micron lifted its outlook.",
            "url": "https://finance.yahoo.com/m/abc/micron-raises.html?.tsrc=rss"},
           {"title": "Micron Announces Record Fiscal First Quarter Results", "url": "https://other",
            "summary": "Revenue was a record."}]
    out = scan_src.with_summaries(named, rss)
    assert out[0]["summary"] == "Micron lifted its outlook."      # by its address
    assert "summary" not in out[1]
    assert out[2]["summary"] == "Revenue was a record."           # by its headline
    assert out[0]["publisher"] == "Barron's" and "summary" not in named[0]


@pytest.mark.parametrize("publisher", [
    "The Motley Fool", "Motley Fool", "GuruFocus.com", "24/7 Wall St.", "Simply Wall St.",
    "Zacks", "Insider Monkey", "TIKR", "Trefis", "TipRanks", "TheStreet", "Investing.com",
    "Stocktwits", "MarketBeat", "Kiplinger"])
def test_a_second_hand_site_is_set_aside_however_yahoo_spells_it(publisher: str) -> None:
    t = "Micron raises its quarterly revenue outlook on AI memory demand"
    assert catalysts.story(t, "MU", ["Micron"], publisher) is None, publisher


@pytest.mark.parametrize("publisher", [
    "Barron's", "Barrons.com", "MT Newswires", "BusinessWire", "Business Wire", "GlobeNewswire",
    "Reuters", "Dow Jones Newswires", "Yahoo Finance", "Benzinga", "Seeking Alpha"])
def test_a_source_that_reports_still_scores(publisher: str) -> None:
    t = "Micron raises its quarterly revenue outlook on AI memory demand"
    g = catalysts.story(t, "MU", ["Micron"], publisher)
    assert g is not None and g.tier == catalysts.MAJOR, publisher


def test_the_date_of_a_report_is_not_the_report() -> None:
    """The first live read of the companies' own releases: Ciena's notice of when it
    will report was a major Earnings story by its "Results"."""
    notice = ("Ciena Announces Reporting Date and Web Broadcast for Fiscal Fourth Quarter and "
              "Year-End 2026 Results")
    assert catalysts.grade(notice).tag in catalysts.NOT_NEWS
    assert catalysts.story(notice, "CIEN", ["Ciena"], "BusinessWire") is None
    for real in ("Ciena Reports Fiscal Fourth Quarter 2026 Financial Results",
                 "Ciena Reports Record Results; Webcast at 8:30 a.m.",
                 "KANZHUN LIMITED Announces Second Quarter 2026 Financial Results"):
        assert catalysts.grade(real) == ("Earnings", catalysts.MAJOR), real


def _store(tmp_path: Any) -> scan_src.ScanStore:
    store = scan_src.ScanStore(str(tmp_path / "w.json"))
    now = time.time()
    for s in store.watchlist():
        store.news_at[s] = now
    store.news_at.pop("AAPL", None)   # the one name due
    return store


RSS = """<rss><channel><item><title>Apple raises its quarterly dividend</title>
<link>https://finance.yahoo.com/news/apple-dividend.html?.tsrc=rss</link>
<description>Apple lifted its payout by four per cent and added to its buyback.</description>
<pubDate>Fri, 13 Nov 2026 14:00:00 +0000</pubDate></item></channel></rss>"""

ANSWER = {"news": [
    {"title": "Apple raises its quarterly dividend", "publisher": "MT Newswires",
     "link": "https://finance.yahoo.com/news/apple-dividend.html", "type": "STORY",
     "providerPublishTime": 1794578400, "relatedTickers": ["AAPL"]},
    {"title": "Is Apple Stock a Buy After Its Dividend Raise?", "publisher": "The Motley Fool",
     "link": "https://www.fool.com/apple-buy", "type": "STORY", "relatedTickers": ["AAPL"]},
]}


def test_the_news_tick_reads_the_named_rows_and_says_so_when_it_cannot(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []
    search_up = True

    def fake(url: str, **kw: Any) -> FetchResult:
        asked.append(kw.get("key") or url)
        if "v1/finance/search" in url:
            if not search_up:
                return FetchResult(False, None, "unavailable", None, "HTTP 429", 429)
            return FetchResult(True, json.dumps(ANSWER).encode(), "live", 0.0, None, 200)
        return FetchResult(True, RSS.encode(), "live", 0.0, None, 200)

    monkeypatch.setattr(scan_src, "fetch", fake)
    store = _store(tmp_path)
    st = store.tick_news()
    assert st.ok and {"scannews_AAPL", "scansearch_AAPL"} <= set(asked)
    rows = store.news["AAPL"]
    assert [(r["publisher"], r["title"][:20]) for r in rows] == [
        ("MT Newswires", "Apple raises its qua"), ("Motley Fool", "Is Apple Stock a Buy")]
    assert rows[0]["summary"].startswith("Apple lifted its payout")
    assert not st.notes
    # The story the score may read is the newswire's; the column is nobody's.
    held = [r for r in rows if catalysts.story(r["title"], "AAPL", ["Apple"], r["publisher"])]
    assert [r["publisher"] for r in held] == ["MT Newswires"]

    # Yahoo's search refusing: the RSS is the rows, with no outlet, and the status says it.
    search_up = False
    store.news_at.pop("AAPL", None)
    st = store.tick_news()
    assert st.ok and [r["publisher"] for r in store.news["AAPL"]] == ["Yahoo Finance"]
    assert any("did not answer for AAPL" in n for n in st.notes)


def test_the_five_feeds_from_the_top_outlets_are_on_the_wire() -> None:
    feeds = {(pub, section): cat for cat, _, pub, section, _ in wire.FEEDS}
    assert feeds[("Bloomberg", "Technology")] == "corp"
    assert feeds[("Bloomberg", "Politics")] == "geo"
    assert feeds[("WSJ", "Business")] == "corp"
    assert feeds[("FT", "Companies")] == "corp"
    assert feeds[("CNBC", "Earnings")] == "corp"
    assert len(wire.FEEDS) == 45 and len({u for _, u, _, _, _ in wire.FEEDS}) == 45


def test_a_story_under_a_share_class_of_the_name_is_the_names() -> None:
    """Yahoo files Alphabet's stories under GOOG and its own "GOOGN", never GOOGL: on the
    first live pass none of GOOGL's 36 stories was its own, and the name was read from
    the RSS with no outlet on any of them."""
    doc = {"news": [
        {"title": "Alphabet wins a cloud contract with the Pentagon", "publisher": "Reuters",
         "link": "https://x/1", "type": "STORY", "relatedTickers": ["GOOGN", "GOOG"]},
        # This name and two others: three companies, though four tickers.
        {"title": "Alphabet, Amazon and Microsoft lift capital spending", "publisher": "Bloomberg",
         "link": "https://x/2", "type": "STORY",
         "relatedTickers": ["GOOG", "GOOGN", "AMZN", "MSFT"]},
        # This name and three others: a list.
        {"title": "Four megacaps to watch", "publisher": "Reuters", "link": "https://x/3",
         "type": "STORY", "relatedTickers": ["GOOG", "AMZN", "MSFT", "META"]},
        {"title": "Nvidia names an interim chief", "publisher": "Reuters", "link": "https://x/4",
         "type": "STORY", "relatedTickers": ["NVDA"]},
    ]}
    for sym in ("GOOGL", "GOOG"):
        assert [r["url"] for r in scan_src.parse_search(doc, sym)] == ["https://x/1", "https://x/2"]
    assert [r["url"] for r in scan_src.parse_search(doc, "NVDA")] == ["https://x/4"]


def test_an_empty_answer_is_not_an_answer() -> None:
    """Yahoo answered 200 with no stories for Amazon, twice in one evening: kept, that
    was the name's news for nine minutes."""
    assert scan_src.search_ok(json.dumps(ANSWER).encode()) is None
    assert scan_src.search_ok(b'{"news": [], "count": 0}') == "no stories in the answer"
    assert scan_src.search_ok(b"<html>Too Many Requests</html>") is not None
