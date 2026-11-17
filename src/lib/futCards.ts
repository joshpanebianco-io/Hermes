/**
 * The small rules of a futures contract's card row (owner, 2026-11-15: "in futures what
 * are the most important things ot display in the cards?").
 *
 * THE ROW, AND HOW IT CAME TO BE SIX. It was seven: price, bias, gamma, Implied day,
 * Range used, Implied vol and the next release. The three in the middle were one reading
 * (the day the options price, how much of it is spent, the index it is read from), so
 * they became one card, Day range, and a Nearest levels card took the freed place. The
 * owner asked the same day whether anything more useful could stand where those two did
 * ("is there anything mor euseful we can replace day range and nearest levels with?"),
 * and each was a second copy of something on the page: the range used is the Fuel line
 * of the Session ranges card under the row, and the distance to a level is on the chart
 * beside it. So the row is:
 *
 *   price · bias · gamma · SESSION TYPE · LEVELS · the next release
 *
 * Session type is the trend-or-range lean with its count (daytype.py), which had been on
 * no page since the Futures Overview went. Levels is the day's state against the chart's
 * four, in the Stocks chips' words (lib/outsideDay dayState). What is here is what those
 * cards need that is not a rule of its own elsewhere; the next release's rule is beside
 * `booksOf`, which it reads (lib/futures nextRelease).
 *
 * Pure, so each rule is tested without a page (futCards.test.ts).
 */

export type LevelName = "PDH" | "PDL" | "PMH" | "PML";

/** The chart's own four, as its bars endpoint sends them (ScanBars.levels). */
export interface ChartLevels {
  pdh: number | null;
  pdl: number | null;
  pmh: number | null;
  pml: number | null;
  /** The pre-market range is final: 09:30 has passed for the chart's day. */
  pm_done: boolean;
}

export interface LevelAt {
  key: LevelName;
  price: number;
  /** The level minus the last print: positive above, negative below. */
  dist: number;
}

const NAMES: ReadonlyArray<[LevelName, "pdh" | "pdl" | "pmh" | "pml"]> = [
  ["PDH", "pdh"],
  ["PMH", "pmh"],
  ["PML", "pml"],
  ["PDL", "pdl"],
];

/**
 * The chart's levels with how far the last print is from each, highest first: the
 * Levels card's hover.
 *
 * THE CHART'S OWN FOUR, AND ONLY THOSE (owner, 2026-11-14, of a second set of levels on
 * a chart: "you now have double ups of the levels"). The card reads the levels the chart
 * beside it has just drawn and named, handed up by the chart itself, so "PDH" on the
 * card is the line marked PDH and can be no other price. That makes them the levels of
 * the day the chart's last bar is in: over a weekend Friday's, until the Sunday reopen.
 *
 * Empty with no print or no level at all (a day that has not opened has none).
 */
export function levelsFrom(levels: Pick<ChartLevels, "pdh" | "pdl" | "pmh" | "pml"> | null | undefined, last: number | null | undefined): LevelAt[] {
  if (!levels || typeof last !== "number" || !Number.isFinite(last)) return [];
  const all: LevelAt[] = [];
  for (const [key, field] of NAMES) {
    const price = levels[field];
    if (typeof price === "number" && Number.isFinite(price)) all.push({ key, price, dist: price - last });
  }
  return all.sort((a, b) => b.price - a.price);
}

const COUNTRY: Record<string, string> = {
  "United States": "US",
  "United Kingdom": "UK",
  "Euro Zone": "EZ",
  "Euro Area": "EZ",
  "European Union": "EU",
};

/** "US", "UK", "Japan": the country as a card has room for it. */
export function countryShort(country: string | null | undefined): string {
  if (!country) return "";
  return COUNTRY[country] ?? country;
}
