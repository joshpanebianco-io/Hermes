"""
The wire's market test and its top tier (sources/wire.py `off_tape`, `market_hooks`,
`is_high`).

EVERY HEADLINE HERE WAS ON THE TAPE ON WED 11 NOV 2026, the morning the owner asked
that the terminal carry "only … news that can actually impact the market and stocks".
Read line by line, 162 of its 400 stories were not market news, and of the fifteen on
the top tier two were events.
"""

from __future__ import annotations

import pytest

from newsterminal.sources import wire
from newsterminal.sources.wire import impact_of, is_high, market_hooks, off_tape

MARKETS = ("CNBC", "Top")

# ---- a story names something a market trades on, or it goes ---------------------------


@pytest.mark.parametrize(
    ("title", "publisher", "section"),
    [
        # On the market feeds, which had no test at all.
        ("Measles is surging in the U.S. — and outbreaks can cost millions", "CNBC", "Top"),
        ("$150 for a Thanksgiving Pie? A Humble Dessert Staple Gets Pricey.", "NYT", "Business"),
        ("Hundreds of schools in Italy, UK evacuated over 'hoax' bomb threats", "CNBC", "Top"),
        ("A Fan-Favorite Aquarium Screen Saver Is Leaving Roku", "NYT", "Business"),
        ("Kim Kardashian's Skims offers refunds for $148 advent calendar after backlash",
         "BBC", "Business"),
        ("Christmas toy rush being driven by squishies and building sets", "BBC", "Business"),
        ("Rep. Jim Jordan, Sen. John Thune elected GOP leaders in Congress", "CNBC", "Top"),
        ("Hegseth impeachment effort torpedoed in House", "CNBC", "Top"),
        ("About Your Next Board Meeting", "WSJ", "Markets"),
        ("Entertainment 360 Acquires Brigade, a Management Firm Rich in Substackers",
         "NYT", "Business"),
        # Through the world gate, each by one word.
        ("Canadian Authorities Kill 4 Bears Involved in Deadly Attack on Hikers", "NYT", "World"),
        ("Haitian PM praises El Salvador after joint strike on alleged home of gang leader",
         "BBC", "World"),
        ("Rights group raises concerns about jailed Dr Abu Safia amid strikes on Gaza",
         "Al Jazeera", "World"),
        ("Transport workers in Chile block highways in protest over surging fuel prices",
         "BBC", "World"),
        ("Spain Hit by General Strike as Cost of Living Takes Center Stage Ahead of Elections",
         "WSJ", "World"),
        ("Najib Razak, Ex-Prime Minister of Malaysia, Is Released to House Arrest", "NYT", "World"),
        ("Israel's parliament sworn in as Eisenkot tries to forge a government", "Reuters",
         "World"),
        # A power is named and nothing is happening between powers.
        ("Ukraine captures first Indonesian prisoner of war amid surge in Russian recruitment",
         "Guardian", "World"),
        ("Outcry after Taiwan asks mainland Chinese tourist to sign independence statement",
         "SCMP", "China"),
        ("US citizen, ‘Chinese blood’: top biologist Yuan Junying caught in debate over returnees",
         "SCMP", "China"),
        # The general feeds' own gate kept these as economic; none moves what is traded here.
        ("'Another Invasion': More Illegals Have Landed On Spain's Canary Islands Than All Last "
         "Year", "ZeroHedge", "Markets"),
        ("Half of Australia's windfarm pipeline is in slowest-building state", "ABC", "Australia"),
        ("Japan top court rules 2025 election in unconstitutional state", "Japan Times", "Japan"),
    ],
)
def test_a_story_that_names_nothing_a_market_trades_on_goes(title: str, publisher: str,
                                                            section: str) -> None:
    assert market_hooks(title) == [], title
    # Nothing a market trades on, unless an earlier, narrower reason caught it first.
    assert off_tape(title, publisher, section) in ("names nothing a market trades on",
                                                   "a court report", "a feature")


@pytest.mark.parametrize(
    ("title", "hook"),
    [
        ("Fed's Paulson calls for gradual rate hikes amid ongoing high inflation", "policy"),
        ("Consumer prices rose 0.4% in October, more than expected, complicating Fed's inflation "
         "fight", "macro"),
        ("US Treasury Futures Retreat as Markets See More Fed Hikes", "rates"),
        ("Euro-Pound Options Turn Bullish as Traders Bet on Bigger Rebound", "rates"),
        ("S&P 500, Nasdaq futures rise as CoreWeave results calm AI jitters", "assets"),
        ("AI Malaise, Midterms Cloud 2027 Profits After Blowout Quarter", "assets"),
        ("Consumers are showing signs of strain even as they keep spending, CNBC/NRF Retail "
         "Monitor shows", "consumer"),
        ("European TTF Gas Rises as Storage Withdrawals Accelerate", "energy"),
        ("Iran warns of domestic gas shortages from war this winter", "energy"),
        ("White House vows to press ahead with tariffs despite midterm backlash over rising "
         "prices", "trade"),
        ("China's goods surplus tops $1 trillion for a second year amid calls for Beijing to "
         "rebalance trade", "trade"),
        ("US lawmakers push China chip rules after Nvidia CEO allegations", "trade"),
        ("US Treasury chief Bessent moved to military base after Iranian threats, sources say",
         "fiscal"),
        ("Nvidia hires law firm Wachtell Lipton to lead Jensen Huang affair probe", "company"),
        ("FDA warns of vision loss risk linked to popular GLP-1 drugs like Wegovy, Zepbound",
         "company"),
        ("KKR, Germany’s RWE Invest $16 Billion in U.K. Wind-Power Projects", "company"),
        ("Canada's Barrick Mining files for IPO of North American business in New York",
         "company"),
        ("Iran denies talks with US, says Hormuz will stay shut until demands are met", "geo"),
        ("Russia, Ukraine and US start second day of Abu Dhabi peace talks", "geo"),
        ("Rubio says no need for major combat operations against Iran given US economic campaign",
         "geo"),
        ("Deal vs deal? US, China trade calls to honour commitments before Xi-Trump summit",
         "geo"),
        ("China sends aircraft carrier group into western Pacific", "geo"),
    ],
)
def test_what_a_market_trades_on_stays(title: str, hook: str) -> None:
    assert hook in market_hooks(title), (title, market_hooks(title))
    assert off_tape(title, *MARKETS) is None


def test_the_institutions_own_words_always_stay() -> None:
    # A Fed governor's speech names no bank and no number.
    t = "Waller, The Economic Outlook and Some Thoughts on Labor Market Dynamism"
    assert off_tape(t, "Federal Reserve", "Speeches") is None
    assert off_tape("Exchange of letters between the Governor and the Chancellor on the Asset "
                    "Purchase Facility - November 2026", "Bank of England", "Policy") is None
    assert off_tape(t, *MARKETS) is not None


# ---- a keyword search returns whoever used the words ----------------------------------


@pytest.mark.parametrize(
    ("title", "outlet"),
    [
        # Months-old releases dated that morning.
        ("US Crude Oil Output Fell in May, While Exports Hit Record, EIA Says", "EnergyNow.com"),
        ("Saudi June Crude Exports Climb From Record May Low, Data Shows", "EnergyNow.com"),
        ("Oil (USCrude) Price Forecast for Today, Tomorrow, Next Week, and Next 30 Days",
         "LiteFinance"),
        ("China Oil Imports Reach 41.94 Million Tons in October 2026, Highest Since March - News "
         "and Statistics", "IndexBox"),
        ("Central Bank Outlook 2027: Fed, ECB, BoE, BoJ and PBoC Diverging Paths - News and "
         "Statistics", "IndexBox"),
        ("Stock markets end higher; Sensex, Nifty jump nearly 1 pc", "DT Next"),
        # No outlet named at all.
        ("HANG SENG INDEX (^HSI) Charts, Data & News - Yahoo! Finance Canada", "Google News"),
    ],
)
def test_a_search_result_from_no_newsroom_goes(title: str, outlet: str) -> None:
    assert not wire.is_newsroom(outlet)
    assert off_tape(title, "Google News", "Energy", outlet) == "not a newsroom"


@pytest.mark.parametrize("outlet", ["Reuters", "AP News", "Bloomberg.com", "Financial Times",
                                    "The Guardian", "CNBC", "The Telegraph"])
def test_a_newsroom_is_a_newsroom(outlet: str) -> None:
    assert wire.is_newsroom(outlet)
    assert off_tape("Oil falls below $90 as Trump pulls back from threat to strike Iran",
                    "Google News", "Energy", outlet) is None


def test_a_feed_that_is_its_own_publisher_is_not_asked() -> None:
    # DW is in the feed table; it is not on the search list, and is not a search result.
    assert not wire.is_newsroom("DW")
    assert off_tape("Qatar LNG Loadings Climb To Half Of Pre-War Levels As Energy-Starved Europe "
                    "Prays For Winter Relief", "DW", "Business") is None


@pytest.mark.parametrize(
    ("title", "why"),
    [
        ("Current price of oil as of November 11, 2026", "a page, not a story"),
        ("Earnings call transcript: RWE Q3 2026 tops strategy goals despite EPS miss",
         "a page, not a story"),
        ("Tech, Media & Telecom Roundup: Market Talk", "a page, not a story"),
        ("Five Books About World War II for Young Readers", "a feature"),
        ("‘In Flanders Fields’: How a patriotic poem became an anti-war anthem", "a feature"),
        ("'If I tell you to run, run': BBC joins a Ukrainian drone unit as it protects a "
         "front-line city", "a feature"),
        ("The 49ers acquire WR Keenan Allen from the Colts, AP source says", "a feature"),
        ("Tiger Woods has another private, 18-hole golf destination in the works — this one for "
         "Long Island’s Gold Coast", "a feature"),
        # A press release, by the listing it names; a court's verdict on a person.
        ("Rantizo (Nasdaq: RNTZ) Advances U.S. Production of Heavy-Lift Autonomous Drones After "
         "$258.8 Million Acquisition, Targets California’s $61.2 Billion Agricultural Market",
         "a page, not a story"),
        ("UK fraudster who invented ‘too good to be true’ takeover bid given suspended sentence",
         "a court report"),
        ("Liquidators probe multi-million-dollar sale of collapsed Mundella assets",
         "names nothing a market trades on"),
        # An analyst repeating himself on a company that moves no index.
        ("Needham reiterates Thryv stock rating at Buy with $6 target",
         "an analyst's note on a company that moves no index"),
        ("Evercore ISI cuts StubHub stock price target to $13 on Q4 outlook",
         "an analyst's note on a company that moves no index"),
    ],
)
def test_pages_features_and_housekeeping_go(title: str, why: str) -> None:
    assert off_tape(title, *MARKETS) == why


def test_an_analysts_note_on_an_index_mover_stays() -> None:
    assert off_tape("Susquehanna reiterates Positive rating on Boeing stock at $250",
                    "Investing.com", "News") is None


def test_the_advice_column_behind_an_if() -> None:
    assert wire.NOISE.search("If I Were in My 20s, I'd Buy This AI ETF After Its Recent Crash "
                             "and Hold It Forever")


# ---- the top tier ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        # The print itself: medium that morning, for want of the letters CPI.
        "Consumer prices rose 0.4% in October, more than expected, complicating Fed's inflation "
        "fight",
        "Inflation runs hotter than expected as higher prices extend beyond the gas station",
        "Rate-Hike Debate Ignited by Fed Officials as CPI Comes in Hot",
        # A chokepoint shut: low that morning.
        "Iran denies talks with US, says Hormuz will stay shut until demands are met",
        # Shooting between named powers, in the headline's own clause.
        "U.S., Iran Exchange Strikes on Islands as They Fight for Control of Strait",
        # A decision.
        "Fed holds rates steady at 3.75%",
        "Bank of Japan raises rates to 1%",
    ],
)
def test_a_decision_a_print_or_shooting_is_high(title: str) -> None:
    assert is_high(title), title
    assert impact_of(title) == "high"


@pytest.mark.parametrize(
    "title",
    [
        # A central banker talking, or a paper analysing: nine of the fifteen that morning.
        "The Fed Has to Raise Rates. How Fast To Go Has Officials Divided.",
        "Fed to raise rates once more in December as inflation risks stay high: Reuters poll",
        "Fed's Paulson calls for gradual rate hikes amid ongoing high inflation",
        "Fed officials open door to a quicker round of rate hikes as inflation worsens",
        "Elevated Inflation Keeps Pressure on Fed to Raise Rates",
        "BOE's Lombardelli does not rule out December rate hike, she tells the Guardian",
        "Fed’s Goolsbee Says October CPI Report ‘Borderline Disturbing’",
        # Somebody else's number, and somebody else's rates.
        "German October inflation confirmed at 2.8%",
        "Australia’s Home Loans Fall by Record After Rapid RBA Rate Hikes",
        # A war that is in the second clause, and one side's daily tally.
        "Baltic nations, Finland issue overnight drone warnings as Russia, Ukraine exchange "
        "strikes",
        "Russia shoots down 92 drones over Leningrad region",
        # A word that is not an attack.
        "China backs Cuba in opposing sanctions, blockades; pledges 'firm support', Xinhua reports",
        # A company failing that moves no index.
        "One reason Children’s Place is filing for bankruptcy? Not enough children.",
    ],
)
def test_talk_and_other_peoples_numbers_are_medium(title: str) -> None:
    assert not is_high(title), title
    assert impact_of(title) == "medium"


@pytest.mark.parametrize(
    "title",
    [
        "Haitian PM praises El Salvador after joint strike on alleged home of gang leader",
        "Rights group raises concerns about jailed Dr Abu Safia amid strikes on Gaza",
        "'Another Invasion': More Illegals Have Landed On Spain's Canary Islands Than All Last "
        "Year",
        "Citigroup CEO Jane Fraser strikes bullish tone on China expansion after brokerage "
        "approval",
        # A plot is not an attack, and "attacks including" names no target.
        "Three Iran-backed suspects plotted attacks including RAF Fairford incident, US says",
    ],
)
def test_a_word_alone_is_never_high(title: str) -> None:
    assert not is_high(title), title


@pytest.mark.parametrize(
    "title",
    [
        # Under-ranked that morning: each low, each a thing that moves a name or a sector.
        "Nvidia hires law firm Wachtell Lipton to lead Jensen Huang affair probe",
        "US lawmakers push China chip rules after Nvidia CEO allegations",
        "FDA warns of vision loss risk linked to popular GLP-1 drugs like Wegovy, Zepbound",
        "Rubio says no need for major combat operations against Iran given US economic campaign",
        "Russia, Ukraine and US start second day of Abu Dhabi peace talks",
        "Adnoc Gas Still Evaluating Options to Bypass Strait of Hormuz",
    ],
)
def test_what_was_ranked_too_low_is_medium(title: str) -> None:
    assert impact_of(title) == "medium", title


def test_the_headlines_own_clause() -> None:
    assert wire.main_clause("Rights group raises concerns about jailed Dr Abu Safia amid strikes "
                            "on Gaza") == "Rights group raises concerns about jailed Dr Abu Safia"
    assert wire.main_clause("EXCLUSIVE: India holds Pernod, Diageo Scotch shipments as "
                            "investigators seek higher tariff").startswith("India holds")
    # "on" is inside the clause.
    assert "Iran" in wire.main_clause("A U.S. strike on Iran breaks a month-long lull")
    assert wire.actors("U.S., Iran Exchange Strikes on Islands") == {"us", "iran"}
    assert wire.actors("Renewed U.S.-Iran fighting sends oil above $90") == {"us", "iran"}
    # "us", the pronoun, is nobody.
    assert wire.actors("Give us a break, say traders") == set()


def test_parse_feed_applies_the_market_test() -> None:
    def item(title: str) -> str:
        return (f"<item><title>{title}</title><link>https://example.com/{abs(hash(title))}</link>"
                "<pubDate>Wed, 11 Nov 2026 12:00:00 GMT</pubDate></item>")

    xml = ("<rss><channel>"
           + item("Measles is surging in the U.S. — and outbreaks can cost millions")
           + item("Treasuries slide as hot inflation sparks bets on Fed rate rise")
           + "</channel></rss>")
    got = wire.parse_feed(xml, "CNBC", "Top", "markets")
    assert [g["title"][:10] for g in got] == ["Treasuries"]
    # Through a search: the outlet the suffix names has to be a newsroom.
    xml = ("<rss><channel>"
           + item("US Crude Oil Output Fell in May, While Exports Hit Record, EIA Says - "
                  "EnergyNow.com")
           + item("Oil falls below $90 as Trump pulls back from threat to strike Iran - "
                  "Financial Times")
           + "</channel></rss>")
    got = wire.parse_feed(xml, "Google News", "Energy", "energy", via_google=True)
    assert [(g["publisher"], g["title"][:9]) for g in got] == [("Financial Times", "Oil falls")]
