/**
 * An outside day: a name through BOTH of its ranges the same way.
 *
 * THE OWNER'S RULE (2026-11-13, at the open: "i think the app has some logic wrong. an
 * outside day should be either above both premarket high and previous day high or
 * previous day low and pre market low"). The chip called "Outside day" tested the
 * previous day's range alone, so a name over PDH and still under its pre-market high
 * was listed as an outside day; the rule the owner means was on a second chip, "Both
 * ranges". There is one name for it now, on every page: above the pre-market high AND
 * the previous day's high, or below the pre-market low AND the previous day's low. A
 * name through the previous day's level alone is "Through PDH/PDL" and nothing more.
 *
 * BEFORE 09:30 THE PRE-MARKET RANGE CANNOT BE BROKEN: it is still forming, and its high
 * is whatever the pre-market has printed so far, so no last trade is above it. Until it
 * is set, the previous day's level is the only one there is, and a name beyond it is
 * read as outside. That is the rule the wide scan already goes by (universe.py's
 * `both`), and this is its twin for the rows the engine sends (the Setups table), so
 * the two pages agree at every hour. A name with no pre-market range at all (it did not
 * trade before the bell) has only one range to be through, and is not an outside day.
 *
 * Pure, so it can be tested without a page (outsideDay.test.ts).
 */
/** What the two chips say on hover, the same words on every page that has them. */
export const OUTSIDE_DAY_TITLE =
  "Above both the pre-market high and the previous day's high, or below both lows. Before 09:30 the pre-market range is still forming, so the previous day's level alone decides.";
export const THROUGH_DAY_TITLE = "Through the previous day's high or low, whatever the pre-market range says";

export interface OutsideLevels {
  pdh: number | null;
  pdl: number | null;
  pmh: number | null;
  pml: number | null;
  /** The pre-market range is final: 09:30 has passed for this session. */
  pm_done: boolean;
}

/** Which way the name is an outside day, or null when it is not one. */
export function outsideDay(last: number | null, lv: OutsideLevels): "up" | "down" | null {
  if (last == null) return null;
  const overDay = lv.pdh != null && last > lv.pdh;
  const underDay = lv.pdl != null && last < lv.pdl;
  if (!lv.pm_done) return overDay ? "up" : underDay ? "down" : null;
  if (overDay && lv.pmh != null && last > lv.pmh) return "up";
  if (underDay && lv.pml != null && last < lv.pml) return "down";
  return null;
}

/** Through the previous day's high or low, whatever the pre-market range says. */
export function throughDay(last: number | null, lv: Pick<OutsideLevels, "pdh" | "pdl">): boolean {
  return last != null && lv.pdh != null && lv.pdl != null && (last > lv.pdh || last < lv.pdl);
}
