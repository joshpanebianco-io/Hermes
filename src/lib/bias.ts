import type { Bias } from "@/types/terminal";

/**
 * A bias as colour and as words, in one place.
 *
 * Shared by the brief, the older note and the Past calls list that shows both,
 * so "leaning bearish" is one hue and one phrase wherever it appears.
 */

/**
 * The hue for a chip or a pip. The leaning states take the DTE shades of the
 * call and put hues: the same direction, visibly less of it.
 */
export function biasHue(b: Bias | string | null | undefined): string {
  if (b === "bullish") return "var(--call)";
  if (b === "leaning bullish") return "var(--call-dte)";
  if (b === "bearish") return "var(--put)";
  if (b === "leaning bearish") return "var(--put-dte)";
  return "var(--ink-3)";
}

/**
 * The hue for a bias set as TEXT — the brief's big "Lean Bear".
 *
 * NOT `biasHue`, because the DTE shades that make a leaning pip read as
 * "less" are too dark to read as type: #8e2a5e on the surface is about 2.5:1.
 * Direction here is carried by the word itself, so both strengths take the
 * full hue, lifted toward white until a serif headline clears contrast.
 */
export function biasInk(b: Bias | string | null | undefined): string {
  if (b === "bullish" || b === "leaning bullish") {
    return "color-mix(in oklab, var(--call) 82%, white)";
  }
  if (b === "bearish" || b === "leaning bearish") {
    return "color-mix(in oklab, var(--put) 70%, white)";
  }
  return "var(--ink-2)";
}

/** The schema's words are for the model; these are for the page. */
export function biasLabel(b: Bias | string | null | undefined): string {
  switch (b) {
    case "bullish":
      return "Bullish";
    case "leaning bullish":
      return "Lean Bull";
    case "neutral":
      return "Neutral";
    case "leaning bearish":
      return "Lean Bear";
    case "bearish":
      return "Bearish";
    default:
      return "—";
  }
}

/** Conviction 1–5 as the word a desk would use for it. */
export function convictionWord(c: number): string {
  if (c >= 4) return "high";
  if (c === 3) return "moderate";
  return "low";
}

/** What the score's three lines read, on the board's book and the tape's count alike. */
export interface ScoreRead {
  score?: number;
  coverage?: number;
  live?: number;
  total: number;
  weight_label?: string;
  families?: { key: string; short: string; weight: number; score: number | null }[];
}

/** +48, -31, 0: the score as the page prints it. */
export function scoreText(score: number): string {
  return score > 0 ? `+${score}` : String(score);
}

/** "8 of 15 reads live · 85% of London's weight": how much of the read there is right now. */
export function liveLine(r: ScoreRead): string {
  return `${r.live ?? 0} of ${r.total} reads live · ${r.coverage ?? 0}% of ${r.weight_label ?? "the weight"}`;
}
