import type { DriverBook, DriverVote } from "@/types/terminal";

/**
 * The driver board as a report's sheet: what the Bias card's pop-up prints (owner,
 * 2026-11-16: "make the pop out card a bit wider and format it more like a professional
 * report", the same day the Market Report page left the navigation and the pop-up became
 * the one place a contract's read is written out).
 *
 * THE REPORT'S WORDS. A factor is named as the market report names it (server
 * report.FACTOR_NAMES and BOOK_FACTOR_NAMES): "Volume profile & structure", "Macro ·
 * rates & dollar", "News & data". Its tag is the report's rule (report.factors_of):
 * Bullish or Bearish by the family's own score, Mixed when it is level with reads both
 * ways, Neutral when nothing leans, Not live yet (Nothing yet for the news) when no read
 * in it can vote at this hour. So the pop-up and a report written from the same board
 * say the same thing about it.
 *
 * WHAT IS NOT A FACTOR. Event risk is the table's last row, as in the report: no side,
 * no weight, it lowers the ceiling. Dealer gamma is not in the table at all (it has not
 * voted since 2026-11-12 and the report leaves it out); it heads Context, with the
 * positioning, the put/call and OpEx: what a move will find, never a vote.
 *
 * Pure: the board in, the rows out.
 */

export type Lean = "bull" | "bear" | "mixed" | "neutral" | "none" | "damp";

export interface SheetRead {
  key: string;
  label: string;
  value: string;
  note: string;
  vote: DriverVote["vote"];
  /** False when it cannot vote at this hour. */
  live: boolean;
}

export interface SheetFactor {
  key: string;
  name: string;
  /** The small line under the name: "rates & dollar". */
  sub: string | null;
  /** The share of the score in this session; null for the event row, 0 for a family weighed at another hour. */
  weight: number | null;
  /** The family's own net read, -100 to +100; null when none of it can vote now. */
  score: number | null;
  lean: Lean;
  tag: string;
  reads: SheetRead[];
}

export interface SheetContext {
  key: string;
  label: string;
  value: string;
  note: string;
}

export interface Sheet {
  /** Heaviest first; a family with no weight this session after those that have one, then events. */
  factors: SheetFactor[];
  context: SheetContext[];
  /** "London", "New York pre-open". */
  session: string;
}

/** family → [name, the line under it]; report.FACTOR_NAMES. */
const NAMES: Record<string, [string, string | null]> = {
  catalysts: ["News & data", null],
  rates: ["Macro", "rates & dollar"],
  risk: ["Risk appetite", null],
  structure: ["Volume profile & structure", null],
  participation: ["Participation", "sectors & leaders"],
};
/** report.BOOK_FACTOR_NAMES. */
const BOOK_NAMES: Record<string, Record<string, [string, string | null]>> = {
  SIL: { rates: ["Macro", "rates, dollar & metals"] },
  CL: { rates: ["Macro", "dollar & products"], risk: ["Demand", "credit & copper"], catalysts: ["Inventories & data", null] },
};

const SESSION: Record<string, string> = {
  asia: "Asia",
  london: "London",
  ny_pre: "New York pre-open",
  ny_live: "New York",
};

/** The session a board is weighed for, as a word; from its label when the key is missing. */
export function sessionName(b: Pick<DriverBook, "weight_label"> & { session_key?: string }): string {
  if (b.session_key && SESSION[b.session_key]) return SESSION[b.session_key];
  const m = /^(.*?)'s weight$/.exec(b.weight_label ?? "");
  return m ? m[1].replace(/^the /, "") : "This session";
}

function readOf(v: DriverVote): SheetRead {
  return { key: v.key, label: v.label, value: v.value, note: v.note, vote: v.vote, live: v.live !== false };
}

/** report.factors_of's tag, on the client's board. */
export function familyTag(key: string, score: number | null, reads: SheetRead[]): { lean: Lean; tag: string } {
  const live = reads.filter((r) => r.live);
  if (live.length === 0 || score == null) return { lean: "none", tag: key === "catalysts" ? "Nothing yet" : "Not live yet" };
  if (score > 0) return { lean: "bull", tag: "Bullish" };
  if (score < 0) return { lean: "bear", tag: "Bearish" };
  const longs = live.some((r) => r.vote === "long");
  const shorts = live.some((r) => r.vote === "short");
  return longs && shorts ? { lean: "mixed", tag: "Mixed" } : { lean: "neutral", tag: "Neutral" };
}

export function sheetOf(b: DriverBook & { session_key?: string }): Sheet {
  const names = { ...NAMES, ...(BOOK_NAMES[b.key] ?? {}) };
  const weighed: SheetFactor[] = [];
  const idle: SheetFactor[] = [];
  for (const f of b.families) {
    const reads = b.votes.filter((v) => v.family === f.key).map(readOf);
    if (reads.length === 0) continue;
    const [name, sub] = names[f.key] ?? [f.label, null];
    const row: SheetFactor = { key: f.key, name, sub, weight: f.weight, score: f.score, reads, ...familyTag(f.key, f.score, reads) };
    if (f.weight > 0) weighed.push(row);
    else idle.push({ ...row, lean: "none", tag: "Not weighed now" });
  }
  weighed.sort((x, y) => (y.weight ?? 0) - (x.weight ?? 0));

  const loose = b.votes.filter((v) => !v.family);
  const ev = loose.find((v) => v.key === "event_risk");
  const factors = [...weighed, ...idle];
  if (ev) {
    const n = Number.parseInt(ev.value, 10) || 0;
    factors.push({
      key: "event",
      name: "Geopolitics & events",
      sub: "lowers conviction, not a side",
      weight: null,
      score: null,
      lean: n ? "damp" : "neutral",
      tag: n ? `${n} stor${n === 1 ? "y" : "ies"}` : "Quiet",
      reads: [{ ...readOf(ev), label: "Since the close", live: true }],
    });
  }
  const gamma = loose.filter((v) => v.key !== "event_risk");
  const context: SheetContext[] = [
    ...gamma.map((v) => ({ key: v.key, label: v.label, value: v.value, note: v.note })),
    ...b.context.map((c) => ({ key: c.key, label: c.label, value: c.value, note: c.note })),
  ];
  return { factors, context, session: sessionName(b) };
}
