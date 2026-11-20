import type { ExpiryEvent, ExpiryState } from "@/types/terminal";

/**
 * The options expiry calendar in words (owner, 2026-11-20: "do we also mention when it's
 * opex week? or what day is opex etc?", then "should opex week day be mentioned somewhere
 * in macro?"). The collector keeps the table (server expiry.py): the monthly OpEx, triple
 * witching, month end and quarter end, each with its date and how many days off it is.
 * Until now only the Futures gamma read said "OpEx week", and only that week. Pure.
 */

const EXPIRIES = new Set<ExpiryEvent["kind"]>(["monthly", "quarterly"]);
const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "Fri 18 Dec" from "2026-12-18". */
export function expiryDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : DAY.format(d);
}

/** The next options expiries, OpEx and triple witching only, nearest first. */
export function nextExpiries(e: ExpiryState | null | undefined): ExpiryEvent[] {
  return (e?.next ?? []).filter((x) => EXPIRIES.has(x.kind));
}

/**
 * The game plan's line: the next expiry, and the quarter's triple witching when that is
 * not the next one. "Monthly OpEx today · triple witching Fri 18 Dec"; in OpEx week
 * "Monthly OpEx Fri 20 Nov · in 3d"; further off, the date alone.
 */
export function expiryLine(e: ExpiryState | null | undefined): string | null {
  const next = nextExpiries(e);
  const first = next[0];
  if (!first) return null;
  const when = first.is_today ? "today" : first.days <= 6 ? `${expiryDay(first.date)} · in ${first.days}d` : expiryDay(first.date);
  const head = `${first.label} ${when}`;
  const witching = first.kind === "quarterly" ? undefined : next.find((x) => x.kind === "quarterly");
  return witching ? `${head} · ${witching.label.toLowerCase()} ${expiryDay(witching.date)}` : head;
}

/**
 * The gamma card's tag (owner, 2026-11-20: "we should also mention the opex thing in the
 * gamma level cards of the futures section"): the next expiry, hot on its day and in its
 * week ("OpEx today", "OpEx Fri · 3d"), the date alone otherwise ("OpEx Fri 18 Dec").
 * Triple witching is named as itself.
 */
export function expiryTag(e: ExpiryState | null | undefined): { text: string; hot: boolean; next: ExpiryEvent } | null {
  const first = nextExpiries(e)[0];
  if (!first) return null;
  const name = first.kind === "quarterly" ? "Triple witching" : "OpEx";
  if (first.is_today) return { text: `${name} today`, hot: true, next: first };
  if (first.days <= 6) return { text: `${name} ${expiryDay(first.date).split(" ")[0]} · ${first.days}d`, hot: true, next: first };
  return { text: `${name} ${expiryDay(first.date)}`, hot: false, next: first };
}

/** Each expiry's note, for a hover: "Fri 20 Nov, Monthly OpEx: monthly options expire …". */
export function expiryTitle(events: readonly ExpiryEvent[]): string {
  return events.map((x) => `${expiryDay(x.date)}, ${x.label}: ${x.note}`).join("\n");
}
