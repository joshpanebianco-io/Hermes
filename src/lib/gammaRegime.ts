/**
 * How a dealer-gamma regime is drawn: in ink, never in a side's colour.
 *
 * WHY (owner, 2026-11-12: "gamma levels incorrect bias - positive doesnt mean bullish and
 * vice versa"). "Positive gamma" was printed in the call side's green and "negative
 * gamma" in the put side's pink on eight surfaces: the brief's gamma card, the Futures
 * overview and each book's stat row, the Gamma panel's pill, its click-through, the
 * driver strip, the Index view's ETF rows and the game plan's regime cell. On this
 * terminal green and pink mean a side and nothing else, so every one of them said
 * positive gamma is bullish. It is not a side. Above the flip dealers hedge against a
 * move and it is damped; below it they hedge with a move and it is amplified; either
 * way, up or down. The engine stopped counting it as a vote the same day (server
 * bias.BOARD_FAMILY). The walls keep their hues: a call wall and a put wall are levels
 * on a side of price, which is what those colours are for.
 */

/** The class for the regime's word, whichever regime it is. */
export const REGIME_INK = "text-ink-2";

/** What the regime ("POS" or "NEG") does to a move, in two words; empty when there is none to read. */
export function regimeMeans(r: string | null | undefined): string {
  return r === "POS" ? "moves damped" : r === "NEG" ? "moves amplified" : "";
}
