// node --experimental-strip-types --test src/lib/futures.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { FUT_VIEW_KEYS, booksOf, futViewName, isFutBook, nextRelease } from "./futures.ts";

test("the views are each book in order, then the Market Report: no overview and no brief", () => {
  // The Overview went on 2026-11-14 (owner: "lets remove it completely"), the Brief on
  // 2026-11-15, and the written report came back as the view after CL on 2026-11-16.
  assert.deepEqual(FUT_VIEW_KEYS, ["NQ", "ES", "GC", "SIL", "CL", "report"]);
  assert.ok(isFutBook("SIL") && !isFutBook("brief") && !isFutBook("overview") && !isFutBook("report"));
  assert.equal(futViewName("report"), "Market Report");
  assert.equal(futViewName("CL"), "CL · WTI crude");
});

test("a release reaches the books its subject moves", () => {
  assert.deepEqual(booksOf({ event: "Core CPI m/m", themes: ["inflation"], core: true }), ["NQ", "ES", "GC", "SIL"]);
  assert.deepEqual(booksOf({ event: "EIA Crude Oil Inventories", themes: [], core: false }), ["CL"]);
  assert.deepEqual(booksOf({ event: "Retail Sales", themes: ["growth"], core: true }), ["NQ", "ES", "CL"]);
  assert.deepEqual(booksOf({ event: "Dollar index", themes: ["dollar"], core: true }), ["NQ", "ES", "GC", "SIL", "CL"]);
  assert.deepEqual(booksOf({ event: "Speech", themes: [], core: true }), []);
  // A foreign jobs number is a jobs number that reaches none of them.
  assert.deepEqual(booksOf({ event: "French Unemployment Rate", themes: ["jobs"], core: false }), []);
});

// The calendar as it stood on Saturday 14 Nov 2026, 17:54 ET (seconds from then).
const H = 3600;
const row = (event: string, region: string, score: number, themes: string[], core: boolean, inHours: number, released = false) => ({
  event,
  region: region as "us",
  score,
  themes,
  core,
  ts: 1_000_000 + inHours * H,
  released,
});
const WEEK = [
  row("GDP Price Index y/y", "apac", 4, ["inflation", "growth"], true, 23.9), // Japan's
  row("Retail Sales y/y", "apac", 4, ["growth"], true, 26), // China's
  row("FOMC Member Barr Speaks", "us", 3, ["rates"], true, 34),
  row("FOMC Chair Warsh Speaks", "us", 4, ["rates"], true, 41),
  row("Retail Sales m/m", "us", 5, ["growth"], true, 61.5),
  row("API Weekly Crude Oil Stock", "us", 2, ["energy"], false, 69.5),
  row("Crude Oil Inventories", "us", 3, ["energy"], false, 87.5),
];
const NOW = 1_000_000;

test("the next release is America's at 4 or more: not Japan's GDP, not a regional member", () => {
  // The card read "in 23h 57m · GDP Price Index y/y" for NQ that evening.
  assert.equal(nextRelease(WEEK, "NQ", NOW)?.event, "FOMC Chair Warsh Speaks");
  assert.equal(nextRelease(WEEK, "ES", NOW)?.event, "FOMC Chair Warsh Speaks");
  // Rates reach gold and silver through yields.
  assert.equal(nextRelease(WEEK, "GC", NOW)?.event, "FOMC Chair Warsh Speaks");
  assert.equal(nextRelease(WEEK, "SIL", NOW)?.event, "FOMC Chair Warsh Speaks");
});

test("crude reads growth before its own inventories, and its inventories count at 3", () => {
  // A Fed speech is rates, which does not reach crude: retail sales (growth) is its next.
  assert.equal(nextRelease(WEEK, "CL", NOW)?.event, "Retail Sales m/m");
  // With that printed, the weekly inventories: a 3, named for crude. The API's 2 is not.
  const after = WEEK.map((r) => (r.event === "Retail Sales m/m" ? { ...r, released: true } : r));
  assert.equal(nextRelease(after, "CL", NOW)?.event, "Crude Oil Inventories");
  // The inventories are no index's release.
  const only = WEEK.filter((r) => r.event.includes("Crude"));
  assert.equal(nextRelease(only, "NQ", NOW), null);
});

test("a release that has printed or whose minute has passed is not the next", () => {
  const past = WEEK.map((r) => (r.event === "FOMC Chair Warsh Speaks" ? { ...r, ts: NOW - 61 } : r));
  assert.equal(nextRelease(past, "NQ", NOW)?.event, "Retail Sales m/m");
  // Inside the minute it is still shown.
  const due = WEEK.map((r) => (r.event === "FOMC Chair Warsh Speaks" ? { ...r, ts: NOW - 30 } : r));
  assert.equal(nextRelease(due, "NQ", NOW)?.event, "FOMC Chair Warsh Speaks");
  assert.equal(nextRelease([], "NQ", NOW), null);
});

test("two at the same minute: the higher score is the one named", () => {
  const two = [row("ADP Employment Change", "us", 4, ["jobs"], true, 5), row("Core CPI m/m", "us", 5, ["inflation"], true, 5)];
  assert.equal(nextRelease(two, "NQ", NOW)?.event, "Core CPI m/m");
  assert.equal(nextRelease([...two].reverse(), "NQ", NOW)?.event, "Core CPI m/m");
});

test("two at the same minute and score: the headline, which is the shorter name", () => {
  // Tuesday 17 Nov 2026, 08:30: the feed lists the ex-autos series first.
  const sales = [row("Retail Sales Ex Autos m/m", "us", 5, ["growth"], true, 61.5), row("Retail Sales m/m", "us", 5, ["growth"], true, 61.5)];
  assert.equal(nextRelease(sales, "CL", NOW)?.event, "Retail Sales m/m");
  assert.equal(nextRelease([...sales].reverse(), "CL", NOW)?.event, "Retail Sales m/m");
});
