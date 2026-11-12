import type { DayCall, DayLabel, DayLean } from "@/types/terminal";

/**
 * Session type — the words the pages share for daytype.py's lean (the Futures
 * Overview and the Dashboard's plan), so they say the same thing. Counts, never
 * probabilities: the server composes the counts (`why`); this only words the label,
 * the night and the hover. The Scanner's strip carried it too for a day (2026-11-10);
 * the owner took it off a stocks page the next.
 */

/** The call's tone: a call is a statement, no lean is quiet. It is not a side. */
export const CALL_HUE: Record<DayCall, string> = { range: "text-ink", trend: "text-ink", mixed: "text-ink-2", none: "text-ink-3" };

/** "trend day up · 1.32 ATR · closed 93% up its range · inside yesterday" */
export function labelWords(l: DayLabel): string {
  const kind = l.type === "trend" ? `trend day${l.dir ? ` ${l.dir}` : ""}` : `${l.type} day`;
  const bits = [kind];
  if (l.range_atr != null) bits.push(`${l.range_atr.toFixed(2)} ATR`);
  if (l.close_pos != null) bits.push(`closed ${Math.round(l.close_pos * 100)}% up its range`);
  if (l.inside) bits.push("inside yesterday");
  return bits.join(" · ");
}

/** "night 0.31 ATR so far · after a range day" */
export function nightWords(ln: DayLean): string {
  const n = ln.night;
  const night = n.atr != null ? `night ${n.atr.toFixed(2)} ATR${n.done === false ? " so far" : ""}` : "night not read yet";
  const p = ln.prev;
  const prev = p.type ? `after a ${p.type === "trend" ? `trend day${p.dir ? ` ${p.dir}` : ""}` : `${p.type} day`}` : "";
  return prev ? `${night} · ${prev}` : night;
}

/** The hover text: the voting conditions, the base rate, and the one rule. */
export function leanTitle(ln: DayLean): string {
  const base = ln.base.n ? `\nevery session: ${ln.base.trend} trend days in ${ln.base.n}, ${ln.base.range} range` : "";
  return `${ln.why}${base}\nCounts over the record, not probabilities.`;
}
