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

import type { CalendarRow, Quote } from "@/types/terminal";

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
 * A board row that is a futures contract, and not the fund beside it.
 *
 * WHY (owner, 2026-11-12, of the Futures overview: "where it has the book we should
 * only have the futures"). The board's "core" group was built for one screen that
 * showed both desks, so each contract is followed by its ETF: NQ then QQQ, ES then
 * SPY, GC then GLD, RTY then IWM. On the Futures tab the funds are another page's.
 * The feed's own symbol says which a row is: every contract's ends "=F" (NQ=F).
 */
export const isFuture = (q: Pick<Quote, "symbol">): boolean => q.symbol?.endsWith("=F") ?? false;

/** The books the driver board scores. Silver and crude are not scored yet. */
export const SCORED: ReadonlySet<FutBook> = new Set<FutBook>(["NQ", "ES", "GC"]);

export const FUT_VIEWS = [
  { key: "overview", label: "Overview", title: "All five at once: price, bias, gamma, the implied day, the nearest levels, what moves them" },
  ...FUT_BOOKS.map((b) => ({ key: b, label: b, title: `${FUT_NAME[b]}: the chart with its levels, the news that reaches it, the ranges, the profile and gamma` })),
  { key: "brief", label: "Brief", title: "The written pre-session brief for NQ, ES and GC" },
] as const;

export type FutView = (typeof FUT_VIEWS)[number]["key"];
export const FUT_VIEW_KEYS: readonly FutView[] = FUT_VIEWS.map((v) => v.key);

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
