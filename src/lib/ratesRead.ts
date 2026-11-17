/**
 * The Rates & policy card's words.
 *
 * THE FIGURES WERE RIGHT AND THE READER DID THE READING (owner, 2026-11-14: "is the
 * rates and policy card in macro as inutiive and easy to read as it could be"). The
 * card printed "+27bp" and left "that is a full hike" to arithmetic, "Jan 28" for
 * January 2028 over "Dec 09" for the ninth of December, and a date in three styles.
 * What is here turns each figure into the words a desk says it in, in one place, so
 * the card and its click-through cannot say two different things about one number.
 *
 * PURE: no clock, no imports that run. Dates are arithmetic in UTC on the date the
 * collector sent, so the server's render and the browser's are the same string.
 *
 * A PRICED MOVE IS SAID IN QUARTER POINTS. The card was built on never dividing by
 * 25bp, because a probability needs an assumed move size. This is not a probability:
 * "+27bp" and "a full hike" are the same statement in two units, and the second is
 * the one that is read at a glance. The basis points stay beside it.
 */

import type { PolicyMeeting } from "@/types/terminal";

/** One quarter point: the Fed's usual move, and the unit a path is talked about in. */
export const STEP_BP = 25;

/** drivers.YIELD_BP: the 10Y's day change at or beyond which it votes on the driver board. */
export const YIELD_BP = 4;

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** An ISO date as "Wed 9 Dec": the day first, as the clock and the calendar's holidays write it. */
export function dayLabel(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return `${WD[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

/**
 * A date as its source prints it, as ISO: the Treasury's "11/13/2026" (month first)
 * and the New York Fed's "2026-11-12". Null for anything else.
 */
export function isoDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const us = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(raw.trim());
  if (us) return `${us[3]}-${us[1].padStart(2, "0")}-${us[2].padStart(2, "0")}`;
  return /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : null;
}

/** A contract month, "2028-01", as "Jan 2028": never "Jan 28", which reads as a day. */
export function monthLabel(ym: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(ym);
  if (!m) return ym;
  return `${MON[Number(m[2]) - 1] ?? m[2]} ${m[1]}`;
}

/** Whole months from one contract month to another: "2026-11" to "2028-01" is 14. */
export function monthsApart(from: string, to: string): number | null {
  const a = /^(\d{4})-(\d{2})/.exec(from);
  const b = /^(\d{4})-(\d{2})/.exec(to);
  if (!a || !b) return null;
  return (Number(b[1]) - Number(a[1])) * 12 + (Number(b[2]) - Number(a[2]));
}

const PARTS: [number, string][] = [
  [1 / 6, "a sixth of a"],
  [1 / 4, "a quarter of a"],
  [1 / 3, "a third of a"],
  [1 / 2, "half a"],
  [2 / 3, "two thirds of a"],
  [3 / 4, "three quarters of a"],
];

/**
 * A priced move in quarter points: 27bp is "a full hike", 17bp "about two thirds of a
 * hike", -12bp "about half a cut", 86bp "about 3½ hikes". Null at or inside `hold`
 * basis points, where nothing is priced.
 */
export function moveSize(bp: number | null | undefined, hold = 3): string | null {
  if (bp === null || bp === undefined || !Number.isFinite(bp) || Math.abs(bp) <= hold) return null;
  const kind = bp > 0 ? "hike" : "cut";
  const n = Math.abs(bp) / STEP_BP;
  if (n < 0.875) {
    let best = PARTS[0];
    for (const p of PARTS) if (Math.abs(p[0] - n) < Math.abs(best[0] - n)) best = p;
    return `about ${best[1]} ${kind}`;
  }
  const halves = Math.round(n * 2) / 2;
  if (halves <= 1) return `a full ${kind}`;
  const whole = Math.floor(halves);
  return `about ${whole}${halves > whole ? "½" : ""} ${kind}s`;
}

/** What one meeting has priced, in words. The stance is the collector's (policy.HOLD_BAND_BP), so the row and the words agree. */
export function meetingSize(m: Pick<PolicyMeeting, "stance" | "move_bp">): string {
  return m.stance === "hold" ? "a hold" : (moveSize(m.move_bp, 0) ?? "a hold");
}

/** The card's first sentence: "A full hike is priced for Wed 9 Dec." */
export function decisionLine(m: Pick<PolicyMeeting, "stance" | "move_bp" | "date">): string {
  const size = meetingSize(m);
  const verb = size.endsWith("s") ? "are" : "is";
  return `${size[0].toUpperCase()}${size.slice(1)} ${verb} priced for ${dayLabel(m.date)}.`;
}

/** The whole path in words: "about 3½ hikes in 14 months", "nothing priced in 14 months". */
export function pathSize(moveBp: number | null | undefined, months: number | null): string {
  const over = months && months > 0 ? ` in ${months} month${months === 1 ? "" : "s"}` : "";
  const size = moveSize(moveBp);
  return size ? `${size}${over}` : `nothing priced${over}`;
}

/** A day's change as a move, never a side: "↑ 5bp", "↓ 2bp", "unch". Rounds as the figure prints. */
export function moveText(chgBp: number | null | undefined): string {
  if (chgBp === null || chgBp === undefined || !Number.isFinite(chgBp)) return "—";
  const r = Math.round(chgBp);
  if (r === 0) return "unch";
  return `${r > 0 ? "↑" : "↓"} ${Math.abs(r)}bp`;
}

export type Wind = "headwind" | "tailwind";

export interface TenYearRead {
  /** The sentence, up to where the wind word goes (or the whole of it when there is none). */
  text: string;
  /** What the move is for the index books; null inside the band. */
  wind: Wind | null;
}

const bpAbs = (v: number) => `${Math.abs(v).toFixed(Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0)}bp`;

/**
 * The 10Y in a sentence.
 *
 * LIVE WHEN IT CAN BE, THE TREASURY'S CLOSE WHEN IT CANNOT. The yields on the card are
 * the Treasury's daily print, which in the session is yesterday's: a read built on it
 * would say "headwind" at ten o'clock on a morning the 10Y had fallen six. So while
 * the board's 10Y is trading the sentence is the driver board's own vote (`live`,
 * drivers._yields: ±4bp, shut on a bond holiday), and the two cannot disagree. Outside
 * that it is the last close, WITH ITS DAY, so an old move is never read as today's.
 */
export function tenYearRead(a: {
  live: { last: number; chgBp: number; vote: "long" | "short" | "neutral" } | null;
  close: { value: number; chgBp: number | null; day: string | null } | null;
}): TenYearRead | null {
  if (a.live) {
    const { last, chgBp, vote } = a.live;
    const lvl = `${last.toFixed(2)}%`;
    if (vote === "neutral" || Math.abs(chgBp) < YIELD_BP) {
      const how = Math.round(chgBp * 10) === 0 ? "unchanged" : `${chgBp > 0 ? "up" : "down"} ${bpAbs(chgBp)}`;
      return { text: `The 10Y is ${how} today at ${lvl}: inside ±${YIELD_BP}bp, no read from rates.`, wind: null };
    }
    return {
      text: `The 10Y is ${chgBp > 0 ? "up" : "down"} ${bpAbs(chgBp)} today at ${lvl}:`,
      wind: vote === "short" ? "headwind" : "tailwind",
    };
  }
  if (!a.close) return null;
  const { value, chgBp, day } = a.close;
  const lvl = `${value.toFixed(2)}%`;
  const when = day ? ` on ${dayLabel(day)}` : "";
  if (chgBp === null || !Number.isFinite(chgBp)) return { text: `The 10Y closed at ${lvl}${when}.`, wind: null };
  if (Math.abs(chgBp) < YIELD_BP) {
    const how = Math.round(chgBp) === 0 ? "unchanged" : `${chgBp > 0 ? "up" : "down"} ${bpAbs(chgBp)}`;
    return { text: `The 10Y closed ${how} at ${lvl}${when}: inside ±${YIELD_BP}bp, no read from rates.`, wind: null };
  }
  return {
    text: `The 10Y closed ${chgBp > 0 ? "up" : "down"} ${bpAbs(chgBp)} at ${lvl}${when}:`,
    wind: chgBp > 0 ? "headwind" : "tailwind",
  };
}

/** Below this the curve is nearly flat; from `STEEP_BP` it is steep. The long-run 2s10s sits between. */
export const FLAT_BP = 50;
export const STEEP_BP = 100;

export type Slope = "inverted" | "nearly flat" | "moderate" | "steep";

/** The curve's shape from 2s10s in basis points. 27bp is nearly flat, not steep. */
export function slope(spreadBp: number): Slope {
  if (spreadBp < 0) return "inverted";
  if (spreadBp < FLAT_BP) return "nearly flat";
  return spreadBp < STEEP_BP ? "moderate" : "steep";
}

/** How the spread moved on the day, from the two legs' changes: "steeper by 3bp", "flatter by 2bp", "unchanged". */
export function slopeMove(longChgBp: number | null | undefined, shortChgBp: number | null | undefined): string | null {
  if (longChgBp == null || shortChgBp == null || !Number.isFinite(longChgBp) || !Number.isFinite(shortChgBp)) return null;
  const d = Math.round(longChgBp - shortChgBp);
  if (d === 0) return "unchanged";
  return `${d > 0 ? "steeper" : "flatter"} by ${Math.abs(d)}bp`;
}
