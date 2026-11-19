"use client";

import { useMemo } from "react";
import type { EarningsRow } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { aheadFirst, nearestFirst } from "@/lib/earningsOrder";
import { compact } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * Earnings — the reports that move an index rather than a stock.
 *
 * WHY AN INDEX-FUTURES TERMINAL CARRIES THIS. The Nasdaq 100 is cap-weighted
 * and its top handful of names are roughly a third of it, so NVDA or AVGO after
 * the close moves NQ harder than most macro prints move it in a week. A session
 * note written without knowing who reports tonight is missing the largest
 * scheduled risk in it.
 *
 * BEFORE OR AFTER THE BELL IS THE COLUMN THAT MATTERS, so it leads each row
 * rather than hiding in a tooltip: an after-hours report is tomorrow's gap and a
 * pre-market one is this morning's, and they are different trades.
 *
 * FILTERED BY SIZE UPSTREAM, not here — the collector drops anything under
 * $50bn that is not a bellwether, so this panel renders five or ten names a day
 * instead of three hundred.
 */
/*
 * ON THE STOCKS DESK the panel answers a second question — does anything I
 * trade report soon — so the scanner's watchlist rides along whatever its size
 * and every name on it is marked. On the futures desk it stays about what
 * moves an index.
 */
export function Earnings({
  rows,
  today,
  afterClose = false,
  ageMin,
  error,
  watch,
}: {
  rows: EarningsRow[];
  /** The scanner's watchlist — marked, and kept regardless of size. Stocks desk only. */
  watch?: ReadonlySet<string>;
  /**
   * The ET calendar date, from the collector.
   *
   * NOT `new Date()`. Computing it here ran on the server in UTC and in the
   * browser in local time, so "Today" and "Tomorrow" could disagree between the
   * two renders — a hydration mismatch that React reports and then repairs by
   * throwing the server's markup away. The collector already knows the ET date
   * and it is the same string on both sides.
   */
  today: string;
  /** New York has closed for the day, or it is a weekend: the days ahead lead (lib/earningsOrder). */
  afterClose?: boolean;
  ageMin?: number | null;
  error?: string | null;
}) {
  const byDay = useMemo(() => {
    const m = new Map<string, EarningsRow[]>();
    for (const r of rows) {
      const a = m.get(r.date);
      if (a) a.push(r);
      else m.set(r.date, [r]);
    }
    // Once the session is over, what is coming leads and what has been traded follows.
    return (afterClose ? aheadFirst : nearestFirst)([...m.entries()], today);
  }, [rows, today, afterClose]);

  const mine = watch ? rows.filter((r) => watch.has(r.symbol)).length : 0;
  return (
    <Module
      title="Earnings"
      sub={watch ? `${rows.length} reports · ${mine} on the Scanner` : `${rows.length} large caps`}
      ageMin={ageMin}
      every={30}
      error={error}
      bodyClassName="px-0 py-0"
      /*
       * IT TAKES THE ROOM ITS COLUMN HAS LEFT, AND SCROLLS INSIDE IT (2026-11-15). The
       * Macro board came to sit under this card (owner: "switch rate and policy with
       * macro board") and is 140px taller than Rates & policy was; with fourteen reports
       * listed this card was 596px and pushed the bottom of the board off the screen. It
       * is the one list in its column, as the Calendar is in the other (`qt-fill`,
       * globals.css): the days are in order, so what scrolls out of sight is furthest off.
       */
      className="qt-fill min-h-[260px] flex-1 basis-0"
      scroll
    >
      {rows.length === 0 ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">
          {watch
            ? "Nothing on the Scanner or among the large caps reports in the next two weeks."
            : "Nothing big enough to move an index in the next two weeks."}
        </p>
      ) : (
        byDay.map(([date, list], gi) => (
          <div key={date}>
            <div className="qt-band flex items-baseline gap-2 border-y border-ring/40 bg-surface-2/50 px-3 py-1 first:border-t-0">
              <span className="eyebrow text-[9px]">{label(date, today)}</span>
              <span className="fig text-[9px] text-ink-3">{list.length}</span>
              {/* The figure columns, named where the calendar names its own —
                 the reader has one place to look on both panels. First group
                 only; four repeats of a legend is noise, not labelling. */}
              {gi === 0 && (
                <span className="fig ml-auto text-[8.5px] tracking-wide text-ink-3">
                  <span title="Earnings per share. A trailing 'e' is the consensus estimate; once reported, the actual prints against the estimate — green beat, red miss.">
                    eps
                  </span>
                  <span className="hidden sm:inline" title="Market capitalisation — how much index weight the print can move.">
                    {" "}· cap
                  </span>
                </span>
              )}
            </div>
            <ul>
              {list.map((r) => (
                <li key={`${r.date}-${r.symbol}`} className="hit flex items-baseline gap-2 px-3 py-[3px]">
                  {/* NEUTRAL, BOTH OF THEM (2026-11-14). After the close was pink and
                      before the open green, which on this terminal read as down and up:
                      a time of day is not a side. The letters say which. */}
                  <span
                    className={cn(
                      "fig w-[34px] shrink-0 rounded-sm px-1 text-center text-[9px] leading-[14px]",
                      r.when === "after" || r.when === "pre"
                        ? "qt-pill bg-surface-2 text-ink-2 [--pill-hue:var(--ink-2)]"
                        : "text-ink-4",
                    )}
                    title={
                      r.when === "after"
                        ? "After the close — tomorrow's gap"
                        : r.when === "pre"
                          ? "Before the open — this morning's gap"
                          : "Time not specified"
                    }
                  >
                    {r.when === "after" ? "AMC" : r.when === "pre" ? "BMO" : "—"}
                  </span>
                  <span
                    className={cn(
                      "fig flex w-[70px] shrink-0 items-center gap-1.5 self-center text-[11px]",
                      r.bellwether || watch?.has(r.symbol) ? "text-ink" : "text-ink-2",
                      watch?.has(r.symbol) && "font-semibold",
                    )}
                    title={watch?.has(r.symbol) ? "On your scanner watchlist" : undefined}
                  >
                    <TickerLogo sym={r.symbol} size={13} />
                    {r.symbol}
                    {watch?.has(r.symbol) && (
                      <span aria-label="on the Scanner" className="h-[5px] w-[5px] shrink-0 rounded-full bg-flip-fig qt:rounded-[1px]" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-3">{r.name}</span>
                  {/*
                    * WHICH NUMBER THIS IS, ALWAYS. This was
                    * `eps_actual ?? eps_forecast` in one undifferentiated cell,
                    * so "$1.45" could be a result or a guess and nothing said
                    * which. Now: before the report, the estimate wears an "e";
                    * after it, the actual takes the cell — green or red by the
                    * surprise — and the estimate it beat or missed sits beside
                    * it. The surprise carries the tooltip.
                    */}
                  {r.eps_actual != null ? (
                    <span
                      className="fig shrink-0 text-right text-[10px]"
                      title={
                        r.surprise_pct != null
                          ? `Reported ${r.eps_actual} vs ${r.eps_forecast ?? "?"} expected — ${
                              r.surprise_pct > 0 ? "beat" : r.surprise_pct < 0 ? "miss" : "in line"
                            } by ${Math.abs(r.surprise_pct)}%`
                          : `Reported ${r.eps_actual}`
                      }
                    >
                      <span
                        className={cn(
                          (r.surprise_pct ?? 0) > 0 && "up",
                          (r.surprise_pct ?? 0) < 0 && "down",
                          r.surprise_pct == null && "text-ink",
                        )}
                      >
                        {r.eps_actual}
                      </span>
                      {r.eps_forecast != null && (
                        <span className="text-ink-3"> vs {r.eps_forecast}</span>
                      )}
                    </span>
                  ) : (
                    <span
                      className="fig w-[46px] shrink-0 text-right text-[10px] text-ink-3"
                      title="Consensus EPS estimate — not reported yet"
                    >
                      {r.eps_forecast != null ? `${r.eps_forecast}e` : "—"}
                    </span>
                  )}
                  <span
                    className="fig hidden w-[44px] shrink-0 text-right text-[9.5px] text-ink-3 sm:block"
                    title="Market capitalisation"
                  >
                    {r.market_cap ? compact(r.market_cap) : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </Module>
  );
}

/** "Today", "Tomorrow", else "Wed 2 Sep". */
function label(date: string, today: string): string {
  if (date === today) return "Today";
  const d = new Date(`${date}T12:00:00Z`);
  const t = new Date(`${today}T12:00:00Z`);
  const days = Math.round((d.getTime() - t.getTime()) / 86_400_000);
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  // en-GB and in UTC, so it is "Tue 17 Nov" as the comment above says and as the
  // calendar beside it writes a day; en-US gave "Tue, Nov 17".
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}
