// node --experimental-strip-types --test src/lib/earningsOrder.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { aheadFirst, nearestFirst } from "./earningsOrder.ts";

const order = (dates: string[], today: string) =>
  nearestFirst(dates.map((d) => [d, null] as const), today).map(([d]) => d);

test("today, then the days either side of it, with December at the bottom", () => {
  const dates = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-12-16"];
  assert.deepEqual(order(dates, "2026-11-05"), [
    "2026-11-05", // today
    "2026-11-04", // yesterday wins the tie with tomorrow
    "2026-11-06", // tomorrow
    "2026-11-03", // two days back
    "2026-11-09",
    "2026-11-10",
    "2026-12-16",
  ]);
});

test("the day just gone beats the day ahead at any distance", () => {
  assert.deepEqual(order(["2026-11-07", "2026-11-03"], "2026-11-05"), ["2026-11-03", "2026-11-07"]);
});

test("a month boundary counts as one day", () => {
  assert.deepEqual(order(["2026-12-01", "2026-11-28", "2026-11-30"], "2026-11-30"), ["2026-11-30", "2026-12-01", "2026-11-28"]);
});

test("the order the rows arrive in does not matter", () => {
  const a = order(["2026-11-06", "2026-11-04", "2026-11-05"], "2026-11-05");
  const b = order(["2026-11-05", "2026-11-06", "2026-11-04"], "2026-11-05");
  assert.deepEqual(a, b);
});

test("with no date to measure from, it falls back to date order", () => {
  assert.deepEqual(order(["2026-11-06", "2026-11-04", "2026-11-05"], ""), ["2026-11-04", "2026-11-05", "2026-11-06"]);
});

test("the input is left alone", () => {
  const input = [["2026-11-06", 1], ["2026-11-05", 2]] as const;
  nearestFirst(input, "2026-11-05");
  assert.equal(input[0][0], "2026-11-06");
});

test("after the close what is coming leads, and what has been traded follows, latest first", () => {
  // Fri 13 Nov 2026 in the evening: Thursday's five reports sat above Tuesday's NVDA.
  const dates = ["2026-11-12", "2026-11-13", "2026-11-17", "2026-11-11", "2026-11-19"];
  const after = aheadFirst(dates.map((d) => [d, null] as const), "2026-11-13").map(([d]) => d);
  assert.deepEqual(after, ["2026-11-13", "2026-11-17", "2026-11-19", "2026-11-12", "2026-11-11"]);
  // A weekend has no today: the days ahead, then the days gone.
  const sat = aheadFirst(dates.map((d) => [d, null] as const), "2026-11-14").map(([d]) => d);
  assert.deepEqual(sat, ["2026-11-17", "2026-11-19", "2026-11-13", "2026-11-12", "2026-11-11"]);
  // Before the close the owner's order stands: yesterday above tomorrow.
  assert.deepEqual(order(["2026-11-12", "2026-11-13", "2026-11-17"], "2026-11-13"), ["2026-11-13", "2026-11-12", "2026-11-17"]);
  // No usable today: date order, as nearestFirst falls back to.
  assert.deepEqual(aheadFirst([["2026-11-17", null], ["2026-11-12", null]] as const, "").map(([d]) => d), ["2026-11-12", "2026-11-17"]);
});
