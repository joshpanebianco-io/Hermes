/**
 * Multicharts: which names the Scanner's six charts show (owner, 2026-11-12: "have a
 * option next to the filter bar called multicharts which displays multiple charts from
 * the top 10 ... maybe start with 6 - lay it out so its 3 columns 2 rows etc and then have
 * the options to change what is displayed in those 6 charts from the top 10").
 *
 * THE TEN ARE THE TEN HIGHEST SCORES ON THE WHOLE LIST (`topScores`), long and short
 * together. They were the first ten of whichever chip was lit, so "Long" gave the ten
 * best longs; the owner then asked for Multicharts to "funciton like the pill bar it's
 * next too - eg not both things can be selected at the same time" (2026-11-12), and
 * the day after for it to be a view of its own, the tab after Game plan. The chips are
 * the Setups view's, so no chip is choosing the charts' list.
 *
 * A CHART KEEPS ITS NAME. The rank moves every five seconds in the session, and six
 * charts that followed it would trade places under the reader all morning. So a name
 * holds its chart until the reader changes it or it leaves the ten, and then the best
 * name not on screen takes that chart, and stays there if the old one comes back. What
 * is held is written down as it changes (`HeldSlots`), which is what makes that stick.
 *
 * A NEW LIST STARTS FROM THE TOP. The held names carry the list they were picked from
 * (the trading day); for another day they do not apply and the six are its first six,
 * in order.
 *
 * Pure, so it can be tested without a page (multiChart.test.ts).
 */

/** How many charts the page draws: three columns, two rows. */
export const CHART_SLOTS = 6;
/** How many names they are drawn from, and what the "Top 10" chip keeps. */
export const TOP_N = 10;

/** The six charts' names, and the list they were chosen from. */
export interface HeldSlots {
  key: string;
  slots: string[];
}

export const NO_HELD: HeldSlots = { key: "", slots: [] };

export function isHeldSlots(v: unknown): v is HeldSlots {
  if (typeof v !== "object" || v === null) return false;
  const o = v as { key?: unknown; slots?: unknown };
  return (
    typeof o.key === "string" &&
    Array.isArray(o.slots) &&
    o.slots.length <= 24 &&
    o.slots.every((s) => typeof s === "string" && s.length > 0 && s.length <= 12)
  );
}

/**
 * The names with the highest scores, best first; names that tie keep the order they
 * came in (the engine's). A name that could not be read has no score to rank.
 *
 * THE ENGINE'S RANK WHERE IT SENDS ONE (quant audit, 2026-11-13). The list is ranked on
 * the uncapped score, so a penalty counts at the top where two names both read 100, and
 * a name trading under its usual volume is kept out of the ten (scanscore.rvol_gate).
 * Sorting the capped total again here undid both, so `score.rank` decides when every
 * row carries it; an older collector's rows fall back to the total.
 */
export function topScores(
  rows: ReadonlyArray<{ sym: string; ok: boolean; score: { total: number; rank?: number } }>,
  n = TOP_N,
): string[] {
  const ok = rows.filter((r) => r.ok);
  const ranked = ok.length > 0 && ok.every((r) => typeof r.score.rank === "number");
  return ok
    .map((r, i) => ({ r, i }))
    .sort((a, b) =>
      ranked
        ? (a.r.score.rank as number) - (b.r.score.rank as number)
        : b.r.score.total - a.r.score.total || a.i - b.i,
    )
    .slice(0, n)
    .map((x) => x.r.sym);
}

/**
 * What each chart shows: the held name where it is still one of `pool`, and where it is
 * not (or nothing is held) the best names not already on a chart, in the pool's order.
 * Fewer names than charts gives fewer charts.
 */
export function fillSlots(held: readonly string[], pool: readonly string[], n = CHART_SLOTS): string[] {
  const want = Math.min(n, pool.length);
  const inPool = new Set(pool);
  const used = new Set<string>();
  const kept: Array<string | null> = [];
  for (let i = 0; i < want; i++) {
    const s = held[i];
    if (s && inPool.has(s) && !used.has(s)) {
      kept.push(s);
      used.add(s);
    } else {
      kept.push(null);
    }
  }
  const rest = pool.filter((s) => !used.has(s));
  let next = 0;
  return kept.map((s) => s ?? rest[next++]);
}

/** Put a name on chart `i`. A name already on another chart trades places with this one. */
export function placeIn(slots: readonly string[], i: number, sym: string): string[] {
  const out = [...slots];
  if (i < 0 || i >= out.length || out[i] === sym) return out;
  const was = out.indexOf(sym);
  if (was >= 0) out[was] = out[i];
  out[i] = sym;
  return out;
}

export function sameSlots(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((s, i) => s === b[i]);
}
