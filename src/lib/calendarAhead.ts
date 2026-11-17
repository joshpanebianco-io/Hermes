/**
 * Which upcoming releases the Macro calendar's Ahead list shows (owner, 2026-11-16: "on
 * macro can we add a bit more of the future things that show up in the calendar? and
 * have a see more if we do want to see more").
 *
 * The card showed today, tomorrow and half of the day after: the rest of the week was
 * below the fold, behind every series of every release in turn. Now the first ET day
 * with a release ahead is shown whole, as before, and each later day by its releases
 * from `FAR_MIN` up (the ones that stop the tape: CPI, payrolls, FOMC, GDP), each one
 * line with its other series on the hover (`folded`), so the fortnight fits the card.
 * "See more" shows every release the filters leave, unfolded. The collector reads two
 * weeks ahead (server calendar.DAYS_AHEAD).
 *
 * Measured at 08:50 ET on 16 Nov 2026 with Mine on: tomorrow on, 24 releases of
 * impact four and up across the fortnight, where the US PCE release alone was thirteen
 * lines unfolded.
 *
 * Pure.
 */

/** Days shown whole, counted from the first day with a release ahead. */
export const FULL_DAYS = 1;
/** Past them, a release is shown from this impact up. */
export const FAR_MIN = 4;

export function aheadShown<T>(
  items: readonly T[],
  dayOf: (x: T) => string,
  scoreOf: (x: T) => number,
  all: boolean,
): {
  shown: T[];
  hidden: number;
  lastDay: string | null;
  /** Nothing of the day was left out (a far day of big releases alone is whole too). */
  whole: (day: string) => boolean;
  /** The day is past the whole ones and the list is trimmed: its releases are one line each. */
  folded: (day: string) => boolean;
} {
  const lastDay = items.length ? dayOf(items[items.length - 1]) : null;
  if (all) return { shown: [...items], hidden: 0, lastDay, whole: () => true, folded: () => false };
  const near = new Set<string>();
  const cut = new Set<string>();
  const shown: T[] = [];
  for (const x of items) {
    const d = dayOf(x);
    if (near.size < FULL_DAYS) near.add(d);
    if (near.has(d) || scoreOf(x) >= FAR_MIN) shown.push(x);
    else cut.add(d);
  }
  return {
    shown,
    hidden: items.length - shown.length,
    lastDay,
    whole: (day) => !cut.has(day),
    folded: (day) => !near.has(day),
  };
}
