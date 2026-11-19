// node --experimental-strip-types --test src/lib/reportSheet.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { groupMovers, moverSection, onTheDay, rotationLines, rotationRead, tradingDay } from "./reportSheet.ts";
import type { BriefRatio } from "../types/terminal.ts";

// The stored rows' own instants (reports 20261117-071345 and 20261115-205905).
const TUE_0713 = Date.parse("2026-11-17T12:13:45Z") / 1000;
const SUN_2059 = Date.parse("2026-11-16T01:59:05Z") / 1000;

test("the trading day rolls at 18:00 ET and over a weekend", () => {
  assert.equal(tradingDay(TUE_0713), "2026-11-17");
  assert.equal(tradingDay(SUN_2059), "2026-11-16"); // Sunday 20:59 ET is Monday's
  assert.equal(tradingDay(1794786600), "2026-11-16"); // Japan's GDP, Sun 18:50 ET
  assert.equal(tradingDay(Date.parse("2026-11-16T22:59:00Z") / 1000), "2026-11-16"); // Mon 17:59 ET
  assert.equal(tradingDay(Date.parse("2026-11-16T23:00:00Z") / 1000), "2026-11-17"); // Mon 18:00 ET
  assert.equal(tradingDay(Date.parse("2026-11-14T15:00:00Z") / 1000), "2026-11-16"); // a Saturday
  assert.equal(tradingDay(Date.parse("2026-11-13T23:30:00Z") / 1000), "2026-11-16"); // Fri 18:30 ET
  assert.equal(tradingDay(null), null);
});

const row = (ts: number, kind: "data" | "fed" | "earnings", country: string | null, lands: "asia" | "london" | "premkt" | "ny" | null) => ({
  ts, kind, country, lands_in_session: lands,
});

test("a New York note's calendar is the day's US events and prints landing in New York", () => {
  const day = "2026-11-17";
  assert.equal(onTheDay(row(1794922200, "data", "United States", "premkt"), day, "ny"), true); // Retail Sales 08:30
  assert.equal(onTheDay(row(1794949500, "earnings", null, null), day, "ny"), true); // NVDA after the close
  assert.equal(onTheDay(row(1794898800, "data", "United Kingdom", "london"), day, "ny"), false); // UK jobs 02:00
  assert.equal(onTheDay(row(1794985200, "data", "United Kingdom", "london"), day, "ny"), false); // tomorrow's UK CPI
  assert.equal(onTheDay(row(1794922200, "data", "Canada", "premkt"), day, "ny"), true);
  assert.equal(onTheDay({ ts: undefined, kind: "fed", country: null, lands_in_session: null }, day, "ny"), false);
});

test("an Asia note keeps the night's own prints and the US day after them", () => {
  const day = "2026-11-16";
  assert.equal(onTheDay(row(1794786600, "data", "Japan", "asia"), day, "asia"), true); // GDP Sun 18:50
  assert.equal(onTheDay(row(1794823200, "data", "United States", "premkt"), day, "asia"), true); // Barr Mon 05:00
  assert.equal(onTheDay(row(1794898800, "data", "United Kingdom", "london"), day, "asia"), false); // Tuesday's
});

const R = (id: string, chg: number | null, d: BriefRatio["dir"]): BriefRatio => ({ id, group: "equity", level: 1, chg_5d: chg, dir: d });
// The ratios of 17 Nov 2026's reports.
const NOV17 = [R("XLK/XLU", -4.3, "down"), R("XLK/SPY", -1.92, "down"), R("XLC/XLP", -2.34, "down"),
  R("QQQ/IWM", 0.82, "up"), R("QQQ/SPY", -0.91, "down"), R("XLP/SPY", 3.64, "up")];

test("the ratios read as lines, one a leading leg", () => {
  assert.deepEqual(rotationLines(NOV17), [
    { lead: "Tech", parts: [{ vs: "Utilities", chg: -4.3 }, { vs: "S&P 500", chg: -1.92 }] },
    { lead: "Comms", parts: [{ vs: "Staples", chg: -2.34 }] },
    { lead: "Nasdaq 100", parts: [{ vs: "Russell 2000", chg: 0.82 }, { vs: "S&P 500", chg: -0.91 }] },
    { lead: "Staples", parts: [{ vs: "S&P 500", chg: 3.64 }] },
  ]);
  assert.deepEqual(rotationLines([R("Gold/Silver", 1.2, "up"), R("GDX/GLD", null, "flat")]), [
    { lead: "Gold", parts: [{ vs: "Silver", chg: 1.2 }] },
  ]);
});

test("defensives or growth leading only when both ratios say so", () => {
  assert.equal(rotationRead(NOV17), "Defensives leading");
  assert.equal(rotationRead([R("XLK/XLU", 2, "up"), R("XLP/SPY", -1.5, "down")]), "Growth leading");
  assert.equal(rotationRead([R("XLK/XLU", -2, "down"), R("XLP/SPY", 0.1, "flat")]), null);
  assert.equal(rotationRead([]), null);
});

// ---- the briefing's list (brief_version 4, 2026-11-19) -----------------------------
const at = (iso: string) => Date.parse(iso) / 1000;
const CATS: Record<string, { kind: "data" | "fed" | "auction" | "earnings" | "holiday"; ts: number; earlier?: boolean }> = {
  c1: { kind: "data", ts: at("2026-11-19T13:30:00Z") },               // Thu 08:30 ET claims
  c2: { kind: "data", ts: at("2026-11-17T13:30:00Z"), earlier: true }, // Tue retail sales
  c3: { kind: "fed", ts: at("2026-11-19T14:10:00Z") },                 // Thu 09:10 speaker
  c4: { kind: "earnings", ts: at("2026-11-18T21:05:00Z") },            // Wed after the close
  c5: { kind: "fed", ts: at("2026-11-18T19:00:00Z") },                 // Wed FOMC, by its day
  c6: { kind: "data", ts: at("2026-11-19T12:00:00Z") },                // Thu 07:00 ET
};

test("an item sits under its kind, and this week's earlier prints under their own", () => {
  const day = "2026-11-19";
  const sec = (id: string, h = false) => moverSection(id, CATS[id], h, day);
  assert.equal(sec("rates"), "rates");
  assert.equal(sec("vix"), "vol");
  assert.equal(sec("positioning"), "vol");
  assert.equal(sec("h4", true), "news");
  assert.equal(sec("c1"), "data");
  assert.equal(sec("c2"), "week");
  assert.equal(sec("c3"), "fed");
  assert.equal(sec("c4"), "earnings"); // last night's results are earnings, not last week
  assert.equal(sec("c5"), "week"); // a Fed decision of an earlier day, unflagged, by its day
  assert.equal(sec("c9"), null); // no such row
});

test("the sections come in one order, a calendar row by its time, the rest as ranked", () => {
  const movers = [{ id: "h4" }, { id: "c1" }, { id: "vix" }, { id: "c6" }, { id: "rates" }, { id: "c2" }, { id: "h2" }];
  const got = groupMovers(movers, (id) => CATS[id], (id) => id.startsWith("h"), "2026-11-19");
  assert.deepEqual(
    got.map((s) => [s.key, s.items.map((m) => m.id)]),
    [
      ["data", ["c6", "c1"]],
      ["week", ["c2"]],
      ["news", ["h4", "h2"]],
      ["rates", ["rates"]],
      ["vol", ["vix"]],
    ],
  );
  assert.equal(got[1].sub, "already in the price");
});
