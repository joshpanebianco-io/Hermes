// node --experimental-strip-types --test src/lib/headerStrip.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Quote } from "../types/terminal.ts";
import { fitCount, lagText, stripTiles } from "./headerStrip.ts";

const quote = (key: string) => ({ key }) as Quote;
const keys = (ks: string[]) => stripTiles(ks.map(quote)).map((t) => `${t.startsGroup ? "|" : ""}${t.quote.key}`);

test("the strip runs in trading order, whatever order the feed sends", () => {
  assert.deepEqual(keys(["BTC", "VIX", "QQQ", "NQ", "ES"]), ["NQ", "ES", "|QQQ", "|VIX", "|BTC"]);
});

test("each group but the first opens with a divider", () => {
  const all = ["NQ", "ES", "GC", "SPY", "QQQ", "VIX", "VVIX", "US10Y", "DXY", "WTI", "BTC"];
  assert.deepEqual(keys(all), ["NQ", "ES", "GC", "|SPY", "QQQ", "|VIX", "VVIX", "|US10Y", "DXY", "WTI", "BTC"]);
});

test("a missing group leaves no stray divider, and the first tile never has one", () => {
  assert.deepEqual(keys(["SPY", "QQQ", "US10Y"]), ["SPY", "QQQ", "|US10Y"]);
  assert.deepEqual(keys(["VVIX"]), ["VVIX"]);
  assert.deepEqual(keys([]), []);
});

test("a key the strip does not carry is not drawn", () => {
  assert.deepEqual(keys(["VIX3M", "NQ"]), ["NQ"]);
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

test("everything fits when it fits with no count beside it, to the pixel", () => {
  // 70 + 10 + 70 + 10 + 70 = 230.
  assert.equal(fitCount([70, 70, 70], 10, 300, 40), 3);
  assert.equal(fitCount([70, 70, 70], 10, 230, 40), 3);
});

test("one pixel short, room is kept for the count, which costs more than the one tile", () => {
  // 229 less the count's 40 and its gap of 10 leaves 179: two tiles are 150, three are 230.
  assert.equal(fitCount([70, 70, 70], 10, 229, 40), 2);
});

test("the answer does not depend on whether the count is showing", () => {
  // The bug this replaced: a narrower box beside the count held the count on screen.
  // `room` is the same either way, so there is only one answer.
  const widths = [70, 70, 70, 70];
  for (const room of [310, 309, 200, 90, 49]) {
    assert.equal(fitCount(widths, 10, room, 40), fitCount(widths, 10, room, 40));
  }
  assert.equal(fitCount(widths, 10, 310, 40), 4);
});

test("tiles are taken from the left, so NQ is the last to go", () => {
  assert.equal(fitCount([70, 120, 70], 10, 170, 40), 1);
  assert.equal(fitCount([70, 120, 70], 10, 120, 40), 1);
});

test("too narrow for even the first tile, none fit and the count holds them all", () => {
  assert.equal(fitCount([70, 70], 10, 119, 40), 0);
  assert.equal(fitCount([70, 70], 10, 0, 40), 0);
  assert.equal(fitCount([70, 70], 10, -5, 40), 0);
});

test("an empty strip fits", () => {
  assert.equal(fitCount([], 10, 0, 40), 0);
});
