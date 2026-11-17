import assert from "node:assert/strict";
import { test } from "node:test";
import { DESK_REPORT, assetWord, booksIn, covers, deskOf, subjectFor } from "./reportDesk.ts";

test("Futures picks one of the five books and any session; Stocks the three funds for New York", () => {
  assert.deepEqual(DESK_REPORT.futures.subjects.map((s) => s.key), ["NQ", "ES", "GC", "SIL", "CL"]);
  assert.deepEqual(DESK_REPORT.futures.sessions, ["asia", "london", "ny"]);
  assert.deepEqual(DESK_REPORT.stocks.subjects.map((s) => s.label), ["SPY · QQQ · IWM"]);
  assert.deepEqual(DESK_REPORT.stocks.sessions, ["ny"]);
});

test("an older report is read under every book it carries", () => {
  assert.ok(covers("indexes", "NQ") && covers("indexes", "ES") && !covers("indexes", "GC"));
  assert.ok(covers("all", "GC") && covers(undefined, "NQ"));
  assert.ok(covers("SIL", "SIL") && !covers("SIL", "GC"));
  assert.deepEqual(booksIn("CL"), ["CL"]);
});

test("each desk reads its own reports", () => {
  assert.equal(deskOf("etfs"), "stocks");
  for (const a of ["NQ", "indexes", "all", "CL"] as const) assert.equal(deskOf(a), "futures");
  assert.ok(covers("etfs", "etfs") && !covers("etfs", "NQ") && !covers("indexes", "etfs"));
});

test("a past report opened by hand lights its own book, or keeps the lit one when it carries it", () => {
  assert.equal(subjectFor("GC", "NQ", "futures"), "GC");
  assert.equal(subjectFor("indexes", "ES", "futures"), "ES");
  assert.equal(subjectFor("indexes", "CL", "futures"), "NQ");
  assert.equal(subjectFor("etfs", "etfs", "stocks"), "etfs");
});

test("a Past reports row says what it is about", () => {
  assert.equal(assetWord("etfs"), "SPY · QQQ · IWM");
  assert.equal(assetWord("indexes"), "NQ · ES");
  assert.equal(assetWord("SIL"), "SIL");
});
