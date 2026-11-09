import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeTick, nextEma, type LiveBar } from "./chartLive.ts";

// On the ten-minute grid.
const T = 1794238800;
const bar: LiveBar = { t: T, o: 100, h: 101, l: 99, c: 100.5, v: 1000 };

test("a trade inside the bar moves its close and stretches its range", () => {
  const got = mergeTick(bar, { price: 102, at: T + 95 }, 600);
  assert.deepEqual(got, { bar: { t: T, o: 100, h: 102, l: 99, c: 102, v: 1000 }, isNew: false });
});

test("a trade inside the range only moves the close", () => {
  const got = mergeTick(bar, { price: 100, at: T + 95 }, 600);
  assert.equal(got?.bar.h, 101);
  assert.equal(got?.bar.l, 99);
  assert.equal(got?.bar.c, 100);
});

test("the minute's candle carries the high and low between polls", () => {
  const got = mergeTick(bar, { price: 100, at: T + 95, minute: { t: T + 60, o: 100, h: 103, l: 98, c: 100 } }, 600);
  assert.equal(got?.bar.h, 103);
  assert.equal(got?.bar.l, 98);
});

test("a trade past the bar opens the next one on the grid", () => {
  const got = mergeTick(bar, { price: 104, at: T + 601 }, 600);
  assert.deepEqual(got, { bar: { t: T + 600, o: 104, h: 104, l: 104, c: 104, v: 0 }, isNew: true });
});

test("the old minute does not stretch a new bar", () => {
  const got = mergeTick(bar, { price: 104, at: T + 601, minute: { t: T + 540, o: 90, h: 120, l: 80, c: 104 } }, 600);
  assert.equal(got?.bar.h, 104);
  assert.equal(got?.bar.l, 104);
  assert.equal(got?.bar.o, 104);
});

test("a trade older than the newest bar changes nothing", () => {
  assert.equal(mergeTick(bar, { price: 104, at: T - 1 }, 600), null);
});

test("with no bars at all the trade is the first", () => {
  assert.equal(mergeTick(null, { price: 5, at: T + 5 }, 60)?.isNew, true);
});

test("an ema steps by 2/(n+1) of the distance", () => {
  assert.equal(nextEma(100, 109, 8), 102);
});
