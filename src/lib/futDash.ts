import type { BoxRow, DriverBook } from "@/types/terminal";

/**
 * The Dashboard's Futures card (owner, 2026-11-16: "can we update the dashboard to have
 * like a futures card whcih also says what session it is", then "like a bias kind of card
 * and quick brief sumamry etc"; of two mocks, prices, bias and session type, as the top
 * row's fourth card).
 *
 * THE BRIEF IS THE ENGINE'S, NOT A MODEL'S. Two sentences composed from the driver board
 * on each poll: where the five lean, which is strongest and the reads that carry it, and
 * any session-type call. So it is never older than the board and never says a thing the
 * board does not (the written report is the Futures tab's Market Report view).
 *
 * THE SESSION STRIP is the four boxes a futures trader draws (Asia, London, the pre-market,
 * New York), each done, trading now, or still to come in the futures day that began at the
 * 18:00 ET reopen.
 *
 * Pure.
 */

export const DASH_BOOKS = ["NQ", "ES", "GC", "SIL", "CL"] as const;
export type DashBook = (typeof DASH_BOOKS)[number];

/** The word a sentence uses for a book. */
const WORD: Record<DashBook, string> = { NQ: "NQ", ES: "ES", GC: "gold", SIL: "silver", CL: "crude" };

const list = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
// The rows print a score as the bias cards do (lib/bias scoreText): "-54", "+12".
const signedScore = (n: number) => (n > 0 ? `+${n}` : String(n));
/** A read as a clause: "copper -0.89%", and a figure of several parts in brackets. */
const reason = (label: string, value: string) =>
  `${label.toLowerCase()} ${value.includes("·") ? `(${value})` : value}`;

/** What the session weights are, in the sentence: "the New York pre-open". */
export function weightsWord(label: string | undefined): string {
  if (!label) return "this session";
  const m = /^(.*?)'s weight$/.exec(label);
  return m ? m[1] : label.replace(/'s weight$/, "");
}

/**
 * The card's brief: where the five lean, the strongest and what carries it, and any
 * session-type call. `scoreOf` is the whole-weight score the scale draws.
 */
export function futuresBrief(
  books: Partial<Record<DashBook, DriverBook>>,
  leans: Partial<Record<DashBook, { call: string; word: string } | null>>,
  scoreOf: (b: DriverBook) => number,
): string[] {
  const have = DASH_BOOKS.filter((k) => books[k]);
  if (have.length === 0) return ["The driver board has not been read yet."];
  const longs = have.filter((k) => books[k]!.bias === "long");
  const shorts = have.filter((k) => books[k]!.bias === "short");
  const flat = have.filter((k) => !books[k]!.bias);
  const when = weightsWord(books[have[0]]!.weight_label);
  const w = (ks: readonly DashBook[]) => ks.map((k) => WORD[k]);

  let first: string;
  if (longs.length === have.length) first = `All ${have.length === 5 ? "five" : have.length} lean long`;
  else if (shorts.length === have.length) first = `All ${have.length === 5 ? "five" : have.length} lean short`;
  else if (longs.length && shorts.length) first = `Split: ${list(w(longs))} long, ${list(w(shorts))} short`;
  else if (longs.length || shorts.length) {
    const side = longs.length ? "long" : "short";
    const leaning = longs.length ? longs : shorts;
    first = `${cap(list(w(leaning)))} lean${leaning.length === 1 ? "s" : ""} ${side}, ${list(w(flat))} ${flat.length === 1 ? "has" : "have"} no lean`;
  } else first = "No lean on any of the five";
  const out = [`${first} for ${when}.`];

  // The strongest lean, and the two heaviest reads that agree with it.
  const leaning = have.filter((k) => books[k]!.bias);
  if (leaning.length) {
    const top = leaning.reduce((a, b) => (Math.abs(scoreOf(books[b]!)) > Math.abs(scoreOf(books[a]!)) ? b : a));
    const b = books[top]!;
    const weight = new Map(b.families.map((f) => [f.key, f.weight]));
    const why = b.votes
      .filter((v) => v.family && v.live !== false && v.vote === b.bias)
      .sort((x, y) => (weight.get(y.family as string) ?? 0) - (weight.get(x.family as string) ?? 0))
      .slice(0, 2)
      .map((v) => reason(v.label, v.value));
    out.push(`${cap(WORD[top])} is the strongest (${signedScore(scoreOf(b))}, ${b.grade})${why.length ? `: ${list(why)}` : ""}.`);
  }

  // A session-type call is worth a clause; "No lean" and "Mixed record" are not.
  const calls = DASH_BOOKS.filter((k) => leans[k] && (leans[k]!.call === "trend" || leans[k]!.call === "range"));
  if (calls.length) out.push(`${calls.map((k) => `${WORD[k] === "gold" ? "Gold" : WORD[k]}: ${leans[k]!.word.toLowerCase()}`).join("; ")}.`);
  return out;
}

export type BoxState = "done" | "now" | "next";

const mins = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + (m || 0);
};
/** Minutes into the futures day, which begins at the 18:00 ET reopen. */
const intoDay = (m: number) => (m - 18 * 60 + 1440) % 1440;

/** Each of the four boxes as done, trading now, or still to come in today's futures day. */
export function sessionStrip(boxes: readonly BoxRow[], etTime: string): { key: BoxRow["key"]; label: string; state: BoxState; at: string }[] {
  const now = intoDay(mins(etTime));
  return boxes.map((b) => {
    const end = intoDay(mins(b.end_et)) || 1440;
    const state: BoxState = b.open ? "now" : end <= now ? "done" : "next";
    return { key: b.key, label: b.label, state, at: b.open ? b.end_et : b.start_et };
  });
}

/** The next thing the clock does: the soonest box to open or close, an opening first at a tie. */
export function nextEvent(boxes: readonly BoxRow[]): { label: string; next: BoxRow["next"]; min: number } | null {
  let best: BoxRow | null = null;
  for (const b of boxes) {
    if (b.next_min == null || b.next_min < 0) continue;
    if (!best || b.next_min < best.next_min || (b.next_min === best.next_min && b.next === "opens" && best.next === "closes")) best = b;
  }
  return best ? { label: best.label, next: best.next, min: best.next_min } : null;
}
