/**
 * When a scheduled event is ahead, due, or done — one rule for every panel.
 *
 * WHY ONE RULE (audit, 2026-10-14). Three panels each decided "next" their
 * own way off the calendar's `released` flag, and the flag only ever flips
 * for a print that publishes an actual. A Fed speaker never does, so the
 * Market tab led with Barkin's 13:00 speech hours after he sat down; the
 * Calendar kept an unreleased row under "Ahead" for an hour and only
 * re-sorted when the feed did; the Scanner said "nothing inside 6h" with CPI
 * nine hours off, which is true and no use at 23:00.
 *
 * THE CLOCK DECIDES, THE FLAG CONFIRMS. Released is done. Otherwise an event
 * is ahead until its time, "due" for a few minutes after it (the actual is on
 * its way — the release is the moment, not the row update), and done after
 * that whether or not an actual ever arrives.
 */

export type EventPhase = "ahead" | "due" | "done";

/** Minutes past its time that an unreleased event still reads as printing now. */
export const DUE_GRACE_MIN = 10;

export interface Timed {
  ts: number | null;
  released: boolean;
}

/** `nowSec` is unix seconds. An untimed row is never "next" — it has no when. */
export function eventPhase(e: Timed, nowSec: number): EventPhase | null {
  if (e.released) return "done";
  if (e.ts === null || !Number.isFinite(e.ts)) return null;
  if (e.ts > nowSec) return "ahead";
  return nowSec - e.ts <= DUE_GRACE_MIN * 60 ? "due" : "done";
}

/** Still to come, or printing right now. */
export function isPending(e: Timed, nowSec: number): boolean {
  const p = eventPhase(e, nowSec);
  return p === "ahead" || p === "due";
}

/** The earliest pending row that passes `keep`, or null. */
export function nextEvent<T extends Timed>(rows: readonly T[], nowSec: number, keep: (r: T) => boolean = () => true): T | null {
  let best: T | null = null;
  for (const r of rows) {
    if (!keep(r) || !isPending(r, nowSec)) continue;
    if (best === null || (r.ts ?? Infinity) < (best.ts ?? Infinity)) best = r;
  }
  return best;
}
