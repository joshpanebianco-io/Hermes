import assert from "node:assert/strict";
import { test } from "node:test";
import { GAMMA_LABEL_GAP, GAMMA_LABEL_HALF, gammaPrice, layoutGamma, type GammaLevels } from "./gammaMap.ts";

// The Nasdaq future at Friday 20 Nov 2026's close: through two of its put walls, 1,664 under
// the flip, inside the day's expected move.
const NQ: GammaLevels = { last: 25126, flip: 26790, puts: [25955, 25749, 24719], calls: [], em: [24284, 26298] };
// SPY that evening, the S&P future's levels in its prices: no expected move of its own.
const SPY: GammaLevels = { last: 697.49, flip: 721.04, puts: [699.46, 694.48, 689.51], calls: [], em: null };

test("every level sits in proportion, left to right, with the flip's far side given room", () => {
  const r = layoutGamma(NQ, 518);
  assert.ok(r);
  assert.deepEqual(r.marks.map((m) => m.price), [24719, 25749, 25955, 26790]);
  assert.deepEqual(r.marks.map((m) => m.kind), ["put", "put", "put", "flip"]);
  // The flip is the highest level: a fifth of the span is kept beyond it for the other zone.
  const span = 26790 - 24284;
  assert.ok(r.flip !== null);
  assert.equal(Math.round(518 - r.flip), Math.round((span * 0.2 * 518) / (span * 1.27)));
  assert.ok(r.em && r.em[0] > 0 && r.em[0] < r.last && r.last < r.em[1] && r.em[1] < r.flip);
});

test("two walls too close to print side by side take two rows, and never overlap in one", () => {
  const r = layoutGamma(NQ, 518);
  assert.ok(r);
  assert.equal(r.lanes, 2);
  const at = (p: number) => r.marks.find((m) => m.price === p);
  assert.equal(at(25749)?.lane, 0);
  assert.equal(at(25955)?.lane, 1);
  for (let lane = 0; lane < r.lanes; lane++) {
    const row = r.marks.filter((m) => m.lane === lane);
    for (let i = 1; i < row.length; i++) {
      assert.ok(row[i].x - GAMMA_LABEL_HALF > row[i - 1].x + GAMMA_LABEL_HALF + GAMMA_LABEL_GAP);
    }
  }
  // With room to spare they are one row.
  assert.equal(layoutGamma(NQ, 2400)?.lanes, 1);
});

test("a fund has no expected move, and its price is placed among its walls", () => {
  const r = layoutGamma(SPY, 518);
  assert.ok(r);
  assert.equal(r.em, null);
  const xs = r.marks.map((m) => m.x);
  assert.ok(xs[1] < r.last && r.last < xs[2]); // 694.48 < 697.49 < 699.46
});

test("a price above the flip keeps the room on the flip's low side", () => {
  const r = layoutGamma({ last: 83.41, flip: 81, puts: [82], calls: [85, 87], em: null }, 500);
  assert.ok(r && r.flip !== null);
  assert.equal(Math.round(r.flip), Math.round((6 * 0.2 * 500) / (6 * 1.27)));
  assert.deepEqual(r.marks.map((m) => m.kind), ["flip", "put", "call", "call"]);
});

test("nothing to draw without a width, and one price alone still has a place", () => {
  assert.equal(layoutGamma(NQ, 0), null);
  const alone = layoutGamma({ last: 100, flip: null, puts: [], calls: [], em: null }, 400);
  assert.ok(alone && alone.marks.length === 0 && alone.flip === null);
  assert.ok(alone.last > 0 && alone.last < 400);
});

test("a level prints to its instrument's decimals, and whole when it is whole", () => {
  assert.equal(gammaPrice(26790, 0), "26,790");
  assert.equal(gammaPrice(721.04, 2), "721.04");
  assert.equal(gammaPrice(3515.4, 1), "3,515.4");
  assert.equal(gammaPrice(42, 3), "42");
  assert.equal(gammaPrice(41.07, 3), "41.070");
});
