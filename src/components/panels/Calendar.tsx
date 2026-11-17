"use client";

import { useMemo, useState } from "react";
import type { AuctionEvent, CalendarRow, FedEvent, HolidayNotice, Impact, Region } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { cn } from "@/lib/cn";
import { isBool, manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { segItem } from "@/lib/seg";
import { isPending } from "@/lib/events";
import { countryCode, groupReleases, subLabel, type Release } from "@/lib/releases";
import { oneSchedule, tierLit, toggleTier as nextTiers } from "@/lib/schedule";
import { useNow } from "@/lib/useNow";
import { aheadShown } from "@/lib/calendarAhead";
import { PrintPopover, READ_WORD, readTone } from "@/components/vol/PrintRead";

/**
 * The economic calendar.
 *
 * THE SURPRISE IS THE COLUMN THAT MATTERS. A print is not bullish or bearish
 * on its own — it is bullish or bearish against what was already priced. So
 * actual, consensus and previous sit together on one line and the gap between
 * the first two is coloured, because the reaction is a function of that gap
 * and nobody computes it well in the two seconds after 08:30.
 *
 * SIGN IS NOT DIRECTION. A hot CPI and a hot payrolls number are both "above
 * consensus" and they mean opposite things for equities. So a surprise is
 * coloured by MAGNITUDE alone — amber for a meaningful miss either way — and
 * never green-for-good. Deciding what a beat means is the reader's job and the
 * terminal has no business pretending otherwise.
 */

/**
 * Score 0–5 collapsed to the same three tiers the wire uses.
 *
 * ONE VOCABULARY ACROSS THE TERMINAL. The calendar scores 0–5 internally
 * because ranking needs the resolution, but a reader filtering two panels
 * should not have to hold two scales in their head — "high" means the same
 * thing on the tape and on the calendar.
 */
function tierOf(score: number): Impact {
  if (score >= 4) return "high";
  if (score === 3) return "medium";
  return "low";
}

/**
 * THE TIERS ARE TOGGLES THAT COMBINE, exactly as on the wire and for the same
 * reason (owner, 2026-09-22) — see IMPACTS in Wire.tsx. One vocabulary means one
 * behaviour too: two rows of identical chips where one row is pick-one and the
 * other is pick-several would be a trap.
 *
 * LIT IS WHAT YOU SEE, AND THERE IS NO "ALL" AMONG THEM (2026-11-14; lib/schedule).
 * The card had "All 23" here and "All 23" again on the region row. All three lit is
 * the whole calendar.
 */
const TIER_KEYS = ["high", "medium", "low"] as const;
const TIERS: { key: Impact; label: string; hue: string; title: string }[] = [
  {
    key: "high",
    label: "High",
    hue: "var(--err)",
    title: "Stops the tape: CPI, PCE, payrolls, FOMC, GDP. Combines with the other tiers",
  },
  {
    key: "medium",
    label: "Med",
    hue: "var(--warn)",
    title: "Watched: PMI, ISM, claims, confidence, auctions. Combines with the other tiers",
  },
  { key: "low", label: "Low", hue: "var(--ink-4)", title: "Context. Combines with the other tiers" },
];

/**
 * Region, as the desk that trades it rather than the continent it is in.
 *
 * AUSTRALIA AND NEW ZEALAND SIT UNDER APAC with Japan and China because an RBA
 * decision prints inside the Asia session and is read by whoever is trading it.
 * Switzerland and the Nordics sit under EU for the same reason — they print into
 * the London morning. A geographic grouping would split the Asia session across
 * two chips and merge nothing useful.
 */
const REGIONS: { key: Region | "all"; label: string; title: string }[] = [
  { key: "all", label: "All", title: "Every region" },
  { key: "us", label: "US", title: "United States" },
  { key: "eu", label: "EU", title: "Euro Zone, Germany, France, Switzerland, the Nordics" },
  { key: "uk", label: "UK", title: "United Kingdom" },
  { key: "apac", label: "APAC", title: "Japan, China, Hong Kong, Korea, Australia, New Zealand" },
  { key: "other", label: "Other", title: "Everywhere else" },
];

/**
 * WHOSE CALENDAR. The futures desk reads it for what reaches NQ, ES and GC —
 * the collector's `core` judgement. The stocks desk trades New York only, so
 * its MINE is the US calendar from medium impact up (score ≥ 2): every US
 * print moves single names and index ETFs, and nothing printing in Tokyo does
 * until it has reached SPY. Each desk remembers its own filters.
 */
export type CalendarScope = "futures" | "stocks";

const MINE: Record<CalendarScope, { sub: string; on: string; off: string; keep: (r: CalendarRow) => boolean }> = {
  futures: {
    sub: "reaches NQ · ES · GC",
    on: "Showing only releases that reach the books you trade. Click for the full calendar.",
    off: "Showing the full calendar. Click to narrow to what reaches NQ, ES and GC.",
    keep: (r) => r.core,
  },
  stocks: {
    sub: "US releases that move stocks",
    on: "Showing US releases of medium impact and up — what moves the names you trade. Click for the full calendar.",
    off: "Showing the full calendar. Click to narrow to the US releases that move stocks.",
    keep: (r) => r.region === "us" && r.score >= 2,
  },
};

export function Calendar({
  rows,
  fed = NO_FED,
  auctions = NO_AUCTIONS,
  holidays = NO_HOLIDAYS,
  ageMin,
  error,
  scope = "futures",
}: {
  rows: CalendarRow[];
  /**
   * The Fed's diary and the Treasury's coupon auctions (owner, 2026-11-14, of a review
   * of the Macro cards: "do what you recommend"). They were a card of their own a
   * screen below this one; their decisions, minutes, Beige Books and auctions are rows
   * of this list now, less whatever the calendar already lists (lib/schedule).
   */
  fed?: FedEvent[];
  auctions?: AuctionEvent[];
  /**
   * The days a market is shut or shuts early (owner, 2026-11-12: "macro section doesnt
   * list bank holidays etc?"). Neither calendar feed carries them, so they are the
   * collector's own table (holidays.py): US stocks and bonds, London, Tokyo.
   */
  holidays?: HolidayNotice[];
  ageMin?: number | null;
  error?: string | null;
  scope?: CalendarScope;
}) {
  // Futures keeps its original keys, so nothing a reader set before the desks
  // existed is forgotten; the stocks desk gets its own.
  const key = scope === "stocks" ? "cal.stocks." : "cal.";
  const mine = MINE[scope];
  // The tiers that are lit; EMPTY IS THE WHOLE CALENDAR. A stored single string
  // from before this was a list is rejected by `manyOf` and lands on ALL once.
  const [tiers, setTiers] = usePersisted<Impact[]>(
    `${key}tier`,
    [],
    manyOf("high", "medium", "low"),
  );
  const toggleTier = (k: Impact) => setTiers((prev) => nextTiers(prev, k, TIER_KEYS));
  /*
   * MINE IS ON BY DEFAULT, and it is the filter that makes this panel usable.
   * The raw calendar is 220 rows a day, most of it Korean industrial
   * production and Italian unemployment. `core` is the collector's judgement
   * about whether a release reaches NQ, ES or GC — theme and weight together,
   * not country, so a Chinese GDP miss survives and a US housing-starts print
   * does not.
   */
  const [coreOnly, setCoreOnly] = usePersisted<boolean>(`${key}mine`, true, isBool);
  const [region, setRegion] = usePersisted<Region | "all">(
    `${key}region`,
    "all",
    oneOf("all", "us", "uk", "eu", "apac", "global", "other"),
  );

  // ONE RELEASE, ONE ROW (lib/releases): the 08:30 CPI's seven series are one
  // line titled by Core CPI m/m, its other series beneath it. Everything below
  // — the filters, the counts, Ahead and Just printed — works on releases, so
  // a count is the number of lines a chip would show, and the lead's tier,
  // region and `core` speak for the release (its series share all three).
  // The diary's rows join first, so they are filtered, counted and dated as releases are.
  const releases = useMemo(
    () => groupReleases(oneSchedule(rows, fed, auctions), calFields).map(asCal),
    [rows, fed, auctions],
  );

  // The minute clock, so a passed row leaves Ahead on time rather than when
  // the calendar next refetches (every ten minutes) — see lib/events.
  const nowMs = useNow(60_000);
  // SEE MORE (owner, 2026-11-16: "add a bit more of the future things that show up in
  // the calendar? and have a see more if we do want to see more"). Off, the first day
  // is whole and the rest of the fortnight is its big releases, one line each
  // (lib/calendarAhead); on, every release the filters leave, unfolded. Not remembered:
  // the card opens trimmed.
  const [more, setMore] = useState(false);
  const { pending, recent, counts, regionCounts } = useMemo(() => {
    const now = (nowMs ?? Date.now()) / 1000;
    const pool = coreOnly ? releases.filter((x) => mine.keep(x.lead)) : releases;

    // Each chip row counts against the OTHER filters, so a count is what you
    // would actually get by clicking it rather than a total that goes stale the
    // moment anything else moves.
    const byRegion = region === "all" ? pool : pool.filter((x) => x.lead.region === region);
    const c: Record<string, number> = { all: byRegion.length };
    for (const x of byRegion) {
      const t = tierOf(x.lead.score);
      c[t] = (c[t] ?? 0) + 1;
    }
    const lit = (x: CalRelease) => tiers.length === 0 || tiers.includes(tierOf(x.lead.score));
    const byTier = pool.filter(lit);
    const rc: Record<string, number> = { all: byTier.length };
    for (const x of byTier) rc[x.lead.region] = (rc[x.lead.region] ?? 0) + 1;

    const keep = byRegion.filter(lit);
    return {
      counts: c,
      regionCounts: rc,
      // Two weeks of what reaches the books is fifty-odd lines; the cap is for "everything".
      pending: keep.filter((x) => isPending(x, now)).slice(0, 160),
      recent: keep
        .filter((x) => x.released)
        .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))
        .slice(0, 8),
    };
  }, [releases, tiers, coreOnly, region, mine, nowMs]);
  const ahead = useMemo(() => aheadShown(pending, (x) => etDay(x.lead), (x) => x.lead.score, more), [pending, more]);
  const upcoming = ahead.shown;

  // The holidays the filters leave: the region chip narrows them as it does the releases,
  // and the stocks desk's Mine keeps the US ones (it trades New York only). Yesterday's
  // stays for a day, dimmed: a bond holiday is why this morning's yields are two days old.
  const hols = useMemo(() => {
    const today = etToday(nowMs);
    return holidays
      .filter((h) => (region === "all" || h.region === region) && !(coreOnly && scope === "stocks" && h.region !== "us"))
      .map((h) => ({ h, days: today ? dayGap(today, h.date) : 0 }))
      .filter((x) => x.days >= -1)
      .slice(0, 5);
  }, [holidays, region, coreOnly, scope, nowMs]);
  // A HOLIDAY IS A ROW WHEN IT IS NEAR AND A LINE WHEN IT IS NOT (2026-11-14). Three
  // holidays ten days out took a third of the card and left room for three releases.
  // Inside `HOLIDAY_NEAR_DAYS` each keeps its row, because that is when it changes the
  // session being traded; further out they share one line, in full on the hover.
  // With every region in view a release from abroad is its lead line alone (Rows).
  const foldAbroad = region === "all";
  const nearHols = hols.filter((x) => x.days <= HOLIDAY_NEAR_DAYS);
  const farHols = hols.filter((x) => x.days > HOLIDAY_NEAR_DAYS);

  return (
    <Module
      title="Calendar"
      sub={coreOnly ? mine.sub : "everything"}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      /*
       * ITS OWN SCROLL, AND THE ROOM THE COLUMN HAS LEFT. This feed carries 221
       * rows; unfiltered and uncapped it was a wall that pushed every panel under
       * it out of reach, so it was capped at 340px. That cap is why it showed three
       * releases at a time (2026-11-14). It is the only card in its column that can
       * scroll inside itself, so now it takes whatever the board beneath leaves
       * (`qt-fill`, globals.css) and never less than the old 340: the board is whole
       * and the calendar is as tall as the window allows.
       *
       * The rows are sorted by time — the ones you cannot see without scrolling
       * are the ones furthest away, and the next few events are always the ones
       * on screen. The filters live in the module head, which is outside the
       * scrolling body, so narrowing the list never scrolls out of reach.
       */
      /*
       * A CONTAINER, so the rows answer to the panel's own width rather than
       * the window's. Below ~470px of panel (a window under ~1500px) the three
       * figure columns ate the event name down to "BoE MPC …" (review,
       * 2026-10-13: 15 of 19 names truncated at 1280); there the figures move
       * under the name instead and the session column goes.
       */
      className="qt-fill @container min-h-[340px] flex-1 basis-0"
      scroll
      right={
        <div className="flex items-center gap-1.5">
          <span className="seg">
          <button
            type="button"
            onClick={() => setCoreOnly((v) => !v)}
            title={coreOnly ? mine.on : mine.off}
            {...segItem(coreOnly, { hue: "var(--call)", pct: 20, className: cn(coreOnly && "text-call qt:text-ink") })}
          >
            Mine
          </button>
          </span>
          <span className="seg">
          {TIERS.map((t) => {
            const on = tierLit(tiers, t.key);
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => toggleTier(t.key)}
                aria-pressed={on}
                title={t.title}
                {...segItem(on, { hue: t.hue, pct: 26 })}
              >
                {t.label}
                <span className="seg-n">{counts[t.key] ?? 0}</span>
              </button>
            );
          })}
          </span>
        </div>
      }
    >
      <div className="seg seg-bare flex border-b border-ring/50 px-3 py-1.5 qt:pb-2.5">
        {REGIONS.map((r) => {
          const on = region === r.key;
          return (
            <button
              key={r.key}
              type="button"
              onClick={() => setRegion(r.key)}
              title={r.title}
              {...segItem(on, { className: "text-[10px] py-0.5" })}
            >
              {r.label}
              <span className="seg-n">{regionCounts[r.key] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {farHols.length > 0 && (
        <div
          className="flex items-baseline gap-2 border-b border-ring/40 px-3 py-1"
          title={farHols.map(({ h }) => `${dayLong(h.date)}: ${h.label} (${h.name}). ${h.note}`).join("\n")}
        >
          <span className="eyebrow shrink-0 text-[9px]">Holidays ahead</span>
          <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-3">
            {farHols.map(({ h, days }, i) => (
              <span key={`${h.date}-${h.market}`}>
                {i > 0 && " · "}
                <span className="fig">{dayWord(days, h.date)}</span>{" "}
                <span className={h.score >= 5 ? "text-ink" : "text-ink-2"}>{h.label}</span>
              </span>
            ))}
          </span>
        </div>
      )}

      {nearHols.length > 0 && (
        <>
          <Head plain>Holidays and early closes</Head>
          <ul>
            {nearHols.map(({ h, days }) => (
              <li
                key={`${h.date}-${h.market}`}
                title={`${h.name}, ${dayLong(h.date)}. ${h.note}`}
                className={cn("hit flex items-baseline gap-2 px-3 py-[3px]", days < 0 && "opacity-60")}
              >
                <span className={cn("fig w-[84px] shrink-0 text-[10px] whitespace-nowrap", days === 0 ? "text-ink" : "text-ink-3")}>{dayWord(days, h.date)}</span>
                {/* The calendar's own dot: amber where New York is shut, as a release that stops the tape is. */}
                <span
                  className={cn("w-[6px] shrink-0 self-center rounded-full", h.score >= 5 ? "h-[6px] bg-flip" : h.score >= 4 ? "h-[5px] bg-ink-3" : "h-[4px] bg-ink-4")}
                  aria-hidden
                />
                <span className="fig hidden w-[24px] shrink-0 text-[9.5px] text-ink-3 sm:block">{country(h.country)}</span>
                <span className="min-w-0 flex-1 truncate text-[11px] @max-[470px]:whitespace-normal">
                  <span className={days === 0 ? "text-ink" : "text-ink-2"}>{h.label}</span>
                  <span className="text-ink-3"> · {h.name}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {upcoming.length === 0 && recent.length === 0 ? (
        <p className="px-3 py-6 text-center text-[11px] text-ink-3">
          Nothing matches those filters.
        </p>
      ) : (
        <>
          {upcoming.length > 0 && (
            <>
              {/* See more sits in the sticky band, so it is in view however far down the
                  fortnight the list is scrolled. */}
              <Head
                extra={
                  (ahead.hidden > 0 || more) && (
                    <button
                      type="button"
                      onClick={() => setMore((v) => !v)}
                      className="text-[9.5px] text-call hover:underline qt:text-ink-2"
                      title={
                        more
                          ? "Back to the first day in full and only the big releases after it"
                          : `${ahead.hidden} more release${ahead.hidden === 1 ? "" : "s"} the filters leave${ahead.lastDay ? `, to ${ahead.lastDay}` : ""}`
                      }
                    >
                      {more ? "See less" : <>See more <span className="fig text-ink-3">{ahead.hidden}</span></>}
                    </button>
                  )
                }
              >
                Ahead{ahead.lastDay ? ` to ${ahead.lastDay}` : ""}
              </Head>
              <ul>
                {upcoming.map((x, i) => (
                  <Days
                    key={`${x.lead.event}-${x.lead.utc}-${i}`}
                    rel={x}
                    prev={upcoming[i - 1]?.lead}
                    fold={(foldAbroad && x.lead.region !== "us") || ahead.folded(etDay(x.lead))}
                    trimmed={!ahead.whole(etDay(x.lead))}
                  />
                ))}
              </ul>

            </>
          )}
          {recent.length > 0 && (
            <>
              <Head>Just printed</Head>
              <ul>
                {recent.map((x, i) => (
                  <Rows key={`${x.lead.event}-${x.lead.utc}-p${i}`} rel={x} fold={foldAbroad && x.lead.region !== "us"} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </Module>
  );
}

/**
 * One row, preceded by a day rule when the ET date has rolled over.
 *
 * WITHOUT THIS THE LIST LOOKS UNSORTED. The rows are in true chronological
 * order, but the time column shows ET only — so a correctly-ordered list reads
 * "02:30, 03:30, 05:45, 22:00, 00:00, 01:00" and the eye concludes it is
 * scrambled. The day these belong to is the missing column, and a rule is
 * cheaper than repeating a date on every line.
 *
 * KEYED OFF THE ET DATE, not the payload's `date` field — that one is the
 * calendar's own UTC day, and a 22:00 ET release belongs to the following UTC
 * date, which would put the rule in the wrong place.
 */
function Days({ rel, prev, fold, trimmed }: { rel: CalRelease; prev?: CalendarRow; fold?: boolean; trimmed?: boolean }) {
  const day = etDay(rel.lead);
  const changed = !prev || etDay(prev) !== day;
  return (
    <>
      {changed && (
        <li className="flex items-center gap-2 px-3 pt-1.5 pb-0.5">
          <span className="eyebrow text-[9px] text-ink-3">{day}</span>
          {/* A day past the first two shows its big releases alone until See more. */}
          {trimmed && <span className="text-[9px] text-ink-4">high impact only</span>}
          <span className="h-px flex-1 bg-ring/50" aria-hidden />
        </li>
      )}
      <Rows rel={rel} fold={fold} />
    </>
  );
}

/** A release as the panel reads it: the lead's time, and printed once any series has. */
type CalRelease = Release<CalendarRow> & { ts: number | null; released: boolean };

function calFields(r: CalendarRow) {
  return {
    event: r.event,
    when: r.ts,
    country: r.country,
    score: r.score,
    figures: [r.actual_raw, r.consensus_raw, r.previous_raw],
  };
}

function asCal(rel: Release<CalendarRow>): CalRelease {
  const all = [rel.lead, ...rel.subs, ...rel.levels];
  return { ...rel, ts: rel.lead.ts, released: all.some((r) => r.released) };
}

/**
 * The lead row, then each other series of the release as a lighter line under
 * it, its figures in the same three columns. The index levels and unadjusted
 * twins are named on the hover only — see lib/releases.
 */
/*
 * A RELEASE FROM ABROAD IS ONE LINE (2026-11-14). Japan's GDP was six lines and the
 * UK's CPI four, on a card that shows nine: for the books traded here a foreign
 * release is an event with a time and a headline figure, and its other series are
 * detail. So with the region chips on All, a release that is not America's draws its
 * lead alone, with a count, and the rest are on the hover with their figures. A US
 * release keeps every series beneath it, and picking a region's chip unfolds that
 * region's too: that is asking for the detail.
 */
function Rows({ rel, fold }: { rel: CalRelease; fold?: boolean }) {
  const hidden = fold ? rel.subs : [];
  const also = hidden.length
    ? `Also in this release: ${hidden.map((s) => `${subLabel(s.event, rel.lead.event)}${figures(s)}`).join("; ")}`
    : null;
  const folded = rel.levels.length
    ? `Also published, not shown: ${rel.levels.map((r) => r.event).join(", ")}`
    : null;
  const tip = [rel.lead.note, also, folded].filter(Boolean).join("\n\n") || undefined;
  return (
    <>
      <Row r={rel.lead} tip={tip} more={hidden.length} />
      {/* By position too: the UK's GDP comes as four series all named "GDP". */}
      {!fold &&
        rel.subs.map((s, i) => (
          <Row key={`${s.event}-${i}`} r={s} sub={subLabel(s.event, rel.lead.event)} />
        ))}
    </>
  );
}

/** A folded series' figures for the hover: " (actual 0.4%, consensus 0.1%, previous 0.3%)". */
function figures(r: CalendarRow): string {
  const parts = [
    r.released && r.actual_raw ? `actual ${r.actual_raw}` : null,
    r.consensus_raw ? `consensus ${r.consensus_raw}` : null,
    r.previous_raw ? `previous ${r.previous_raw}` : null,
  ].filter(Boolean);
  return parts.length ? ` (${parts.join(", ")})` : "";
}

/** The ET calendar day a release falls on — "Mon 1 Sep". */
function etDay(r: CalendarRow): string {
  if (!r.utc) return "Unscheduled";
  const d = new Date(r.utc);
  if (Number.isNaN(d.getTime())) return "Unscheduled";
  // en-GB, as the holidays above it are written: "Mon 16 Nov", not "Mon, Nov 16".
  return d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "America/New_York",
  });
}

function Head({ children, plain, extra }: { children: React.ReactNode; plain?: boolean; extra?: React.ReactNode }) {
  return (
    // Sticky inside the panel's own scroll, so the column names stay in view
    // down a long day. `plain` is a band over rows with no figures (the holidays):
    // it scrolls away with them rather than sitting over the releases.
    <div className={cn("qt-band flex items-baseline justify-between border-y border-ring/40 bg-surface-2 px-3 py-1 first:border-t-0", !plain && "qt-sticky sticky top-0 z-[2]")}>
      <span className="flex items-baseline gap-2.5">
        <span className="eyebrow text-[9px]">{children}</span>
        {extra}
      </span>
      {/* Names the three figure columns once, instead of three tooltips a
          reader has to discover. Order matches the rows: what printed, what
          was expected, what it was last time. */}
      {!plain && (
        <span className="fig text-[8.5px] tracking-wide text-ink-3 @max-[470px]:hidden">
          act · cons<span className="hidden md:inline"> · prev</span>
        </span>
      )}
    </div>
  );
}

const NO_HOLIDAYS: HolidayNotice[] = [];
const NO_FED: FedEvent[] = [];
const NO_AUCTIONS: AuctionEvent[] = [];

/** A holiday this many days off or nearer has a row of its own; further out it is on the one line. */
const HOLIDAY_NEAR_DAYS = 3;

/** New York's calendar day as "2026-11-11"; null until the page's clock has ticked. */
function etToday(nowMs: number | null): string | null {
  return nowMs == null ? null : new Date(nowMs).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

/** Whole days from one ISO date to another: 1 is tomorrow, -1 yesterday. */
function dayGap(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T12:00:00Z`) - Date.parse(`${from}T12:00:00Z`)) / 86_400_000);
}

const dayLong = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });

/** "Today", "Tomorrow", "Yesterday", else "Thu 26 Nov". */
function dayWord(days: number, iso: string): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

/**
 * One series. `sub` is set for a release's other series: the time, the dot
 * and the country are the lead's, so they stay blank, the name is the series
 * beside its lead ("y/y", "Core y/y") and the line is a size smaller — the
 * figures keep their columns so they read straight down.
 */
function Row({ r, sub, tip, more = 0 }: { r: CalendarRow; sub?: string; tip?: string; more?: number }) {
  // Amber when the print is meaningfully away from consensus. "Meaningful" is
  // relative to the consensus itself, so a 0.2 miss on a 3.0 CPI counts and a
  // 0.2 miss on a 57.8 PMI does not.
  const rel =
    r.surprise !== null && r.consensus
      ? Math.abs(r.surprise) / Math.max(0.1, Math.abs(r.consensus))
      : 0;
  const surprised = r.surprise !== null && (rel > 0.05 || Math.abs(r.surprise) >= 0.2);
  /*
   * WHOSE FIGURE IT IS (owner, 2026-11-15: "the most reputable sources as possible and
   * most official"). The calendar is an aggregator's; for the US releases the agencies
   * publish where a program can read, the collector takes the agency's own figure and
   * the row carries its name: BLS, Census, BEA, EIA. A tag after the name, in ink (a
   * source is not a side), and amber only when the feed had printed something else,
   * which is then the hover. A row with no tag is the feed's alone.
   */
  const off = r.official ?? null;
  const offTitle = off
    ? `${off.text}: ${OFFICIAL_NAME[off.by]}'s own figure for ${off.period}` +
      (off.agrees === false
        ? `. The calendar feed said ${off.feed}; the agency's is the one shown.`
        : off.agrees
          ? ", and the calendar feed says the same."
          : ", in before the calendar feed had it.")
    : undefined;
  const offTag = off && (
    <span
      className={cn("fig text-[8.5px] tracking-[0.04em]", off.agrees === false ? "text-flip" : "text-ink-3")}
      title={offTitle}
    >
      {" "}
      {off.by.toUpperCase()}
      {off.agrees === false ? " ≠ FEED" : ""}
    </span>
  );

  return (
    <li
      className={cn("hit flex items-baseline gap-2 px-3", sub ? "py-[1px]" : "py-[3px]")}
      title={sub ? (r.event !== sub ? r.event : undefined) : (tip ?? r.note ?? undefined)}
    >
      <span className="fig w-[36px] shrink-0 text-[10px] text-ink-3">{sub ? "" : (r.et ?? "—")}</span>
      <span
        className={cn(
          "w-[6px] shrink-0 self-center rounded-full",
          sub ? "h-0" : r.score >= 5 ? "h-[6px] bg-flip" : r.score >= 4 ? "h-[5px] bg-ink-3" : "h-[4px] bg-ink-4",
        )}
        aria-hidden
      />
      <span className="fig hidden w-[24px] shrink-0 text-[9.5px] text-ink-3 sm:block">
        {sub ? "" : country(r.country)}
      </span>
      <span className="min-w-0 flex-1">
        {sub ? (
          <span className="block truncate pl-2 text-[10px] text-ink-3 @max-[470px]:whitespace-normal">
            {sub}
            {offTag}
          </span>
        ) : (
          <span className="block truncate text-[11px] text-ink-2 @max-[470px]:whitespace-normal">
            {r.event}
            {/* The release's other series, folded: how many, and on the hover which. */}
            {more > 0 && <span className="fig text-[9.5px] text-ink-3"> +{more}</span>}
            {offTag}
          </span>
        )}
        {/* Narrow panel: the figures under the name, labelled, so the name
            keeps the width. Only what exists — an unscheduled speech has none. */}
        {(r.actual_raw || r.consensus_raw || r.previous_raw) && (
          <span className="fig hidden text-[10px] text-ink-3 @max-[470px]:block">
            {r.actual_raw && (
              <span className={r.released ? (surprised ? "text-flip" : "text-ink") : undefined}>act {r.actual_raw}</span>
            )}
            {r.actual_raw && (r.consensus_raw || r.previous_raw) && " · "}
            {r.consensus_raw && <>cons {r.consensus_raw}</>}
            {r.consensus_raw && r.previous_raw && " · "}
            {r.previous_raw && <>prev {r.previous_raw}</>}
          </span>
        )}
      </span>
      {/* THE READ, ONCE IT HAS PRINTED: hot, cold or in line — the economy's
          word, never a colour for good or bad — and the click-through to what
          that means for each book (PrintRead). The chip is the trigger, the
          way every VIX figure opens the bands. */}
      {!sub && r.read && (
        <PrintPopover r={r} className="shrink-0 px-1 py-0 leading-none">
          <span className={cn("qt-cap text-[9px]", readTone(r.read))}>{READ_WORD[r.read]}</span>
        </PrintPopover>
      )}
      {r.session && r.session !== "closed" && (
        <span
          className="fig hidden w-[38px] shrink-0 text-[9px] text-ink-3 md:block @max-[470px]:hidden"
          title={sub ? undefined : `Prints during the ${r.session} session`}
        >
          {sub ? "" : r.session}
        </span>
      )}
      <span
        className={cn(
          "fig w-[46px] shrink-0 text-right text-[10.5px] @max-[470px]:hidden",
          r.released ? (surprised ? "text-flip" : "text-ink") : "text-ink-3",
        )}
        title={offTitle ?? (r.released ? "Actual" : "Not printed yet")}
      >
        {r.actual_raw ?? "—"}
      </span>
      <span
        className="fig w-[42px] shrink-0 text-right text-[10px] text-ink-3 @max-[470px]:hidden"
        title="Consensus forecast"
      >
        {r.consensus_raw ?? "—"}
      </span>
      {/* The least decisive of the three, so it is the one that yields on a
          narrow screen — a surprise is judged against consensus, and previous
          only says whether the series is turning. */}
      <span
        className="fig hidden w-[42px] shrink-0 text-right text-[10px] text-ink-3 md:block @max-[470px]:hidden"
        title="Previous reading"
      >
        {r.previous_raw ?? "—"}
      </span>
    </li>
  );
}

/** The release's country in two letters (lib/releases, where the Futures cards read it too). */
const country = countryCode;

/** The agency behind a figure, as the hover says it (server sources/official.py). */
const OFFICIAL_NAME: Record<NonNullable<CalendarRow["official"]>["by"], string> = {
  BLS: "the Bureau of Labor Statistics",
  Census: "the Census Bureau",
  BEA: "the Bureau of Economic Analysis",
  EIA: "the Energy Information Administration",
};
