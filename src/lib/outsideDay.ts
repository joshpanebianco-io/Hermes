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

/**
 * Where a print stands against its levels, as one state: a futures contract's Levels
 * card (owner, 2026-11-15, of the card that printed the distance to the nearest level:
 * "is there anything mor euseful we can replace day range and nearest levels with?").
 * The distance is on the chart beside the card; what the card can add is the read the
 * Stocks chips already give a name, in the same words:
 *
 *   outside   through both ranges the same way (`outsideDay`)
 *   through   beyond the previous day's high or low, and not an outside day
 *   inside    the whole day so far inside the previous day's range (the Stocks chip
 *             "Inside Day": "today's range so far inside the previous day's")
 *   back      between the previous day's levels now, having traded beyond one of them
 *             earlier in the day: the break did not hold
 *   between   between them, with the day's own high and low not known, so it cannot be
 *             said which of the two above it is
 *
 * A print sitting on a level is not through it, as in `outsideDay`. `day` is the day's
 * own range so far (a future's since its 18:00 reopen). Null with no print or no
 * previous day's range.
 */
export type DayState =
  | { kind: "outside"; dir: "up" | "down" }
  | { kind: "through"; dir: "up" | "down" }
  | { kind: "inside" }
  | { kind: "back"; over: boolean; under: boolean }
  | { kind: "between" };

export function dayState(last: number | null | undefined, lv: OutsideLevels | null | undefined, day?: { high: number | null; low: number | null } | null): DayState | null {
  if (last == null || !Number.isFinite(last) || !lv || lv.pdh == null || lv.pdl == null) return null;
  const out = outsideDay(last, lv);
  if (out) return { kind: "outside", dir: out };
  if (last > lv.pdh) return { kind: "through", dir: "up" };
  if (last < lv.pdl) return { kind: "through", dir: "down" };
  if (day?.high == null || day.low == null) return { kind: "between" };
  const over = day.high > lv.pdh;
  const under = day.low < lv.pdl;
  return over || under ? { kind: "back", over, under } : { kind: "inside" };
}
