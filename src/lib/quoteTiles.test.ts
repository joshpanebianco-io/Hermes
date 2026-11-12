// node --experimental-strip-types --test src/lib/quoteTiles.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Quote } from "../types/terminal.ts";
import { DASH_GROUPS, SCAN_GROUPS, lagText, quoteGroups, quoteInk } from "./quoteTiles.ts";

const quote = (key: string) => ({ key }) as Quote;
const keys = (ks: string[], groups = DASH_GROUPS) => quoteGroups(ks.map(quote), groups).map((g) => g.map((q) => q.key).join(" "));

test("the Dashboard's row runs in trading order, whatever order the feed sends", () => {
  assert.deepEqual(keys(["VIX", "IWM", "QQQ", "SPY"]), ["SPY QQQ IWM", "VIX"]);
});

test("the Dashboard's row is SPY, QQQ, IWM and VIX, whatever else the feed sends", () => {
  // The futures are the Futures tab's, and the 10-year, the dollar, crude, bitcoin and
  // VVIX are on Macro's board: the feed still sends them and this row leaves them out.
  const all = ["NQ", "ES", "GC", "SPY", "QQQ", "IWM", "VIX", "VVIX", "US10Y", "DXY", "WTI", "BTC"];
  assert.deepEqual(keys(all), ["SPY QQQ IWM", "VIX"]);
});

test("a group the feed has none of is left out, not drawn empty", () => {
  assert.deepEqual(keys(["SPY", "QQQ", "US10Y"]), ["SPY QQQ"]);
  assert.deepEqual(keys(["NQ", "US10Y"]), []);
  assert.deepEqual(keys([]), []);
});

test("a key a row does not carry is not drawn", () => {
  assert.deepEqual(keys(["VIX3M", "NQ", "VIX"]), ["VIX"]);
});

test("the Stocks tab's line is the index ETFs, then VIX", () => {
  assert.deepEqual(keys(["VIX", "IWM", "SPY", "QQQ", "NQ"], SCAN_GROUPS), ["SPY QQQ IWM", "VIX"]);
});

test("the lag reads only on a delayed print, rounded", () => {
  assert.equal(lagText({ feed: "delayed", lag_min: 10.4 }), "10m");
  assert.equal(lagText({ feed: "delayed", lag_min: 0 }), "0m");
  assert.equal(lagText({ feed: "delayed", lag_min: null }), null);
  assert.equal(lagText({ feed: "closed", lag_min: 300 }), null);
});

test("a floor leaves out a lag too short to matter, and keeps one at the floor", () => {
  assert.equal(lagText({ feed: "delayed", lag_min: 3 }, 5), null);
  assert.equal(lagText({ feed: "delayed", lag_min: 4.4 }, 5), null);
  assert.equal(lagText({ feed: "delayed", lag_min: 4.6 }, 5), "5m");
  assert.equal(lagText({ feed: "delayed", lag_min: 18 }, 5), "18m");
});

test("a shut or stale market's figure dims", () => {
  assert.equal(quoteInk({ feed: "closed" }), "text-ink-3");
  assert.equal(quoteInk({ feed: "stale" }), "text-ink-3");
  assert.equal(quoteInk({ feed: "delayed" }), "text-ink");
});
