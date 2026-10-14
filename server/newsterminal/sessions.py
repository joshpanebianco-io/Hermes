"""
The clock — which desks are trading, and what happens next.

WHY A TERMINAL NEEDS THIS AT ALL. Every number on the board means something
different depending on who is awake to trade it. A 40-handle move in ES at
03:00 ET is London repricing the overnight; the same move at 09:31 is the New
York open and is worth ten times the attention. A board with no session context
is a board that flatters the quietest hours.

EVERYTHING IS COMPUTED IN ET AND CONVERTED, never the reverse. The instruments
here settle on CME and NYSE clocks, both of which are defined in New York time
and observe US daylight saving; deriving from local time would put every
boundary an hour out for three weeks of the year, twice a year, which is
exactly the kind of bug that only shows up when you are least able to spot it.

EXCEPT WHERE A BOUNDARY BELONGS TO ANOTHER CITY. London's desks arrive at
07:00 London, which is 02:00 ET for most of the year and 03:00 ET for the
week between the UK's clock change and the US's (and the three weeks every
March the other way round). Those boundaries are London times, converted —
see "the desk day" below, which every module that splits the day reads.

THE OVERLAPS ARE THE POINT. London-New York, 08:00 ET to the LSE's 16:30
London close (11:30 ET, 12:30 ET in the mismatch weeks), is when both of the
two largest pools are open at once and is where the day's range is usually
set. It is called out separately because it is not derivable at a glance from
two rows of open/closed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .holidays import (
    REGULAR_CLOSE,
    close_minute,
    close_time,
    cme_closed,
    cme_halt,
    holiday_name,
    is_trading_day,
)

ET = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

# ---------------------------------------------------------------- the desk day
#
# ONE DEFINITION OF WHERE EACH DESK'S DAY STARTS (review, 2026-10-14). There
# were three "Londons": the ranges started it at 02:00 ET, the calendar at
# 03:00 ET (so UK GDP at 07:00 London printed "in the Asia session"), and the
# brief at 02:00 — all three ET constants, all three an hour out for the weeks
# the two countries' clocks disagree. Now each boundary is written in the zone
# that defines it, and the ranges, the calendar and the brief read it here.
#
#   18:00 ET       Globex reopens: the futures day, and Asia, begin
#   07:00 London   European futures and the London desks are in (Eurex opens
#                  08:00 CET); an hour before the LSE's cash bell
#   10:00 London   the London OPEN window ends — where its damage is done
#   08:00 ET       the overlap and the 08:30 US data window
#   09:30 ET       US cash
#   16:00 ET       US cash close; ES and NQ settle on this minute
#   17:00 ET       Globex halts for its maintenance hour
GLOBEX_REOPEN = time(18, 0)
GLOBEX_HALT = time(17, 0)
LONDON_DESKS = time(7, 0)
LONDON_OPEN_END = time(10, 0)
LONDON_CLOSE = time(16, 30)
PRE_NY = time(8, 0)
NY_OPEN = time(9, 30)
NY_CLOSE = REGULAR_CLOSE

# The windows that split one Globex day, in the order it runs them.
DESK_WINDOWS: list[tuple[str, str]] = [
    ("asia", "Asia"),
    ("london", "London open"),
    ("euro_mid", "Europe midday"),
    ("preny", "Pre-NY"),
    ("ny", "New York"),
    ("post", "Post-close"),
]


def _hours(t: datetime) -> float:
    return t.hour + t.minute / 60.0 + t.second / 3600.0


def desk_window(when: datetime) -> str | None:
    """Which desk window an instant falls in — each boundary on its own city's clock.

    None for 17:00-18:00 ET, Globex's maintenance hour. The clock only: it does
    not ask whether anything traded (a Saturday reads as its weekday hours);
    `globex_open` is that question. Pure.
    """
    et = _hours(when.astimezone(ET))
    if 17.0 <= et < 18.0:
        return None
    if et >= 18.0:
        return "asia"
    if et >= 16.0:
        return "post"
    if et >= 9.5:
        return "ny"
    if et >= 8.0:
        return "preny"
    # Before 08:00 ET the boundaries are London's. ET 00:00-08:00 is London
    # 04:00/05:00-12:00/13:00, so London's hour never wraps here.
    lon = _hours(when.astimezone(LONDON))
    if lon < 7.0:
        return "asia"
    return "london" if lon < 10.0 else "euro_mid"


def london_at(d: date, t: time) -> datetime:
    """London wall time `t` on London date `d`, as an aware instant."""
    return datetime.combine(d, t, tzinfo=LONDON)


def globex_trade_date(when: datetime) -> date:
    """The futures trade date an instant belongs to: from 18:00 ET it is the next
    weekday's, and a weekend belongs to Monday."""
    et = when.astimezone(ET)
    d = et.date()
    if et.time() >= GLOBEX_REOPEN:
        d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def globex_open(when: datetime) -> bool:
    """Are the index and metal futures trading at this instant?

    Shut Friday 17:00 to Sunday 18:00 ET, every day 17:00-18:00, all of a trade
    date CME closes outright (Christmas, New Year's Day, Good Friday), and after
    the early halt on the NYSE's holidays and half days.
    """
    et = when.astimezone(ET)
    wd, t = et.weekday(), et.time()
    if GLOBEX_HALT <= t < GLOBEX_REOPEN:
        return False
    if wd == 5 or (wd == 6 and t < GLOBEX_REOPEN) or (wd == 4 and t >= GLOBEX_HALT):
        return False
    trade = globex_trade_date(when)
    if cme_closed(trade):
        return False
    halt = cme_halt(trade)
    return not (halt is not None and et.date() == trade and t >= halt)


def overlap_end(d: date) -> datetime:
    """The London-New York overlap's end on `d`: the LSE's 16:30 close, in ET."""
    return london_at(d, LONDON_CLOSE).astimezone(ET)

# key, label, city zone, local open, local close, weight
#
# `weight` is a coarse liquidity rank used only for ordering and emphasis in
# the UI — New York and London genuinely dominate, and a clock that gives
# Sydney the same visual weight as the NYSE open misinforms.
SESSIONS: list[tuple[str, str, str, time, time, int]] = [
    ("sydney", "Sydney", "Australia/Sydney", time(10, 0), time(16, 0), 1),
    ("tokyo", "Tokyo", "Asia/Tokyo", time(9, 0), time(15, 30), 3),
    ("hongkong", "Hong Kong", "Asia/Hong_Kong", time(9, 30), time(16, 0), 3),
    ("shanghai", "Shanghai", "Asia/Shanghai", time(9, 30), time(15, 0), 2),
    ("london", "London", "Europe/London", time(8, 0), time(16, 30), 5),
    ("frankfurt", "Frankfurt", "Europe/Berlin", time(9, 0), time(17, 30), 3),
    ("newyork", "New York", "America/New_York", time(9, 30), time(16, 0), 5),
]

# The moments inside a session that reprice things, each on the clock that
# DEFINES it. Not a calendar — these recur and are what the next-event
# countdown runs on.
#
# EACH ONE KEEPS ITS OWN CITY'S CLOCK (review, 2026-10-13). These used to be
# ET constants — "London open 03:00" — which is right only while London and
# New York are on the same side of daylight saving. For the week between the
# UK's change and the US's (and three weeks every March) London's 08:00 is
# 04:00 ET, and the countdown said "London open in 5m" an hour early beside a
# London row that said 65. So the London moments are London times, the NYSE
# ones New York times (moved by the half-day table), and the CME ones the
# futures week's.
#
#   kind      zone              which days
#   globex    New York          Sun–Thu evenings (the reopen for the next session)
#   london    London            UK weekdays
#   nyse      New York          NYSE trading days (holidays skipped)
#   cme       New York          NYSE trading days
#   halt      New York          Globex weekdays, at the early halt on holidays
MARKERS: list[tuple[str, time, str, str]] = [
    ("globex", time(18, 0), "Globex open", "Futures reopen; the new session's first print"),
    ("london", time(7, 0), "London pre-open",
     "European desks arrive; overnight range often breaks"),
    ("london", time(8, 0), "London open", "Cash equities open in London"),
    ("nyse", time(8, 0), "London/NY overlap",
     "Both major pools open — the day's deepest liquidity"),
    ("nyse", time(8, 30), "US data window", "CPI, PCE, payrolls and claims print at this minute"),
    ("nyse", time(9, 30), "NYSE open", "US cash equities open"),
    ("nyse", time(10, 0), "Late data window",
     "ISM, consumer confidence, JOLTS print at this minute"),
    ("london", time(16, 30), "London close",
     "The LSE's closing auction; European desks square up"),
    ("nyse", time(15, 0), "Final hour", "Closing imbalances begin building"),
    # WHAT 16:00 AND 17:00 ACTUALLY ARE (review, 2026-10-14). 17:00 used to be
    # "CME settlement", which it is not: ES and NQ settle off the 30 seconds
    # to 16:00 ET, gold off the minute to 13:30 ET. 17:00 is only the halt.
    ("cme", time(13, 30), "Gold settlement", "COMEX gold settles on this minute"),
    ("nyse", time(16, 0), "NYSE close", "US cash close; ES and NQ settle on this minute"),
    ("halt", time(17, 0), "Globex halt",
     "Futures stop for the maintenance hour; the trade date rolls at 18:00"),
]


def _is_weekend(d: datetime) -> bool:
    return d.weekday() >= 5


def _local_window(now_utc: datetime, zone: str, o: time, c: time) -> tuple[datetime, datetime]:
    """Today's open/close for one city, as UTC instants."""
    tz = ZoneInfo(zone)
    local = now_utc.astimezone(tz)
    start = local.replace(hour=o.hour, minute=o.minute, second=0, microsecond=0)
    end = local.replace(hour=c.hour, minute=c.minute, second=0, microsecond=0)
    return start.astimezone(UTC), end.astimezone(UTC)


def session_state(
    now_utc: datetime | None = None,
    fed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Who is open, who is next, and how long until each changes."""
    now = now_utc or datetime.now(UTC)
    rows: list[dict[str, Any]] = []

    for key, label, zone, o, c, weight in SESSIONS:
        tz = ZoneInfo(zone)
        local = now.astimezone(tz)
        ny = key == "newyork"
        # NEW YORK KEEPS THE NYSE'S CALENDAR: shut on its holidays, and shut at
        # 13:00 on its half days. The row read OPEN on Thanksgiving before
        # (review, 2026-10-13). The other cities' own holidays are not modelled.
        if ny:
            c = close_time(local.date())
        start, end = _local_window(now, zone, o, c)
        weekend = local.weekday() >= 5
        trading = is_trading_day(local.date()) if ny else not weekend
        open_now = trading and start <= now < end

        if open_now:
            nxt, mins = "closes", (end - now).total_seconds() / 60.0
        else:
            # The next open: today's if it has not happened, else tomorrow's,
            # skipping the weekend. Computed by walking days rather than by
            # arithmetic on weekday numbers, because that walk is obviously
            # correct and the arithmetic is obviously not.
            probe = local
            for _ in range(10):
                cand = probe.replace(hour=o.hour, minute=o.minute, second=0, microsecond=0)
                cand_utc = cand.astimezone(UTC)
                day_ok = is_trading_day(cand.date()) if ny else cand.weekday() < 5
                if cand_utc > now and day_ok:
                    break
                probe = probe + timedelta(days=1)
            else:
                cand_utc = now
            nxt, mins = "opens", (cand_utc - now).total_seconds() / 60.0

        rows.append(
            {
                "key": key,
                "label": label,
                "zone": zone,
                "open": open_now,
                "weekend": weekend,
                "local_time": local.strftime("%H:%M"),
                "local_date": local.strftime("%a %d %b"),
                "hours": f"{o.strftime('%H:%M')}–{c.strftime('%H:%M')} local"
                + (" (early close)" if ny and c != REGULAR_CLOSE else ""),
                "holiday": holiday_name(local.date()) if ny else None,
                "next": nxt,
                "next_min": round(mins),
                "weight": weight,
            }
        )

    et = now.astimezone(ET)
    et_min = et.hour * 60 + et.minute

    # The overlap: 08:00 ET to the LSE's close, which is a LONDON time. It was
    # an ET constant (08:00-11:30) on the grounds that a derived value could
    # not be checked; the mismatch weeks are exactly when it is wrong, and
    # tests/test_desk_day.py now checks it.
    overlap = (is_trading_day(et.date()) and et_min >= 8 * 60
               and now < overlap_end(et.date()))

    return {
        "et": et.isoformat(),
        "et_time": et.strftime("%H:%M:%S"),
        "et_date": et.strftime("%a %d %b %Y"),
        "utc": now.isoformat(),
        "weekend": _is_weekend(et),
        "sessions": rows,
        "open_count": sum(1 for r in rows if r["open"]),
        "overlap": overlap,
        "phase": _phase(et, rows),
        "markers": _markers(now, fed),
    }


# Which desks make an overnight phase. New York is deliberately absent: its
# sub-phases are finer than open/closed and come from the ET ladder instead.
_ASIA = {"sydney", "tokyo", "hongkong", "shanghai"}
_EUROPE = {"london", "frankfurt"}


def _phase(et: datetime, rows: list[dict[str, Any]]) -> dict[str, str]:
    """
    The one-line answer to "where are we in the day".

    HALF BUCKETED, HALF DERIVED, and the split is the whole design.

    New York's sub-phases — pre-open, morning, midday, final hours, post-close —
    are finer than open/closed, and they are defined in ET, which IS New York's
    own clock. A fixed ET ladder is exactly right for them and cannot drift.

    ASIA AND LONDON ARE NOT DEFINED IN ET, and bucketing them by it was wrong
    twice over. It read "Globex" from 18:00 ET to midnight, which is most of the
    Asian session: observed 2026-08-31 at 20:51 ET with Sydney and Tokyo both
    marked OPEN in the very rows printed under a label claiming no cash market
    was trading. The panel was contradicting itself on its own face.

    And a merely corrected bucket could not have stayed right. Sydney keeps
    southern-hemisphere DST while New York keeps northern, so Sydney's open
    swings between 18:00 and 20:00 ET across the year and the two zones change
    on four different dates. Any ET constant for it is wrong for part of every
    year. The module docstring's rule — compute in ET, never the reverse — is
    sound for the CME and NYSE boundaries it was written about, because those
    ARE defined in New York time; it does not transfer to Tokyo.

    So the overnight phases are read off `rows`, which already resolve each city
    in its own zone against its own local weekday. One computation now feeds
    both the headline and the list beneath it, so they cannot disagree again.
    """
    wd = et.weekday()
    m = et.hour * 60 + et.minute

    # THE WEEK IS BOUNDED BY GLOBEX, NOT BY THE CALENDAR. Futures shut 17:00 ET
    # Friday and reopen 18:00 ET Sunday, so a plain `weekday() >= 5` called
    # Sunday evening "Weekend" while the new week's first prints were already on
    # the tape. That is not a corner case for this desk: 18:00 ET Sunday is
    # 08:00 Monday in Sydney, i.e. the start of its actual working week.
    if wd == 5 or (wd == 6 and m < 18 * 60) or (wd == 4 and m >= 17 * 60):
        return {"key": "weekend", "label": "Weekend", "note": "Futures reopen Sunday 18:00 ET"}

    # A NYSE HOLIDAY IS NOT A NEW YORK SESSION. It read "NY morning" on
    # Thanksgiving (review, 2026-10-13) beside a New York row that was open.
    # The cash market is closed all day; the index and metal futures run a
    # shortened session and halt at 13:00 ET.
    d = et.date()
    if wd < 5 and cme_closed(d) and m < 18 * 60:
        return {
            "key": "holiday",
            "label": "Market holiday",
            "note": f"{holiday_name(d) or 'CME closed'} — futures and cash shut all day",
        }
    if wd < 5 and not is_trading_day(d) and 8 * 60 <= m < 18 * 60:
        return {
            "key": "holiday",
            "label": "US market holiday",
            "note": f"{holiday_name(d) or 'NYSE closed'} — cash shut; futures halt at 13:00 ET",
        }

    # New York, in New York's own clock — shortened on a half day.
    close_m = close_minute(d)
    half = close_m < 16 * 60
    if 8 * 60 <= m < 9 * 60 + 30:
        return {"key": "preopen", "label": "US pre-open", "note": "Data window and the overlap"}
    if 9 * 60 + 30 <= m < min(11 * 60 + 30, close_m):
        return {"key": "open", "label": "NY morning", "note": "Deepest liquidity of the day"}
    if 11 * 60 + 30 <= m < min(14 * 60, close_m - 60):
        return {"key": "midday", "label": "NY midday", "note": "Volume typically troughs"}
    if 11 * 60 + 30 <= m < close_m:
        return {
            "key": "close",
            "label": "NY final hour" if half else "NY final hours",
            "note": "Early close at 13:00 ET" if half else "Imbalances and positioning",
        }
    if close_m <= m < 18 * 60:
        return {
            "key": "post",
            "label": "Post-close",
            "note": ("Early close today — cash shut at 13:00 ET" if half
                     else "Cash shut; futures run to the 17:00 ET halt"),
        }

    # Overnight: whoever is actually trading says what this is.
    live = {r["key"] for r in rows if r.get("open")}
    asia = bool(live & _ASIA)
    europe = bool(live & _EUROPE)

    if asia and europe:
        return {
            "key": "handover",
            "label": "Asia into London",
            "note": "Hong Kong still trading as Europe arrives",
        }
    if europe:
        return {
            "key": "london",
            "label": "London session",
            "note": "Europe repricing the overnight",
        }
    if asia:
        return {"key": "asia", "label": "Asia session", "note": "Tokyo and Hong Kong lead"}
    return {"key": "globex", "label": "Globex", "note": "Futures only; no cash market open"}


# The Fed releases that land AT A MINUTE and stop the tape, keyed by the
# calendar's own `kind`. Speeches are scheduled too, but they run for an hour
# and belong in the Fed diary rather than on the session clock.
_FED_MARKERS: dict[str, str] = {
    "FOMC": "Rate decision and the statement land at this minute",
    "Beige Book": "The Fed's regional survey lands at this minute",
}


def _fed_markers(et: datetime, fed: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Today's scheduled Fed releases, as session-clock moments.

    THIS REPLACES A DAILY "FOMC HOUR" MARKER, which sat at 14:00 ET every day of
    the year whether or not the committee was meeting. It read as "the FOMC is
    today" on the ~350 days a year when it was not — the reader has no way to
    tell a recurring clock landmark from a real event, and should not have to.
    Now the marker exists only when the Board's calendar says it does, and it
    carries the event's OWN time rather than an assumed 14:00.
    """
    today = et.date().isoformat()
    out: list[dict[str, Any]] = []
    for e in fed or []:
        note = _FED_MARKERS.get(str(e.get("kind") or ""))
        if note is None or e.get("date") != today or not e.get("et"):
            continue
        hh, _, mm = str(e["et"]).partition(":")
        try:
            cand = datetime.combine(et.date(), time(int(hh), int(mm)), tzinfo=ET)
        except ValueError:
            continue
        if cand.timestamp() <= et.timestamp():
            continue  # Already landed. The wire has it now.
        title = str(e.get("title") or e.get("kind") or "").strip()
        out.append(
            {
                "label": title if e.get("kind") == "FOMC" else str(e.get("kind")),
                "note": note,
                "et": cand.strftime("%H:%M"),
                "in_min": round((cand.timestamp() - et.timestamp()) / 60.0),
            }
        )
    return out


def _marker_day_ok(kind: str, d: date) -> bool:
    """Does a marker of this kind happen on its own zone's date `d`?"""
    if kind == "globex":
        # Sunday–Thursday evenings, unless the trade date they open is one CME
        # closes outright (no reopen on Christmas Eve).
        if d.weekday() not in (6, 0, 1, 2, 3):
            return False
        return not cme_closed(globex_trade_date(datetime.combine(d, GLOBEX_REOPEN, tzinfo=ET)))
    if kind in ("london", "halt"):
        return d.weekday() < 5 and not cme_closed(d)
    return is_trading_day(d)  # nyse, cme


def _marker_time(kind: str, label: str, t: time, d: date) -> time:
    """A NYSE moment on a half day: the close moves to 13:00 and the final hour with it.
    Globex's halt moves to 13:00 on an NYSE holiday and 13:15 on a half day."""
    if kind == "halt":
        return cme_halt(d) or t
    if kind != "nyse":
        return t
    close = close_time(d)
    if label == "NYSE close":
        return close
    if label == "Final hour":
        return time(close.hour - 1, close.minute)
    return t


def _markers(now: datetime, fed: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The next few session moments, with minutes to each.

    ELAPSED TIME IS MEASURED ON TIMESTAMPS. Subtracting two datetimes that share
    a tzinfo is wall-clock arithmetic in Python, so across the night the clocks
    change it was out by an hour (01:30 on 2026-11-01 counted 90 minutes to a
    03:00 that was 150 away). And the walk covers the next few days on each
    marker's own calendar, so a Friday evening no longer counts down to a
    Saturday-morning "London open".
    """
    now_ts = now.timestamp()
    et = now.astimezone(ET)
    out: list[dict[str, Any]] = _fed_markers(et, fed)
    for kind, t, label, note in MARKERS:
        zone = LONDON if kind == "london" else ET
        base = now.astimezone(zone).date()
        for k in range(0, 8):
            d = base + timedelta(days=k)
            if not _marker_day_ok(kind, d):
                continue
            cand = datetime.combine(d, _marker_time(kind, label, t, d), tzinfo=zone)
            if cand.timestamp() <= now_ts:
                continue
            out.append(
                {
                    "label": label,
                    "note": note,
                    "et": cand.astimezone(ET).strftime("%H:%M"),
                    "in_min": round((cand.timestamp() - now_ts) / 60.0),
                }
            )
            break
    out.sort(key=lambda r: r["in_min"])
    return out[:4]
