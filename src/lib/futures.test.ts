// node --experimental-strip-types --test src/lib/futures.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { FUT_VIEW_KEYS, booksOf, isFutBook } from "./futures.ts";

test("the views are the overview, each book in order, then the brief", () => {
  assert.deepEqual(FUT_VIEW_KEYS, ["overview", "NQ", "ES", "GC", "SIL", "CL", "brief"]);
  assert.ok(isFutBook("SIL") && !isFutBook("overview"));
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
