// node --experimental-strip-types --test src/lib/expiryWords.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { ExpiryEvent, ExpiryState } from "../types/terminal.ts";
import { expiryDay, expiryLine, expiryTag, expiryTitle, nextExpiries } from "./expiryWords.ts";

const ev = (date: string, kind: ExpiryEvent["kind"], label: string, days: number): ExpiryEvent => ({
  key: `${kind}-${date}`, date, kind, label, note: `${label} note`, days, is_today: days === 0,
});
const state = (next: ExpiryEvent[]): ExpiryState => ({
  today: "2026-11-20", opex_week: true, monthly_expiry: "2026-11-20", days_to_opex: 0, next, note: null,
});
// The collector's table on Fri 20 Nov 2026.
const FRI = [
  ev("2026-11-20", "monthly", "Monthly OpEx", 0),
  ev("2026-11-30", "month-end", "Month end", 10),
  ev("2026-12-18", "quarterly", "Triple witching", 28),
];

test("on the day: today, and the quarter's witching after it", () => {
  assert.equal(expiryLine(state(FRI)), "Monthly OpEx today · triple witching Fri 18 Dec");
});

test("in OpEx week the day and the count; further off the date alone", () => {
  const tue = [ev("2026-11-20", "monthly", "Monthly OpEx", 3), ...FRI.slice(1)];
  assert.equal(expiryLine(state(tue)), "Monthly OpEx Fri 20 Nov · in 3d · triple witching Fri 18 Dec");
  const far = [ev("2027-01-15", "monthly", "Monthly OpEx", 20), ev("2027-03-19", "quarterly", "Triple witching", 83)];
  assert.equal(expiryLine(state(far)), "Monthly OpEx Fri 15 Jan · triple witching Fri 19 Mar");
});

test("triple witching next is said once; month end is not an expiry", () => {
  const dec = [ev("2026-11-30", "month-end", "Month end", 3), ev("2026-12-18", "quarterly", "Triple witching", 21)];
  assert.equal(expiryLine(state(dec)), "Triple witching Fri 18 Dec");
  assert.deepEqual(nextExpiries(state(dec)).map((x) => x.kind), ["quarterly"]);
  assert.equal(expiryLine(null), null);
});

test("the gamma card's tag: hot on the day and in the week, the date further off", () => {
  assert.deepEqual(
    [expiryTag(state(FRI))?.text, expiryTag(state(FRI))?.hot],
    ["OpEx today", true],
  );
  const tue = [ev("2026-11-20", "monthly", "Monthly OpEx", 3)];
  assert.equal(expiryTag(state(tue))?.text, "OpEx Fri · 3d");
  const witch = [ev("2026-12-18", "quarterly", "Triple witching", 2)];
  assert.equal(expiryTag(state(witch))?.text, "Triple witching Fri · 2d");
  const far = [ev("2027-01-15", "monthly", "Monthly OpEx", 20)];
  assert.deepEqual([expiryTag(state(far))?.text, expiryTag(state(far))?.hot], ["OpEx Fri 15 Jan", false]);
  assert.equal(expiryTag(null), null);
});

test("the hover carries each note with its day", () => {
  assert.equal(expiryDay("2026-12-18"), "Fri 18 Dec");
  assert.equal(expiryTitle(FRI.slice(0, 1)), "Fri 20 Nov, Monthly OpEx: Monthly OpEx note");
});
