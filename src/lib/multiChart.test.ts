// node --experimental-strip-types --test src/lib/multiChart.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { CHART_SLOTS, TOP_N, fillSlots, isHeldSlots, placeIn, sameSlots, topScores } from "./multiChart.ts";

const TEN = ["AMD", "AVGO", "FLY", "MSFT", "MU", "MSTR", "SPCX", "META", "NVDA", "SNDK"];
const row = (sym: string, total: number, ok = true) => ({ sym, ok, score: { total } });

test("the top ten are the ten highest scores, ties in the engine's order", () => {
  const rows = [row("AMD", 100), row("AVGO", 100), row("FLY", 99), row("QQQ", 0), row("MSFT", 90)];
  assert.deepEqual(topScores(rows, 3), ["AMD", "AVGO", "FLY"]);
  // Out of order on the way in: the score decides, and equal scores keep their order.
  assert.deepEqual(topScores([row("B", 50), row("A", 80), row("C", 80)], 3), ["A", "C", "B"]);
  // A name that could not be read is not ranked, whatever its score says.
  assert.deepEqual(topScores([row("X", 99, false), row("Y", 10)]), ["Y"]);
  assert.equal(topScores(Array.from({ length: 40 }, (_, i) => row(`S${i}`, 100 - i))).length, TOP_N);
  // The rows handed in are not reordered.
  assert.deepEqual(rows.map((r) => r.sym), ["AMD", "AVGO", "FLY", "QQQ", "MSFT"]);
});

test("nothing held: the six charts are the first six, in order", () => {
  assert.deepEqual(fillSlots([], TEN), TEN.slice(0, 6));
  assert.equal(fillSlots([], TEN).length, CHART_SLOTS);
});

test("a chart keeps its name while the name is in the ten, whatever its rank does", () => {
  const held = ["AMD", "AVGO", "FLY", "MSFT", "MU", "MSTR"];
  // The same ten, the ranks shuffled: no chart changes.
  const shuffled = ["MU", "SNDK", "AMD", "META", "MSTR", "FLY", "AVGO", "NVDA", "MSFT", "SPCX"];
  assert.deepEqual(fillSlots(held, shuffled), held);
});

test("a name that leaves the ten gives its chart to the best name not on screen", () => {
  const held = ["AMD", "AVGO", "FLY", "MSFT", "MU", "MSTR"];
  // FLY drops out and NBIS comes in at the bottom: SPCX is the best of the four unshown.
  const pool = ["AMD", "AVGO", "MSFT", "MU", "MSTR", "SPCX", "META", "NVDA", "SNDK", "NBIS"];
  const next = fillSlots(held, pool);
  assert.deepEqual(next, ["AMD", "AVGO", "SPCX", "MSFT", "MU", "MSTR"]);
  // FLY comes back: written down, the replacement stays, so nothing flips back and forth.
  assert.deepEqual(fillSlots(next, TEN), next);
});

test("a reader's pick outside the first six holds too", () => {
  const picked = placeIn(TEN.slice(0, 6), 2, "SNDK");
  assert.deepEqual(picked, ["AMD", "AVGO", "SNDK", "MSFT", "MU", "MSTR"]);
  assert.deepEqual(fillSlots(picked, TEN), picked);
});

test("a name already on another chart trades places", () => {
  const six = TEN.slice(0, 6);
  assert.deepEqual(placeIn(six, 0, "MU"), ["MU", "AVGO", "FLY", "MSFT", "AMD", "MSTR"]);
  // The same name, or a chart that is not there: nothing moves, and the input is not changed.
  assert.deepEqual(placeIn(six, 0, "AMD"), six);
  assert.deepEqual(placeIn(six, 9, "MU"), six);
  assert.deepEqual(six, TEN.slice(0, 6));
});

test("fewer names than charts, a name held twice, and a list that grows back", () => {
  assert.deepEqual(fillSlots(["AMD", "AVGO", "FLY", "MSFT", "MU", "MSTR"], ["MSFT", "AMD"]), ["AMD", "MSFT"]);
  assert.deepEqual(fillSlots([], []), []);
  // A stored list that names one twice shows it once.
  assert.deepEqual(fillSlots(["AMD", "AMD", "FLY"], TEN, 3), ["AMD", "AVGO", "FLY"]);
  // Two charts, then the list is ten again: the two stay and the rest fill in order.
  assert.deepEqual(fillSlots(["AMD", "MSFT"], TEN), ["AMD", "MSFT", "AVGO", "FLY", "MU", "MSTR"]);
});

test("what storage holds is checked before it is believed", () => {
  assert.equal(isHeldSlots({ key: "2026-11-11|all|score", slots: ["AMD", "MU"] }), true);
  assert.equal(isHeldSlots({ key: "", slots: [] }), true);
  assert.equal(isHeldSlots(null), false);
  assert.equal(isHeldSlots(["AMD"]), false);
  assert.equal(isHeldSlots({ key: 3, slots: [] }), false);
  assert.equal(isHeldSlots({ key: "k", slots: ["AMD", 7] }), false);
  assert.equal(isHeldSlots({ key: "k", slots: ["THIRTEENCHARS"] }), false);
  assert.equal(sameSlots(["A", "B"], ["A", "B"]), true);
  assert.equal(sameSlots(["A", "B"], ["B", "A"]), false);
  assert.equal(sameSlots(["A"], ["A", "B"]), false);
});
