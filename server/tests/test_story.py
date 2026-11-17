"""
What is held under a stock as its news (catalysts.story), and what its lead story is.

EVERY HEADLINE HERE CAME OFF THE TAPE ON WED 11 NOV 2026, the morning the owner asked
that the terminal carry "only … news that can actually impact the market and stocks".
Of the 254 stories then held under the thirty-six names, 102 were not: templates
written about any stock on any day, the company's diary, previews, opinions, lists,
recaps, and stories that were another company's. A third of the names led with one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import catalysts, scanscore
from newsterminal.catalysts import MAJOR, MINOR, NOISE, NOTABLE
from newsterminal.sources import tvnews

# ---- templates and the company's diary are noise ------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        # The fund-flow line.
        "ETFs Are Buying Amazon (AMZN) on Monday",
        "55 ETFs Add to Apple (AAPL) Holdings on Nov. 9",
        "Micron (MU) Sees $554.6 Million in Net ETF Buying on Nov. 9",
        "AMD sees $709 million reversal as major ETFs pile in",
        "Micron draws $554 million in ETF buying after steep selloff",
        "What iShares MSCI USA Min Vol Factor ETF (USMV) Bought: Microsoft Leads on Nov. 9",
        "What State Street Tech Select SPDR (XLK) Sold: Apple Leads on Nov. 9",
        # The fair-value line.
        "Dell (DELL) Stock May Be 42% Undervalued Following AI Server Backlog News",
        "Strategy (MSTR) Stock May Still Look Undervalued Following The Binance Hack",
        "Meta Platforms (META) Wins JPMorgan Backing, Is It Still 37% Below Fair Value?",
        "Tesla (TSLA) Faces A Valuation Test Following Its Cybertruck Wind Down And Robotaxi Pivot",
        "Space Exploration Technologies (SPCX) Director Resigns, Is The 31% Undervaluation "
        "Case Still Intact?",
        # The comparison.
        "INTC vs. TSM: Which Semiconductor Stock Has More Upside Now?",
        "BGC or HOOD: Which Is the Better Value Stock Right Now?",
        # The index-tracker's note.
        "Dell Technologies (DELL) Registers a Bigger Fall Than the Market: Important Facts to Note",
        "Shopify Inc. (SHOP) Is a Trending Stock: Facts to Know Before Betting on It",
        # The formal name with a question hung on it.
        "Oracle Corporation (ORCL) Is Joining the $1.2 Trillion AI Spending Boom: Is the Risk "
        "Being Overlooked?",
        "Intel Corporation (INTC) Is Showing Signs of a Turnaround: Could the Agentic AI Era "
        "Change Its Future?",
        "Sandisk Corporation (SNDK) Secured Billions in Contracted Revenue: Is the Memory Boom "
        "Just Getting Started?",
        # The rich list.
        "Cathie Wood Dumps $3 Million of This Magnificent Seven Stock",
        "Mark Zuckerberg Net Worth Tops $225 Billion: Meta Founder’s Shares Won’t Go to Family",
        # Advice and housekeeping.
        "If I Were in My 20s, I'd Buy This AI ETF After Its Recent Crash and Hold It Forever",
        "Correction to Microsoft on Pace to Surpass Nvidia Article",
        "Weekly Recap: Lumentum acquisition and Q3 revenue outlook maintained",
    ],
)
def test_a_template_about_any_stock_is_noise(title: str) -> None:
    # Filler, unless its words are already a list's or an explainer's: held as a story
    # under no name either way.
    assert catalysts.grade(title).tag in ("Filler", "List", "Opinion"), title
    assert catalysts.grade(title).tag in catalysts.NOT_NEWS
    assert catalysts.story(title) is None


def test_a_template_is_graded_noise_so_the_store_never_keeps_it() -> None:
    for title in ("ETFs Are Buying Amazon (AMZN) on Monday",
                  "Dell (DELL) Stock May Be 42% Undervalued Following AI Server Backlog News",
                  "Cathie Wood Dumps $3 Million of This Magnificent Seven Stock"):
        assert catalysts.grade(title) == ("Filler", NOISE), title


@pytest.mark.parametrize(
    "title",
    [
        # The diary. Mobileye's was filed under Intel and read as a major Earnings story.
        "Mobileye Announces Participation in Upcoming Fourth Quarter 2026 Investor Conferences",
        "Supermicro Announces Participation in Upcoming Investor Events",
        "Compass Pathways to Participate in Jefferies Global Healthcare Conference on "
        "November 18th and 19th",
        # A ceremony, and a marketing index.
        "Oracle Celebrates Groundbreaking on Future Global Headquarters in Nashville",
        "Oracle Corporation (ORCL) Breaks Ground on Nashville Headquarters; First Buildings "
        "Expected in 2030",
        "IBM Digital Sovereignty Index: In the AI Era, Control Is No Longer Enough. "
        "Enterprises Must Prove it.",
        # A call's date, read as a major Earnings story on the Dashboard.
        "Onfolio Holdings Sets Third Quarter 2026 Earnings Call for November 17, 2026, at "
        "8:00 a.m. ET",
        # A sponsorship, and the housekeeping of a company's own debt.
        "World Team Tennis Names Coinbase as Presenting Partner",
        "BWX Technologies, Inc. Announces Pricing Terms, Expiration and Results of Cash Tender "
        "Offers and Consent Solicitations",
    ],
)
def test_the_companys_diary_is_noise(title: str) -> None:
    assert catalysts.grade(title) == ("PR", NOISE), title
    assert catalysts.story(title) is None


def test_the_date_of_a_report_is_the_calendars_to_give() -> None:
    # A preview as it always was; held under no name now.
    t = ("Dell Technologies to Hold Conference Call Nov. 24 to Discuss Third Quarter Fiscal "
         "2027 Financial Results")
    assert catalysts.grade(t).tag == "Preview"
    assert catalysts.story(t, "DELL", ["Dell"]) is None


@pytest.mark.parametrize(
    ("title", "tag", "tier"),
    [
        # What the company did is still news, and so is what was done to it.
        ("AMD Launches 6th Gen EPYC Server Processors To Support AI Workloads", "News", MINOR),
        ("IBM Unveils Next-Gen Quantum Chip. Useful Systems Are Years, Not Decades, Away. "
         "— Barrons.com", "News", MINOR),
        ("Adobe, Google Expand Partnership to Integrate AI, Creative Tools", "News", MINOR),
        ("German antitrust authority says PayPal practices may restrict competition",
         "Legal", MAJOR),
        ("Apple Raised to Buy From Hold by China Renaissance", "Analyst", NOTABLE),
        ("CoreWeave Price Target Cut to $60.00/Share From $120.00 by Stifel", "Target", MINOR),
        ("CoreWeave stock jumps 15% premarket after Q3 revenue beats estimates",
         "Earnings", MAJOR),
        ("GE Vernova shares slide after SoftBank revises US data center project plans",
         "Move", MAJOR),
        ("Marvell's $115 Billion Lumentum Deal Faces 50-50 Odds: Report", "News", MINOR),
        ("Oklo Shares Gain on DOE Clearance to Begin Research, Demonstration at Isotope Test "
         "Reactor", "Move", MAJOR),
    ],
)
def test_what_happened_is_still_news(title: str, tag: str, tier: int) -> None:
    assert catalysts.grade(title) == (tag, tier), title
    assert catalysts.story(title) == (tag, tier)


@pytest.mark.parametrize(
    "title",
    [
        "Why Alphabet and Amazon Will Always Need Nvidia",
        "What Nebius Group Buyers Were Betting On",
        "What Could Lift Netflix Stock From Here?",
        "How Micron Stock Can Soar 148% and End Its Slump — Barrons.com",
    ],
)
def test_an_explainer_or_a_forecast_of_a_move_is_an_opinion(title: str) -> None:
    assert catalysts.grade(title) == ("Opinion", MINOR), title
    assert catalysts.story(title) is None


def test_an_explainer_of_the_names_own_move_is_still_its_move() -> None:
    # The day is not the reason, and the name did move: a bare move, as it was.
    assert catalysts.grade("Why Sandisk Stock Dropped Again on Tuesday") == ("Move", MINOR)
    assert catalysts.story("Why Sandisk Stock Dropped Again on Tuesday", "SNDK",
                           ["Sandisk", "SanDisk"]) == ("Move", MINOR)


# ---- whose story it is ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("sym", "names", "title"),
    [
        # Each was the name's LEAD story that morning, tagged with its ticker alone.
        ("CRWV", ["CoreWeave"], "Nasdaq Futures Rally as AI Optimism Returns — Update"),
        ("NBIS", ["Nebius"], "CoreWeave in spotlight as Wall Street praises Q3 results, guidance"),
        ("COIN", ["Coinbase"], "‘Charges Could Come Soon’: Kalshi Reportedly Faces CFTC Action "
                               "Over Alleged Failure to Notify New Contracts"),
        ("GOOGL", ["Alphabet", "Google"],
         "‘That’s The Bet’: Palmer Luckey Backs Elon Musk’s $150 Billion Robotaxi Ambitions as "
         "Tesla Tops Waymo in Texas"),
        ("AAPL", ["Apple"], "Dan Niles Buys Nvidia Dip, Says Apple's 2011 Rally After Steve Jobs' "
                            "Exit Shows Why Losing a Visionary Isn't the End"),
        ("AVGO", ["Broadcom"], "Chip Stocks Look Like They're in Another Dot-Com Bubble. But "
                               "This Time Could Be Different. — Barrons.com"),
        ("NFLX", ["Netflix"], "Trade Desk's Jeff Green Says Growth Still Falls Short"),
        ("NFLX", ["Netflix"], "AMC Global Media Inc (AMCX) Q3 2026 Earnings Call Highlights: "
                              "Streaming Growth and Netflix Deal ..."),
        ("SMCI", ["Super Micro", "Supermicro"], "China’s Moonshot AI rents advanced Nvidia chips: "
                                                "Bloomberg"),
    ],
)
def test_a_story_that_does_not_lead_with_the_company_is_not_its_story(
        sym: str, names: list[str], title: str) -> None:
    assert catalysts.story(title, sym, names) is None, title


def test_a_name_the_table_has_no_words_for_is_left_to_its_feed() -> None:
    t = "Oklo Shares Gain on DOE Clearance to Begin Research, Demonstration at Isotope Test Reactor"
    assert catalysts.story(t, "OKLO", []) == ("Move", MAJOR)
    assert catalysts.story(t) == ("Move", MAJOR)


def test_a_guessed_name_is_not_held_against_a_headline_that_does_not_carry_it() -> None:
    """The table's words are what a headline writes; a filer's first word is a guess
    ("GENERAL" for a company the wire calls GE Aerospace). A wrong guess must not cost
    the name every story its feed files under it."""
    t = "Jet engine maker's shares jump after record airline orders"
    assert catalysts.story(t, "XYZ", ["GENERAL"]) is None
    got = catalysts.story(t, "XYZ", ["GENERAL"], strict=False)
    # Kept, as the feed's; not as the name's own move, which the headline does not say.
    assert got == ("News", MINOR)
    # A headline that does name it, outside its lead, is somebody else's either way.
    other = "Boeing soars as General Electric lags on engine delays"
    assert catalysts.story(other, "XYZ", ["General Electric"], strict=False) is None


def test_a_round_up_is_nobodys_whoever_it_is_tagged_with(tmp_path: Any) -> None:
    """It reached the Dashboard's stock news by its NDX tag: an index has no name to
    lead a headline, so it was never asked whose story this is."""
    t = ("MU, AMD, AVGO, Other Chip Stocks Surge As CoreWeave Earnings Reignite AI Trade — "
         "Nasdaq-100 Futures Jump")
    assert catalysts.story(t) is None
    assert catalysts.story(t, "NDX", []) is None
    assert catalysts.story(t, "CRWV", ["CoreWeave"]) is None
    # Three names in the lead is still a story of theirs.
    assert catalysts.story("Micron, Amkor and Nvidia shares skyrocket after Samsung strike "
                           "threat") is not None
    store = tvnews.NewsStore(str(tmp_path / "news.json"))
    store.names = lambda sym: {"CRWV": ["CoreWeave"]}.get(sym, [])
    now = 1_800_000_000.0
    store._add([_s(t, ["CRWV", "NDX"], now - 900, "Stocktwits")], now)
    assert store.top(now=now) == []


@pytest.mark.parametrize(
    "title",
    [
        # Found in the app after the rules went live: each still under its name, and the
        # first costing a Sandisk long ten points as a major move against it.
        "Sandisk (SNDK) Dropped, So What Is Behind Its Latest Move?",
        "Oracle Stock Hovers Around the Flatline: What's Going On?",
        "“The Next Trillion Dollar Company”: Marvell Is Up 82% in 2026. Take Profits, or Buy More?",
        "Intel Is Still Up 61% in 2026 After Its October Crash: “A Broken Company,” or a Buy?",
        "Palantir vs. AMD: Both Stocks Have Pulled Back More Than 20%, But 1 Is a Better Value "
        "Buy Here",
        "Shopify Is Just One Of 3 Top Founder Led Stocks",
        "INTC Stock Down 57% in the Past 6 Months: Should You Exercise Caution?",
        "As Democrats Take Over Congress, Is Palantir Stock at Risk?",
        "Forget Palantir? This IPO Candidate May Be the New \"Autonomy Giant\" in Defense.",
        "Leopold Aschenbrenner Bought Sandisk Before It Fell 63%. Is He Wrong, or Early?",
    ],
)
def test_more_templates_found_once_the_rules_were_live(title: str) -> None:
    assert catalysts.grade(title).tag in catalysts.NOT_NEWS, (title, catalysts.grade(title))
    assert catalysts.story(title) is None


def test_the_template_no_longer_costs_sandisk_ten() -> None:
    news = [{"title": "Sandisk (SNDK) Dropped, So What Is Behind Its Latest Move?",
             "age_min": 180.0, "publisher": "Yahoo Finance"}]
    read = scanscore.catalyst_read("long", None, news, None, sym="SNDK",
                                   names=["Sandisk", "SanDisk"])
    assert read["pts"] == 0


@pytest.mark.parametrize(
    "title",
    [
        # And what must still be a story with a question in it or after it.
        "JPMorgan Says Strategy Could Face $2.8 Billion in Forced Selling. What Would That Do "
        "to the Bitcoin Price?",
        "Nvidia Gets a Downgrade on First Call for Huang to Go. The Stock Is Rising. — Barrons.com",
        "Marvell's $115 Billion Lumentum Deal Faces 50-50 Odds: Report",
    ],
)
def test_a_story_with_a_question_beside_it_is_still_a_story(title: str) -> None:
    assert catalysts.story(title) is not None, (title, catalysts.grade(title))


def test_the_dashboards_feed_keeps_the_names_the_reader_could_act_on(tmp_path: Any) -> None:
    """The flow is every US listing; the desk trades names at two billion and over."""
    store = tvnews.NewsStore(str(tmp_path / "news.json"))
    now = 1_800_000_000.0
    store._add([
        _s("Satellogic Shares Gain on Sharply Higher 3Q Results", ["SATL"], now - 120),
        _s("Amgen slips after late-stage trial data for Sjögren's disease therapy", ["AMGN"],
           now - 600, "Seeking Alpha"),
    ], now)
    assert len(store.top(now=now)) == 2
    big = {"AMGN"}
    assert [r["syms"] for r in store.top(now=now, keep=big.__contains__)] == [["AMGN"]]
    # A wrap tagged with an index and a company: not the company's, and an index is
    # nothing to act on. A tender offer for another company is still a deal.
    store.names = lambda sym: {"CRWV": ["CoreWeave"]}.get(sym, [])
    store._add([_s("Nasdaq Futures Rally as AI Optimism Returns — Update", ["IXIC", "CRWV"],
                   now - 60)], now)
    big = {"AMGN", "CRWV"}
    assert [r["syms"] for r in store.top(now=now, keep=big.__contains__)] == [["AMGN"]]
    assert catalysts.story("Pfizer commences tender offer for Metsera at $65 a share") is not None


def test_a_verdict_is_not_a_story() -> None:
    t = "Sandisk Appears a Highly Lucrative Investment After Recent AI Meltdown"
    assert catalysts.grade(t) == ("Filler", NOISE)
    assert catalysts.story(t, "SNDK", ["Sandisk", "SanDisk"]) is None


def test_the_score_reads_a_preview_worded_move_as_the_names_move() -> None:
    """Nebius's row led with it as a Move and the score, which set talk aside before it
    asked whether the name had moved, earned nothing from it."""
    t = ("NBIS Stock Jumps Over 11% On CoreWeave Boost: Analysts Expect Over Six-Fold Growth "
         "In Sales In Upcoming Q3 Report")
    assert catalysts.grade(t).tag == "Preview"
    news = [{"title": t, "age_min": 300.0, "publisher": "Benzinga"}]
    read = scanscore.catalyst_read("long", None, news, None, sym="NBIS", names=["Nebius"])
    assert read["pts"] == 20
    short = scanscore.catalyst_read("short", None, news, None, sym="NBIS", names=["Nebius"])
    assert short["pts"] == 20 and short["reads_against"]
    # A preview that says nobody moved is still talk.
    talk = [{"title": "Will Broadcom Inc. (AVGO) Beat Estimates Again in Its Next Earnings "
                      "Report?", "age_min": 300.0, "publisher": "Yahoo Finance"}]
    assert scanscore.catalyst_read("long", None, talk, None, sym="AVGO",
                                   names=["Broadcom"])["pts"] == 0


def test_a_rewriter_is_nobodys_source() -> None:
    t = "Nvidia Slides 5% Ahead of High-Stakes Independent Spy Probe"
    assert catalysts.story(t, "NVDA", ["Nvidia", "NVIDIA"], "Reuters") is not None
    assert catalysts.story(t, "NVDA", ["Nvidia", "NVIDIA"], "Coinpedia") is None
    assert catalysts.story("Binance Will Support Sandisk's 8-for-1 SNDKB Stock Split", "SNDK",
                           ["Sandisk"], "Binance News") is None


def test_the_names_own_move_in_a_lists_words_is_its_move() -> None:
    t = "TSMC Stocks Rise 1.64% After October Sales Jump 59.7% to a Record"
    assert catalysts.grade(t).tag == "List"
    assert catalysts.story(t, "TSM", ["TSMC"]) == ("Move", MAJOR)
    # A template in a list's words is not: the tracker's note on Oracle read as its move.
    assert catalysts.story("Here's Why Oracle (ORCL) Fell More Than Broader Market", "ORCL",
                           ["Oracle"]) is None


def test_a_recap_no_longer_costs_the_side() -> None:
    """ "Nebius Sinks 12% in a Week" took three off a Nebius long the morning it was up
    eleven per cent. The row's list does not hold it, so the score never reads it."""
    now = datetime(2026, 11, 11, 13, 0, tzinfo=UTC)
    ts = now.timestamp() - 9 * 3600
    own = [{"title": "Nebius Sinks 12% in a Week: “Not All of These Companies Are Going to "
                     "Make It”", "ts": ts, "publisher": "Yahoo Finance"},
           {"title": "NBIS Stock Jumps Over 11% On CoreWeave Boost: Analysts Expect Over Six-Fold "
                     "Growth In Sales In Upcoming Q3 Report", "ts": ts + 3600,
            "publisher": "Benzinga"}]
    got = scanscore.news_for("NBIS", own, [], ["Nebius"], now)
    # The name's own jump is held, though a preview by its words; the recap is not.
    assert [g["title"][:30] for g in got] == ["NBIS Stock Jumps Over 11% On C"]
    read = scanscore.catalyst_read("long", None, got, None, sym="NBIS", names=["Nebius"])
    assert read["pts"] >= 0


# ---- the lead story -------------------------------------------------------------------


def _s(title: str, syms: list[str], at: float,
       provider: str = "Dow Jones Newswires") -> dict[str, Any]:
    g = catalysts.grade(title)
    return {"id": title[:30], "title": title, "url": "", "provider": provider, "at": at,
            "syms": syms, "tag": g.tag, "tier": g.tier}


def test_the_lead_story_is_the_companys_own() -> None:
    now = 1_800_000_000.0
    stories = [
        _s("Nasdaq Futures Rally as AI Optimism Returns — Update", ["CRWV"], now - 540),
        _s("CoreWeave stock jumps 15% premarket after Q3 revenue beats estimates", ["CRWV"],
           now - 840, "Cointelegraph"),
        _s("CoreWeave Database Launches So AI Teams Can Build, Run, and Scale Production "
           "Applications on One Platform", ["CRWV"], now - 1020, "Yahoo Finance"),
    ]
    got = tvnews.best(stories, "CRWV", now, names=["CoreWeave"])
    assert got is not None
    assert got["title"].startswith("CoreWeave stock jumps 15%")
    assert (got["tag"], got["tier"]) == ("Earnings", MAJOR)


def test_an_upgrade_minutes_old_leads_over_somebody_elses_story() -> None:
    now = 1_800_000_000.0
    stories = [
        _s("Dan Niles Buys Nvidia Dip, Says Apple's 2011 Rally After Steve Jobs' Exit Shows Why "
           "Losing a Visionary Isn't the End", ["AAPL"], now - 6480, "Benzinga"),
        _s("Apple Raised to Buy From Hold by China Renaissance", ["AAPL"], now - 240),
        _s("55 ETFs Add to Apple (AAPL) Holdings on Nov. 9", ["AAPL"], now - 8280, "Yahoo Finance"),
    ]
    got = tvnews.best(stories, "AAPL", now, names=["Apple"])
    assert got is not None and got["title"] == "Apple Raised to Buy From Hold by China Renaissance"
    assert got["tag"] == "Analyst"


def test_a_name_with_nothing_real_shows_no_story() -> None:
    now = 1_800_000_000.0
    stories = [
        _s("Shopify Is Just One Of 3 Top Founder Led Stocks", ["SHOP"], now - 3600,
           "Yahoo Finance"),
        _s("Shopify (SHOP) Sees $61.2 Million in Net ETF Buying on Friday", ["SHOP"], now - 7200,
           "Yahoo Finance"),
        _s("Brokers Suggest Investing in Shopify (SHOP): Read This Before Placing a Bet", ["SHOP"],
           now - 9000, "Yahoo Finance"),
    ]
    # The first is a list by its words ("3 … Stocks" is not caught, so it is News): the
    # test is that the two templates are gone and nothing is invented.
    got = tvnews.best(stories, "SHOP", now, names=["Shopify"])
    assert got is None or got["title"].startswith("Shopify Is Just One")
    assert tvnews.best(stories[1:], "SHOP", now, names=["Shopify"]) is None


def test_the_dashboards_feed_carries_only_stories_about_their_names(tmp_path: Any) -> None:
    store = tvnews.NewsStore(str(tmp_path / "news.json"))
    store.names = lambda sym: {"CRWV": ["CoreWeave"], "GEV": ["GE Vernova"]}.get(sym, [])
    now = 1_800_000_000.0
    store._add([
        _s("Nasdaq Futures Rally as AI Optimism Returns — Update", ["CRWV"], now - 540),
        _s("GE Vernova shares slide after SoftBank revises US data center project plans", ["GEV"],
           now - 3600, "Reuters"),
    ], now)
    assert [r["title"][:10] for r in store.top(now=now)] == ["GE Vernova"]
    assert [h["title"][:10] for h in store.headlines("CRWV", now=now)] == []
    assert len(store.panel(now=now)) == 1


# ---- a headline is graded once ---------------------------------------------------------


def test_a_headline_is_graded_once_however_often_it_is_read() -> None:
    """The Scanner's reply asks about every headline under every name on every read. In
    the session of 11 Nov that was 60% of the collector's time, the process sat at a
    whole core, and a slide-out's read missed its eight seconds. The answer is kept."""
    title = "CoreWeave stock jumps 15% premarket after Q3 revenue beats estimates"
    catalysts._story.cache_clear()
    catalysts.grade.cache_clear()
    first = catalysts.story(title, "CRWV", ["CoreWeave"], "Reuters")
    assert first == catalysts.Grade("Earnings", MAJOR)
    before = catalysts._story.cache_info()
    for _ in range(50):
        # A list or a tuple of names, the publisher in any case: one entry.
        assert catalysts.story(title, "CRWV", ("CoreWeave",), " REUTERS ") == first
        assert catalysts.story(title, "CRWV", ["CoreWeave"], "Reuters") == first
    after = catalysts._story.cache_info()
    assert after.misses == before.misses
    assert after.hits == before.hits + 100


@pytest.mark.parametrize(
    ("sym", "names", "publisher", "strict"),
    [
        ("CRWV", ("CoreWeave",), "reuters", True),
        ("NBIS", ("Nebius",), "", True),          # another company's: not its story
        ("NBIS", ("Nebius",), "", False),
        ("", (), "", True),                        # no name asked for: the grade alone
        ("CRWV", ("CoreWeave",), "coinpedia", True),  # a rewriter's copy is nobody's
    ],
)
def test_the_kept_answer_is_the_computed_one(sym: str, names: tuple[str, ...], publisher: str,
                                              strict: bool) -> None:
    for title in (
        "CoreWeave stock jumps 15% premarket after Q3 revenue beats estimates",
        "Nasdaq Futures Rally as AI Optimism Returns — Update",
        "MU, AMD, AVGO, Other Chip Stocks Surge As CoreWeave Earnings Reignite AI Trade",
        "Apple Raised to Buy From Hold by China Renaissance",
        "ETFs Are Buying Amazon (AMZN) on Monday",
        "",
    ):
        kept = catalysts.story(title, sym, names, publisher, strict)
        again = catalysts.story(title, sym, list(names), publisher.upper(), strict)
        fresh = catalysts._story.__wrapped__(title, sym, names, publisher, strict)
        assert kept == again == fresh
