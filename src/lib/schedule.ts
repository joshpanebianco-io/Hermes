/**
 * One schedule: the Fed's diary and the Treasury's auctions as calendar rows.
 *
 * THE FED & TREASURY CARD WAS A SCREEN BELOW THE FOLD AND HALF A COPY (owner,
 * 2026-11-14, of a review of the Macro cards: "do what you recommend"). It sat under
 * the macro board, 1,000px down on a 1440 screen, and its speakers were already rows
 * of the calendar above it under other names ("FOMC Member Barr Speaks" for
 * "Governor Michael S. Barr"). What the calendar did not have was the rest of that
 * diary: the minutes, the Beige Book, a decision, the coupon auctions. Those become
 * rows here, so the calendar is the one list of what is scheduled and the card is
 * gone from the page.
 *
 * SPEECHES ARE NOT ADDED HERE. Nasdaq's calendar lists them itself, and when
 * TradingView's stands in the collector adds the Board's (calendar.fed_speech_rows).
 * Either way they are already rows; adding them again would list a speaker twice.
 *
 * ONLY WHAT THE CALENDAR DOES NOT ALREADY LIST. Both feeds usually carry the minutes
 * and the auctions under their own names. A diary row is left out when a US calendar
 * row within six hours of it names the same thing.
 *
 * IN THE BROWSER, NOT THE COLLECTOR, on purpose: the collector's `calendar` rows are
 * read by the brief, the bias engine, Hermes and the Futures cards, and the brief
 * already lists the diary and the auctions from their own sources, so rows added
 * there would be listed twice. Pure.
 */

import type { AuctionEvent, CalendarRow, FedEvent } from "@/types/terminal";

/** A diary row and a calendar row this close together, naming the same thing, are one event. */
const SAME_EVENT_SEC = 6 * 3600;

/**
 * The calendar's own scale (0 to 5; 4 and up is the High tier, 3 the Medium), and the
 * score the collector gives the same name when a feed lists it (calendar.score): a
 * decision and its minutes are five, the Beige Book three.
 */
function fedScore(e: FedEvent): number {
  return e.kind === "Beige Book" ? 3 : 5;
}

type NameTest = (event: string) => boolean;

/** What a calendar row would call this diary row, as a test on its name. */
function fedTwin(e: FedEvent): NameTest {
  if (e.kind === "Beige Book") return (s) => /beige/i.test(s);
  if (/minutes/i.test(e.title)) return (s) => /minutes/i.test(s);
  // A decision: the statement, the rate, the projections, the press conference. Not a
  // member speaking that day, and not the minutes of the meeting before.
  return (s) => /fomc|fed(?:eral)? (?:funds|interest)|rate decision/i.test(s) && !/speaks|testif|minutes/i.test(s);
}

/** "10Y" → a test for "10-Year Note Auction", "10 Yr", "10Y". */
function auctionTwin(a: AuctionEvent): NameTest | null {
  const n = /(\d+)/.exec(a.term)?.[1];
  if (!n) return null;
  const term = new RegExp(`\\b${n}\\s*-?\\s*(?:year|yr|y)\\b`, "i");
  return (s) => /auction/i.test(s) && term.test(s);
}

function row(p: Pick<CalendarRow, "event" | "date" | "et" | "utc" | "ts" | "score" | "note">): CalendarRow {
  return {
    ...p,
    country: "United States",
    region: "us",
    session: null,
    themes: ["rates"],
    core: true,
    actual: null,
    actual_raw: null,
    consensus: null,
    consensus_raw: null,
    previous: null,
    previous_raw: null,
    surprise: null,
    released: false,
  };
}

/**
 * The diary's decisions, minutes and Beige Books and the Treasury's coupon auctions,
 * as calendar rows, less the ones `have` already lists. Timed rows only: a row with no
 * time cannot be placed in a list ordered by the clock.
 */
export function diaryRows(
  fed: readonly FedEvent[],
  auctions: readonly AuctionEvent[],
  have: readonly CalendarRow[],
): CalendarRow[] {
  const us = have.filter((r) => r.region === "us" && r.ts != null);
  const listed = (ts: number, name: NameTest | null) =>
    name !== null && us.some((r) => Math.abs((r.ts as number) - ts) <= SAME_EVENT_SEC && name(r.event));

  const out: CalendarRow[] = [];
  for (const e of fed) {
    if ((e.kind !== "FOMC" && e.kind !== "Beige Book") || e.ts == null) continue;
    if (listed(e.ts, fedTwin(e))) continue;
    out.push(row({ event: e.title, date: e.date, et: e.et, utc: e.utc, ts: e.ts, score: fedScore(e), note: e.note }));
  }
  for (const a of auctions) {
    if (a.ts == null || listed(a.ts, auctionTwin(a))) continue;
    out.push(
      row({
        event: `${a.label} auction${a.amount_bn != null ? ` · $${a.amount_bn}bn` : ""}${a.reopening ? " · reopening" : ""}`,
        date: a.date,
        et: a.et,
        utc: a.utc,
        ts: a.ts,
        // The long end reprices equities when it tails; the rest is context.
        score: a.major ? 3 : 2,
        note: "Coupon supply. Competitive bids close 13:00 ET; the result a minute later reprices the long end.",
      }),
    );
  }
  return out;
}

/** The calendar's rows with the diary's and the auctions' added, in time order. */
export function oneSchedule(
  rows: readonly CalendarRow[],
  fed: readonly FedEvent[],
  auctions: readonly AuctionEvent[],
): CalendarRow[] {
  const extra = diaryRows(fed, auctions, rows);
  if (extra.length === 0) return rows as CalendarRow[];
  return [...rows, ...extra].sort((a, b) => (a.ts ?? Infinity) - (b.ts ?? Infinity));
}

/**
 * The impact tiers as switches where LIT IS WHAT YOU SEE (2026-11-14). The Wire and
 * the Calendar each had an "All" chip beside High, Med and Low, and each also had a
 * second "All" on the row beneath (every desk, every region), so one card showed
 * "All 254" unlit next to "All 101" lit. The tier "All" is gone: the three tiers are
 * three switches, every one lit is the whole list, and the last one cannot be put
 * out (it lights all three instead of showing nothing).
 *
 * Stored as before: an empty list is the whole list, so a browser that remembers the
 * old "All" opens with all three lit.
 */
export function toggleTier<T extends string>(lit: readonly T[], k: T, all: readonly T[]): T[] {
  const on = lit.length ? lit : all;
  const next = on.includes(k) ? on.filter((x) => x !== k) : [...on, k];
  return next.length === 0 || next.length === all.length ? [] : all.filter((x) => next.includes(x));
}

/** Whether a tier's chip is lit: every one is when none is stored. */
export function tierLit<T extends string>(lit: readonly T[], k: T): boolean {
  return lit.length === 0 || lit.includes(k);
}
