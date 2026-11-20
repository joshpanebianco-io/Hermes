/**
 * The futures we trade, and what the Futures section knows about each (owner,
 * 2026-11-10: "a seperate futures section that has all info related to futures
 * that we trade - nq, es, gc, sil, cl1").
 *
 * ONE LIST. The section's views, the cards and the chart all read it, so a book
 * added here is a book everywhere on the page. Silver and crude ride the board as
 * SILVER and WTI (the header, the brief and the cross-asset panels read those keys),
 * so the quote is looked up under its board key and everything else, the ranges,
 * the profile, gamma and the ladder, under the book's own.
 */

import type { CalendarRow } from "@/types/terminal";

export const FUT_BOOKS = ["NQ", "ES", "GC", "SIL", "CL"] as const;
export type FutBook = (typeof FUT_BOOKS)[number];

export const FUT_NAME: Record<FutBook, string> = {
  NQ: "Nasdaq 100",
  ES: "S&P 500",
  GC: "Gold",
  SIL: "Silver",
  CL: "WTI crude",
};

/** The board's key for a book's quote. */
export const QUOTE_KEY: Record<FutBook, string> = { NQ: "NQ", ES: "ES", GC: "GC", SIL: "SILVER", CL: "WTI" };

/**
 * The books the driver board scores: all five since 2026-11-15, when silver and crude
 * got a bias of their own (server bias.py). A book the collector has not scored yet
 * (an older collector) still says so on its card.
 */
export const SCORED: ReadonlySet<FutBook> = new Set<FutBook>(FUT_BOOKS);

/** The books the trend-or-range record is kept for (server daytype.py). */
export const DAY_TYPED: ReadonlySet<FutBook> = new Set<FutBook>(["NQ", "ES", "GC"]);

// No Overview since 2026-11-14 (owner: "lets remove it completely"): the five side by
// side repeated each contract's own figures row and stood between the page and a chart.
// The written report was a Brief view here until 2026-11-15, a page of its own for a day,
// and is the Market Report view after CL since 2026-11-16 (owner: "in both futures and
// stocks lets add Market Report tab with the generate funcitonality next to cl").
export type FutView = FutBook | "report";

export const FUT_VIEWS: readonly { key: FutView; label: string; title: string }[] = [
  ...FUT_BOOKS.map((b) => ({
    key: b,
    label: b,
    title: `${FUT_NAME[b]}: the chart with its levels, the news that reaches it, the ranges, the profile and gamma`,
  })),
  { key: "report", label: "Market Report", title: "The written report: NQ, ES, GC, SIL or CL, for Asia, London or New York" },
];

export const FUT_VIEW_KEYS: readonly FutView[] = FUT_VIEWS.map((v) => v.key);

/** A view's name in a title: the contract and its name, or the report's. */
export const futViewName = (v: FutView): string => (v === "report" ? "Market Report" : `${v} · ${FUT_NAME[v]}`);

export const isFutBook = (v: string): v is FutBook => (FUT_BOOKS as readonly string[]).includes(v);

const ENERGY = /crude|oil|eia|opec|gasoline|distillate|baker hughes|rig count|natural gas/i;
const METALS = /gold|silver|precious|metal/i;

/**
 * Which of the books a release reaches, by what it is about. A rule of thumb a desk
 * would say out loud, not a measurement: inflation, rates, jobs and the dollar reach
 * the indices and the metals through yields; growth reaches the indices and crude
 * through demand; energy releases reach crude; the dollar reaches crude too.
 *
 * THE MACRO THEMES COUNT ONLY ON A RELEASE THE CALENDAR SAYS REACHES THE US BOOKS
 * (`core`): France's unemployment rate is a jobs number and moves none of them. An
 * energy or metals release is matched by its name wherever it prints.
 */
export function booksOf(row: Pick<CalendarRow, "event" | "themes" | "core">): FutBook[] {
  const t = new Set(row.core === false ? [] : (row.themes ?? []));
  const hit = new Set<FutBook>();
  if (t.has("inflation") || t.has("rates") || t.has("jobs")) for (const b of ["NQ", "ES", "GC", "SIL"] as const) hit.add(b);
  if (t.has("dollar")) for (const b of ["NQ", "ES", "GC", "SIL", "CL"] as const) hit.add(b);
  if (t.has("growth")) for (const b of ["NQ", "ES", "CL"] as const) hit.add(b);
  if (t.has("energy") || ENERGY.test(row.event)) hit.add("CL");
  if (METALS.test(row.event)) {
    hit.add("GC");
    hit.add("SIL");
  }
  return FUT_BOOKS.filter((b) => hit.has(b));
}

/** A US release is "the next" at this score, the Stocks desk's own bar (lib/nextPrint). */
export const US_SCORE = 4;
/** A release named for the commodity itself (crude inventories, for crude) counts from here. */
export const NAMED_SCORE = 3;

/** The releases named for a book's own commodity. The indices have none. */
const NAMED: Record<FutBook, RegExp | null> = { NQ: null, ES: null, GC: METALS, SIL: METALS, CL: ENERGY };

/**
 * The next scheduled release that can move a book: its Next release card.
 *
 * AMERICA'S, AT THE STOCKS DESK'S BAR (2026-11-15, of an audit of the cards the owner
 * answered "do what you recommend"). The card took the soonest release scored 3 or more
 * that `booksOf` passes, from any country: on Saturday 14 Nov 2026 NQ's read "in 23h 57m
 * · GDP Price Index y/y", which was Japan's, with no country on it, and the next thing
 * under it was a regional Fed member at 05:00. It reads a US release scored 4 or more
 * now, the rule the Stocks tab's next event already goes by (lib/nextPrint), on a
 * subject that reaches the book; and a release named for the commodity itself from 3,
 * wherever it prints (the weekly crude inventories are a 3 and are crude's own number).
 * The news card beside it goes by the same idea: nothing from another country's
 * central bank.
 *
 * `leads` are releases, one row each (lib/releases groupReleases, as lib/nextPrint
 * groups them), so 08:30 reads the release's lead series and not whichever of its rows
 * the feed listed first. The soonest wins; at the same minute the higher score, and at
 * the same score the shorter name, which is the headline of two that print together
 * ("Retail Sales m/m" over "Retail Sales Ex Autos m/m", which the feed lists first).
 */
export function nextRelease<T extends Pick<CalendarRow, "event" | "themes" | "core" | "region" | "score" | "ts" | "released">>(
  leads: readonly T[],
  book: FutBook,
  nowSec: number,
): T | null {
  const named = NAMED[book];
  let best: T | null = null;
  for (const r of leads) {
    if (r.released || r.ts == null || r.ts <= nowSec - 60) continue;
    if (!booksOf(r).includes(book)) continue;
    const us = r.region === "us" && r.score >= US_SCORE;
    const own = named != null && named.test(r.event) && r.score >= NAMED_SCORE;
    if (!us && !own) continue;
    const sooner = best === null || r.ts < (best.ts as number);
    const level = best !== null && r.ts === best.ts;
    if (sooner || (level && (r.score > best!.score || (r.score === best!.score && r.event.length < best!.event.length)))) best = r;
  }
  return best;
}
