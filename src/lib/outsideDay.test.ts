// node --experimental-strip-types --test src/lib/outsideDay.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { outsideDay, throughDay } from "./outsideDay.ts";

// Yesterday 95 to 100, this morning's pre-market 98 to 103, both set.
const SET = { pdh: 100, pdl: 95, pmh: 103, pml: 98, pm_done: true };

test("above both highs is an outside day up; below both lows, down", () => {
  assert.equal(outsideDay(103.5, SET), "up");
  // Pre-market 90 to 94 on a gap down: under both lows.
  assert.equal(outsideDay(89.5, { pdh: 100, pdl: 95, pmh: 94, pml: 90, pm_done: true }), "down");
});

test("over the previous day's high and still under the pre-market high is not one", () => {
  // The case the old chip got wrong: through PDH, inside the pre-market range.
  assert.equal(outsideDay(101.2, SET), null);
  assert.equal(throughDay(101.2, SET), true);
  // And the mirror: under PDL, above the pre-market low.
  const down = { pdh: 100, pdl: 95, pmh: 94, pml: 90, pm_done: true };
  assert.equal(outsideDay(92, down), null);
  assert.equal(throughDay(92, down), true);
});

test("over the pre-market high and inside yesterday's range is not one either", () => {
  assert.equal(outsideDay(99.5, { pdh: 100, pdl: 95, pmh: 99, pml: 97, pm_done: true }), null);
  assert.equal(throughDay(99.5, { pdh: 100, pdl: 95 }), false);
});

test("a level is broken by trading through it, not by touching it", () => {
  assert.equal(outsideDay(103, SET), null);
  assert.equal(outsideDay(100, { ...SET, pmh: 99 }), null);
});

test("before 09:30 the pre-market range is still forming, so the previous day's level alone decides", () => {
  const forming = { pdh: 100, pdl: 95, pmh: 103, pml: 98, pm_done: false };
  assert.equal(outsideDay(101.2, forming), "up");
  assert.equal(outsideDay(94, forming), "down");
  assert.equal(outsideDay(97, forming), null);
});

test("a name with no pre-market range has one range to be through, and is not an outside day", () => {
  assert.equal(outsideDay(101, { pdh: 100, pdl: 95, pmh: null, pml: null, pm_done: true }), null);
  assert.equal(throughDay(101, { pdh: 100, pdl: 95 }), true);
});

test("nothing read is nothing said", () => {
  assert.equal(outsideDay(null, SET), null);
  assert.equal(outsideDay(101, { pdh: null, pdl: null, pmh: null, pml: null, pm_done: false }), null);
  assert.equal(throughDay(null, SET), false);
  assert.equal(throughDay(101, { pdh: null, pdl: 95 }), false);
});
