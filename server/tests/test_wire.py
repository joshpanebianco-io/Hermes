"""The wire's classifiers, which are pure and are where the judgement lives.

EVERY CASE HERE IS A HEADLINE THAT ACTUALLY CAME OFF THE TAPE and was ranked
wrong. The impact tiers and the noise filter are a pile of regexes tuned against
live copy, which is exactly the kind of code that regresses silently when the
next term is added: `backs?`, added for "Fed backs a cut", quietly demoted
"Iran fires back" from a live exchange of fire to speculation, and a bare
`collapse` once ranked a settled crypto arbitration beside a strike on Iran.
"""

from __future__ import annotations

import pytest

from newsterminal.sources.wire import (
    NOISE,
    classify,
    dedupe,
    impact_of,
    is_local_crime,
    is_off_market,
    is_section_page,
)

# ---------------------------------------------------------------- impact


@pytest.mark.parametrize(
    "title",
    [
        # Decided policy.
        "Fed cuts rates by 25 basis points",
        "ECB raises rates for the first time since 2023",
        # Released numbers.
        "US CPI rose 3.1% in August, above forecasts",
        "Nonfarm payrolls come in at 142,000",
        # Shooting, not talking.
        "A U.S. strike on Iran breaks a month-long lull, and Iran fires back",
        "First US military attacks on Iran in a month prompt retaliation",
        "Renewed U.S.-Iran fighting sends oil above $90, threatening higher gas prices",
        # Market structure.
        "Trading halted in the S&P 500 after circuit breaker triggered",
    ],
)
def test_high_is_a_thing_that_happened(title: str) -> None:
    assert impact_of(title) == "high", title


@pytest.mark.parametrize(
    "title",
    [
        # THE WHOLE POINT OF THE SPECULATIVE GUARD. Each of these matches the
        # high list on keywords and is not a decided event.
        "Fed Chair Signals Possible September Rate Hike",
        "Barclays sees two more Fed rate hikes this year after Warsh speech",
        "Global markets fall as Fed rate hike expectations rise",
        "Pound to Euro Weekly Forecast: ECB Rate Hike Threatens GBP Yield Advantage",
        "Oil Prices Fall After US and Iran Receive Framework Ceasefire Proposal",
    ],
)
def test_speculation_about_a_high_event_is_medium(title: str) -> None:
    assert impact_of(title) == "medium", title


@pytest.mark.parametrize(
    "title",
    [
        "Abbott launches ready-to-feed whole milk infant formula",
        "PennantPark unit completes $316.7m debt securitization reset",
        # A bare `collapse` used to make this high.
        "Crypto exchange Gemini not at fault for collapse of Earn lending program",
    ],
)
def test_ordinary_corporate_news_is_low(title: str) -> None:
    assert impact_of(title) == "low", title


# ---------------------------------------------------------------- noise


@pytest.mark.parametrize(
    "title",
    [
        # Motley Fool syndication, which Yahoo's index feed is largely made of.
        "Warren Buffett Has Recommended This 1 Investment for Decades",
        "History Says the Nasdaq Will Do This Next",
        "Prediction: These 2 Stocks Will Beat the Market",
        # The curly apostrophe: `here'?s` with a straight quote matched none of
        # the copy it was aimed at.
        "Trump shrugs off rising prices — here’s what you can do before "
        "inflation eats into your savings",
        # Corporate appointment PR, which flooded the tape from one newswire.
        "Teladoc Health names Michael Grasher as chief financial officer",
        "Innventure appoints Bruce Brown as board chairman",
        # MarketWatch runs its advice column on the top-stories feed, so these
        # reached a trading tape. No market headline is written first-person.
        "My contractor handed my $42,000 pool upgrade to a subcontractor",
        "My friend is charging everyone $80 to attend her 30th birthday party",
        "expion energy appoints marc jarvis to board of directors",
    ],
)
def test_noise_is_dropped(title: str) -> None:
    assert NOISE.search(title), title


@pytest.mark.parametrize(
    "title",
    [
        # A DEPARTURE IS NEWS AND AN APPOINTMENT IS NOT. "Intel CEO steps down"
        # moves the stock and therefore the index, so the appointment filter is
        # deliberately scoped to the appointing verbs.
        "Intel CEO steps down after board loses confidence",
        "John Ternus becomes Apple CEO, with AI as first big challenge",
        "US CPI rose 3.1% in August",
        "A U.S. strike on Iran breaks a month-long lull",
    ],
)
def test_real_news_survives_the_noise_filter(title: str) -> None:
    assert not NOISE.search(title), title


# ---------------------------------------------------------------- corp desk


@pytest.mark.parametrize(
    "title",
    [
        # The analyst-action wire, which is most of the volume on this desk.
        "TD Cowen lowers AutoZone stock price target on DIY headwinds",
        "BMO Capital maintains Market Perform on Stride stock at $93 target",
        "T. Rowe Price stock price target raised to $110 by TD Cowen",
        "Deere upgraded, Lumentum initiated: Wall Street's top analyst calls",
        # Results, guidance and corporate actions.
        "GameStop Q2 2026 preliminary results: sales down, profit up",
        "Aon acquires USI Insurance Services from KKR for $17 billion",
        # Single-stock price action.
        "Affiliated Managers Group stock hits 52-week low at 19.41 USD",
    ],
)
def test_company_news_leaves_the_markets_desk(title: str) -> None:
    """`markets` was a catch-all holding index news, company news and the
    analyst wire at once — 149 of 400 items on one sample."""
    assert classify("markets", title) == "corp", title


@pytest.mark.parametrize(
    "title",
    [
        "Treasury 10-Year Yield Tops 4.75%, Highest Since January 2025",
        "U.S. Stocks Down Amid Mideast Flare-Up",
        "European stocks seal fifth monthly gain",
    ],
)
def test_index_level_news_stays_on_markets(title: str) -> None:
    assert classify("markets", title) == "markets", title


def test_a_bigger_desk_outranks_corp() -> None:
    """corp is ordered after policy, macro and energy: a company story that is
    really a macro or energy story keeps the bigger desk."""
    assert classify("markets", "Trump to host oil executives after refinery profits") == "energy"
    assert classify("markets", "Fed cuts rates by 25 basis points") == "policy"
    # "earnings" is a corp word; the CPI print is still macro.
    assert classify("markets", "US CPI rose 3.1%, denting earnings outlook") == "macro"


# ------------------------------------------------------------ section pages


@pytest.mark.parametrize(
    "title",
    [
        # `site:` queries return an outlet's topic pages looking like stories.
        "NFL Scores, News & Stats | Latest Super Bowl News",
        "Washington",
        "Donald Trump",
    ],
)
def test_section_pages_are_rejected(title: str) -> None:
    assert is_section_page(title), title


def test_a_real_headline_is_not_a_section_page() -> None:
    assert not is_section_page("US strikes Iranian launchers in the strait of Hormuz")


# ---------------------------------------------------------------- category


def test_category_is_promoted_from_the_title() -> None:
    # Arrived on a world feed; the words make it energy.
    assert classify("geo", "US strikes Iranian oil refinery in the Gulf") == "energy"
    assert classify("markets", "Fed holds rates steady at 3.75%") == "policy"
    assert classify("markets", "US CPI rose 3.1% in August") == "macro"


def test_category_reads_the_title_not_the_summary() -> None:
    """A Bloomberg piece on Indian GDP landed on the geo desk because its blurb
    mentioned a border dispute three sentences in.

    The assertion is that it does NOT become geo, not that it becomes macro:
    the title names no macro keyword either, so the correct answer is the feed's
    own default. What matters is that the summary cannot move it.
    """
    got = classify(
        "markets",
        "India's Economy Grows Faster Than Expected in April-June Quarter",
        "Tensions on the disputed border with China weighed on sentiment.",
    )
    assert got != "geo"
    assert got == "markets"


# ---------------------------------------------------------------- dedupe


def test_dedupe_keeps_the_earliest_filer() -> None:
    items = [
        {"title": "US strikes Iranian launchers in the strait of Hormuz",
         "publisher": "Reuters", "ts": 200.0},
        {"title": "US strikes Iranian launchers in the strait of Hormuz today",
         "publisher": "CNBC", "ts": 100.0},
    ]
    out = dedupe(items)  # type: ignore[arg-type]
    assert len(out) == 1
    # The desk that filed first broke it; re-dating on every pickup would show
    # yesterday's story as breaking all afternoon.
    assert out[0]["publisher"] == "CNBC"
    assert "Reuters" in out[0]["also"]


# --- the police blotter -------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        # The one that shipped: on the HIGH crawl beside a strike on Iran,
        # promoted end to end by `invasion` matching a burglary.
        "Man shot and killed in Sydney home invasion was 'targeted attack', police believe",
        "Teenager stabbed to death outside London nightclub",
        "Body found in search for missing Queensland woman",
        "Murder charge over hit-and-run in Melbourne's west",
    ],
)
def test_the_police_blotter_is_not_market_news(title: str) -> None:
    assert is_local_crime(title)
    # And even if a variant slips the list, it must not rank as top-tier.
    assert impact_of(title) != "high"


@pytest.mark.parametrize(
    "title",
    [
        # Violence against a market figure repriced a sector in 2024.
        "Hedge fund founder shot dead outside Miami office",
        "Insurance CEO killed in targeted Manhattan attack, police say",
    ],
)
def test_violence_against_a_market_figure_stays_on_the_tape(title: str) -> None:
    assert not is_local_crime(title)


@pytest.mark.parametrize(
    "title",
    [
        "Russia's invasion of Ukraine escalates as missiles hit Kyiv",
        "China rehearses invasion of Taiwan in largest drills yet",
    ],
)
def test_an_actual_invasion_still_ranks_high(title: str) -> None:
    assert not is_local_crime(title)
    assert impact_of(title) == "high"


# ---------------------------------------------------------------- off-market
#
# Every title below came off the live tape on 2026-10-14; `parse_feed` is
# handed the feed as registered in FEEDS, so these pass the same pair.


@pytest.mark.parametrize(
    ("title", "publisher", "section"),
    [
        # The three the owner saw at the top of the tape.
        ("‘I earn $110,000 a year’: I lost my home in the Great Recession. I’m renting in "
         "my 50s. Why is that judged as failure?", "MarketWatch", "Top"),
        ("PM says housework makes her busier than male predecessors", "Japan Times", "Japan"),
        # The advice column behind a leading quote mark, which hid it from NOISE.
        ("‘I am a pretty cautious person’: My financial adviser wants me to invest $350,000 "
         "in a UAE data center. Is this risky?", "MarketWatch", "Top"),
        ("'I applied for 200 jobs' - How 'spray and pray' AI job applications can backfire",
         "BBC", "Business"),
        ("The Sabrina Carpenter clip that helped a 22-year-old make £120,000 a year",
         "BBC", "Business"),
        # Celebrity property, television, sport — on any feed.
        ("‘Sopranos’ star Steven Van Zandt is selling his Greenwich Village penthouse for "
         "$19 million", "MarketWatch", "Top"),
        ("Lena Dunham’s ‘Girls’ to Return to HBO for 5 New Episodes", "NYT", "Business"),
        ("Choosing a Medicare Advantage Provider for 2027 May Be Easier, but Not Perfect",
         "NYT", "Business"),
        ("FIFA will propose $6.3 billion funding for soccer development, AP sources say",
         "AP", "Economy"),
        # A general-news feed's paper, with nothing economic in the line.
        ("Rays punish error to beat Guardians 3-1 and level series", "Japan Times", "Japan"),
        ("Hakkaku’s complex legacy looms over sumo’s next chapter", "Japan Times", "Japan"),
        ("Guess Which European Country Is Tolerating Child Marriages?", "ZeroHedge", "Markets"),
        ("No black-footed ferrets found in Meeteetse, 40 years after a rescue saved the species",
         "AP", "Economy"),
    ],
)
def test_lifestyle_and_general_news_leave_the_tape(title: str, publisher: str,
                                                   section: str) -> None:
    assert is_off_market(title, publisher, section), title


def test_newsletters_and_quote_pages_are_noise() -> None:
    for title in (
        "Before the Bell: What every Canadian investor needs to know today",
        "AP top stories October 14",
        "Xiaomi Corporation (1810.HK) stock price, news, quote and history",
    ):
        assert NOISE.search(title), title


@pytest.mark.parametrize(
    ("title", "publisher", "section"),
    [
        # Market stories on the same general feeds — each names something economic.
        ("U.K. and Indian economies set to overtake Japan, IMF says", "Japan Times", "Japan"),
        ("SoftBank junk bond sale raises stakes for CEO Son’s all-in AI bet",
         "Japan Times", "Japan"),
        ("Japan’s 2026 rice harvest projected to fall 1%", "Japan Times", "Japan"),
        ("MUFG mulling path to majority control of India’s Shriram Finance",
         "Japan Times", "Japan"),
        ("China sends aircraft carrier group into western Pacific", "Japan Times", "Japan"),
        ("Mining giant BHP to cut hundreds of jobs at iron ore mines", "ABC", "Australia"),
        ("Rex grounds two routes 10 months after $60m rescue package", "ABC", "Australia"),
        ("Trump Announces Federal Support To Keep Local Energy Provider Online In Ohio",
         "ZeroHedge", "Markets"),
        ("More expensive gas, semiconductors likely pushed up inflation last month",
         "AP", "Economy"),
        # A first-person quote that IS a market story: `equity` speaks for it.
        ("\"I'll Be Short Whole Year\": Paul Tudor Jones Warns Of Looming Dot-Com Style "
         "Equity Supply Tsunami", "ZeroHedge", "Markets"),
        # A quote that is not first person.
        ("'A lot of emotion:' First round of redundancies to hit Whyalla steelworks",
         "ABC", "Australia"),
        # Not a general feed: the world and market desks keep their own gates.
        ("Chip stocks suffer worst stretch in 16 months as AI fatigue grips the market",
         "MarketWatch", "Top"),
        ("Hundreds of Royal Mail staff quitting each week under new efficiency plans",
         "BBC", "Business"),
        ("Six Flags’ stock slumps near 17-year low after fatal incident", "MarketWatch", "Top"),
    ],
)
def test_market_stories_stay_on_the_general_feeds(title: str, publisher: str,
                                                  section: str) -> None:
    assert not is_off_market(title, publisher, section), title
