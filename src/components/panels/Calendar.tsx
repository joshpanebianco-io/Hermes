"use client";

import { useMemo } from "react";
import type { CalendarRow, Impact, Region } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { cn } from "@/lib/cn";
import { isBool, manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { segItem } from "@/lib/seg";
import { isPending } from "@/lib/events";
import { groupReleases, subLabel, type Release } from "@/lib/releases";
import { useNow } from "@/lib/useNow";

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
 * other is pick-several would be a trap. None lit is ALL; all three lit is ALL.
 */
const TIERS: { key: Impact | "all"; label: string; hue: string; title: string }[] = [
  { key: "all", label: "All", hue: "var(--ink-3)", title: "Every release on the calendar — clears the tiers" },
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
  ageMin,
  error,
  scope = "futures",
}: {
  rows: CalendarRow[];
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
  const toggleTier = (k: Impact | "all") =>
    setTiers((prev) => {
      if (k === "all") return [];
      const next = prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k];
      return next.length === TIERS.length - 1 ? [] : next;
    });
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
  const releases = useMemo(() => groupReleases(rows, calFields).map(asCal), [rows]);

  // The minute clock, so a passed row leaves Ahead on time rather than when
  // the calendar next refetches (every ten minutes) — see lib/events.
  const nowMs = useNow(60_000);
  const { upcoming, recent, counts, regionCounts } = useMemo(() => {
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
      upcoming: keep.filter((x) => isPending(x, now)).slice(0, 20),
      recent: keep
        .filter((x) => x.released)
        .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))
        .slice(0, 8),
    };
  }, [releases, tiers, coreOnly, region, mine, nowMs]);

  return (
    <Module
      title="Calendar"
      sub={coreOnly ? mine.sub : "everything"}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      /*
       * CAPPED, WITH ITS OWN SCROLL. This feed carries 221 rows. Unfiltered and
       * uncapped it was not a panel, it was a wall: every live panel below it in
       * the column sat behind a fortnight of macro events, which is how sector
       * rotation ended up six panels down and effectively unreachable.
       *
       * The cap is safe precisely because the rows are sorted by time — the ones
       * you cannot see without scrolling are the ones furthest away, and the
       * next few events are always the ones on screen. The filters live in the
       * module head, which is outside the scrolling body, so narrowing the list
       * never scrolls out of reach.
       */
      /*
       * A CONTAINER, so the rows answer to the panel's own width rather than
       * the window's. Below ~470px of panel (a window under ~1500px) the three
       * figure columns ate the event name down to "BoE MPC …" (review,
       * 2026-10-13: 15 of 19 names truncated at 1280); there the figures move
       * under the name instead and the session column goes.
       */
      className="@container max-h-[340px]"
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
            const on = t.key === "all" ? tiers.length === 0 : tiers.includes(t.key);
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

      {upcoming.length === 0 && recent.length === 0 ? (
        <p className="px-3 py-6 text-center text-[11px] text-ink-3">
          Nothing matches those filters.
        </p>
      ) : (
        <>
          {upcoming.length > 0 && (
            <>
              <Head>Ahead</Head>
              <ul>
                {upcoming.map((x, i) => (
                  <Days key={`${x.lead.event}-${x.lead.utc}-${i}`} rel={x} prev={upcoming[i - 1]?.lead} />
                ))}
              </ul>
            </>
          )}
          {recent.length > 0 && (
            <>
              <Head>Just printed</Head>
              <ul>
                {recent.map((x, i) => (
                  <Rows key={`${x.lead.event}-${x.lead.utc}-p${i}`} rel={x} />
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
function Days({ rel, prev }: { rel: CalRelease; prev?: CalendarRow }) {
  const day = etDay(rel.lead);
  const changed = !prev || etDay(prev) !== day;
  return (
    <>
      {changed && (
        <li className="flex items-center gap-2 px-3 pt-1.5 pb-0.5">
          <span className="eyebrow text-[9px] text-ink-3">{day}</span>
          <span className="h-px flex-1 bg-ring/50" aria-hidden />
        </li>
      )}
      <Rows rel={rel} />
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
function Rows({ rel }: { rel: CalRelease }) {
  const folded = rel.levels.length
    ? `Also published, not shown: ${rel.levels.map((r) => r.event).join(", ")}`
    : null;
  const tip = [rel.lead.note, folded].filter(Boolean).join("\n\n") || undefined;
  return (
    <>
      <Row r={rel.lead} tip={tip} />
      {rel.subs.map((s) => (
        <Row key={s.event} r={s} sub={subLabel(s.event, rel.lead.event)} />
      ))}
    </>
  );
}

/** The ET calendar day a release falls on — "Mon 1 Sep". */
function etDay(r: CalendarRow): string {
  if (!r.utc) return "Unscheduled";
  const d = new Date(r.utc);
  if (Number.isNaN(d.getTime())) return "Unscheduled";
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "America/New_York",
  });
}

function Head({ children }: { children: React.ReactNode }) {
  return (
    // Sticky inside the panel's own scroll, so the column names stay in view
    // down a long day.
    <div className="qt-band qt-sticky sticky top-0 z-[2] flex items-baseline justify-between border-y border-ring/40 bg-surface-2 px-3 py-1 first:border-t-0">
      <span className="eyebrow text-[9px]">{children}</span>
      {/* Names the three figure columns once, instead of three tooltips a
          reader has to discover. Order matches the rows: what printed, what
          was expected, what it was last time. */}
      <span className="fig text-[8.5px] tracking-wide text-ink-3 @max-[470px]:hidden">
        act · cons<span className="hidden md:inline"> · prev</span>
      </span>
    </div>
  );
}

/**
 * One series. `sub` is set for a release's other series: the time, the dot
 * and the country are the lead's, so they stay blank, the name is the series
 * beside its lead ("y/y", "Core y/y") and the line is a size smaller — the
 * figures keep their columns so they read straight down.
 */
function Row({ r, sub, tip }: { r: CalendarRow; sub?: string; tip?: string }) {
  // Amber when the print is meaningfully away from consensus. "Meaningful" is
  // relative to the consensus itself, so a 0.2 miss on a 3.0 CPI counts and a
  // 0.2 miss on a 57.8 PMI does not.
  const rel =
    r.surprise !== null && r.consensus
      ? Math.abs(r.surprise) / Math.max(0.1, Math.abs(r.consensus))
      : 0;
  const surprised = r.surprise !== null && (rel > 0.05 || Math.abs(r.surprise) >= 0.2);

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
          <span className="block truncate pl-2 text-[10px] text-ink-3 @max-[470px]:whitespace-normal">{sub}</span>
        ) : (
          <span className="block truncate text-[11px] text-ink-2 @max-[470px]:whitespace-normal">{r.event}</span>
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
        title={r.released ? "Actual" : "Not printed yet"}
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

/** Three letters is enough to place a release and costs a third of the width. */
function country(c: string): string {
  const map: Record<string, string> = {
    "United States": "US",
    "Euro Zone": "EZ",
    "United Kingdom": "UK",
    Germany: "DE",
    Japan: "JP",
    China: "CN",
    Canada: "CA",
    Australia: "AU",
    France: "FR",
    Italy: "IT",
    Switzerland: "CH",
    "South Korea": "KR",
    "Hong Kong": "HK",
    India: "IN",
    Brazil: "BR",
  };
  return map[c] ?? c.slice(0, 2).toUpperCase();
}
