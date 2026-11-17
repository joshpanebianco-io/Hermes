/**
 * The bias as a place on a scale (owner, 2026-11-15: "instead of bias saying 6 of 14
 * reads or whatever, why dont we jus have a scale instead which shows how close to the
 * extremes we are or how close to neutral depending how bullish or bearish we are").
 *
 * The score already is one: -100 with every read bearish, +100 with every one bullish,
 * 0 neutral (server bias.py). The cards printed it as a number beside a count of the
 * reads that could vote, and the count is what the eye met.
 *
 * THE PLACE CARRIES HOW MUCH EVIDENCE THERE IS, AND NOTHING ELSE DOES (owner, the same
 * day, of a mark drawn hollow: "i dont understand why the market bias on stocks has a
 * black dot circle biut the one on rfutures is pink and normal?", then "the whole point
 * of implementing the scale was to demonstrate that"). The score was over the reads that
 * could vote, so at a weekend the Stocks tape, two reads of eleven and both the indices'
 * after-hours gap, was -100. The first build drew that mark as a ring with a faint bar
 * and the word "thin", which is a second scale laid over the first one and it explained
 * nothing. The score is over the WHOLE weight now (bias.py): what cannot vote counts as
 * no lean, the same night reads -35, and every card draws the one solid mark. There is
 * no ring, no "thin" and no count on a card; the count is on the hover.
 *
 * Pure, so the arithmetic is tested without a page (biasScale.test.ts).
 */

/** Where a score sits along the scale, 0 (the bearish end) to 100 (the bullish end); null with no score. */
export function scalePos(score: number | null | undefined): number | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  return (Math.max(-100, Math.min(100, score)) + 100) / 2;
}

/**
 * A read's score over the whole of its session's weight, whichever rule scored it.
 *
 * One scored since 2026-11-15 says so (`basis: "whole"`) and is used as it is. One from
 * before (a stored plan, or a collector not yet restarted) was over the live weight
 * alone, with the share of the weight that was live beside it: the two multiplied are
 * the same figure the new rule gives, so an old read draws where a new one would.
 * With no coverage to go by the score is all there is.
 */
export function wholeScore(r: { score?: number | null; coverage?: number | null; basis?: string | null }): number | null {
  if (typeof r.score !== "number" || !Number.isFinite(r.score)) return null;
  if (r.basis === "whole" || typeof r.coverage !== "number" || !Number.isFinite(r.coverage)) return r.score;
  // `|| 0`: a small short rounds to -0, which prints as "0" and is not equal to it.
  return Math.round((r.score * Math.max(0, Math.min(100, r.coverage))) / 100) || 0;
}

/** "Bias -31 on a scale from -100, bearish, to +100, bullish": the scale for a reader who cannot see it. */
export function scaleLabel(score: number | null | undefined): string {
  if (scalePos(score) === null) return "No bias score yet";
  const s = Math.round(Math.max(-100, Math.min(100, score as number)));
  const text = s > 0 ? `+${s}` : String(s);
  return `Bias ${text} on a scale from -100, bearish, to +100, bullish`;
}
