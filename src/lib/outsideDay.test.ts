// node --experimental-strip-types --test src/lib/outsideDay.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { dayState, outsideDay, throughDay } from "./outsideDay.ts";

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

// ---- the one state a futures contract's Levels card prints -------------------------

// NQ's chart on Saturday 14 Nov 2026: Thursday's cash range, Friday's pre-market.
const NQ = { pdh: 28652.25, pdl: 28044.5, pmh: 28583.75, pml: 28260, pm_done: true };
// Friday's futures day: high 28,607.75, low 27,695.25.
const FRIDAY = { high: 28607.75, low: 27695.25 };

test("the state is outside before it is through: NQ finished Friday under both lows", () => {
  assert.deepEqual(dayState(28034.75, NQ, FRIDAY), { kind: "outside", dir: "down" });
  assert.deepEqual(dayState(28700, NQ, { high: 28700, low: 28100 }), { kind: "outside", dir: "up" });
});

test("beyond the previous day's level alone is through, the way it went", () => {
  // Under PDL 28,044.5 and still over a pre-market low further down.
  const low = { ...NQ, pml: 27900 };
  assert.deepEqual(dayState(28000, low, FRIDAY), { kind: "through", dir: "down" });
  // Over PDH and still under a pre-market high further up.
  const high = { ...NQ, pmh: 28800 };
  assert.deepEqual(dayState(28700, high, { high: 28720, low: 28100 }), { kind: "through", dir: "up" });
  // With no pre-market range there is one range to be through: never an outside day.
  assert.deepEqual(dayState(28700, { ...NQ, pmh: null, pml: null }, null), { kind: "through", dir: "up" });
});

test("the whole day inside the previous day's range is an inside day", () => {
  assert.deepEqual(dayState(28300, NQ, { high: 28500, low: 28100 }), { kind: "inside" });
  // A day that only touched the level has not been through it.
  assert.deepEqual(dayState(28300, NQ, { high: 28652.25, low: 28044.5 }), { kind: "inside" });
});

test("between the levels after trading beyond one is back inside, and says which", () => {
  assert.deepEqual(dayState(28300, NQ, { high: 28700, low: 28100 }), { kind: "back", over: true, under: false });
  assert.deepEqual(dayState(28300, NQ, FRIDAY), { kind: "back", over: false, under: true });
  assert.deepEqual(dayState(28300, NQ, { high: 28700, low: 27900 }), { kind: "back", over: true, under: true });
});

test("between the levels with the day's own range unknown is only between", () => {
  assert.deepEqual(dayState(28300, NQ, null), { kind: "between" });
  assert.deepEqual(dayState(28300, NQ, { high: null, low: 28100 }), { kind: "between" });
  // A print on a level is not through it.
  assert.deepEqual(dayState(28652.25, NQ), { kind: "between" });
});

test("before 09:30 the previous day's level alone makes an outside day, as on a stock", () => {
  assert.deepEqual(dayState(28700, { ...NQ, pmh: 28900, pm_done: false }, null), { kind: "outside", dir: "up" });
});

test("no print or no previous day's range is no state", () => {
  assert.equal(dayState(null, NQ, FRIDAY), null);
  assert.equal(dayState(Number.NaN, NQ, FRIDAY), null);
  assert.equal(dayState(28300, null, FRIDAY), null);
  assert.equal(dayState(28300, { ...NQ, pdh: null }, FRIDAY), null);
});

test("nothing read is nothing said", () => {
  assert.equal(outsideDay(null, SET), null);
  assert.equal(outsideDay(101, { pdh: null, pdl: null, pmh: null, pml: null, pm_done: false }), null);
  assert.equal(throughDay(null, SET), false);
  assert.equal(throughDay(101, { pdh: null, pdl: 95 }), false);
});
