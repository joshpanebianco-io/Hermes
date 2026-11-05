// node --experimental-strip-types --test src/lib/vix.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { bandChip, curveOverride, curveShape, levelRow, vixBand, vixRow, vixSub } from "./vix.ts";

test("the owner's case: 23.72 over 23.00 is Stressed by the curve, and the number sits in Elevated", () => {
  const shape = curveShape(23.72 / 23.0);
  assert.equal(shape, "backwardation");
  const band = vixBand(23.72, shape);
  assert.equal(band, "stressed");
  assert.equal(vixRow(band, vixSub(23.72, band)), "stressed");
  assert.equal(curveOverride(23.72, band), true);
  assert.equal(levelRow(23.72), "elevated");
  assert.equal(bandChip(band, null, curveOverride(23.72, band)), "Stressed · curve");
});

test("the curve only overrides under 28: from there the level says the same", () => {
  assert.equal(curveOverride(27.99, "stressed"), true);
  assert.equal(curveOverride(28, "stressed"), false);
  assert.equal(curveOverride(36, "stressed"), false);
  assert.equal(bandChip("stressed", null, curveOverride(30, "stressed")), "Stressed");
  assert.equal(levelRow(30), "stressed");
});

test("no other band is ever the curve's, and no number means no override", () => {
  assert.equal(curveOverride(23, "elevated"), false);
  assert.equal(curveOverride(15, "normal"), false);
  assert.equal(curveOverride(null, "stressed"), false);
  assert.equal(curveOverride(Number.NaN, "stressed"), false);
  assert.equal(curveOverride(20, null), false);
});

test("the number's own row at each edge of the table", () => {
  assert.equal(levelRow(12.99), "grind");
  assert.equal(levelRow(13), "normal_quiet");
  assert.equal(levelRow(17.99), "normal_quiet");
  assert.equal(levelRow(18), "normal_heavy");
  assert.equal(levelRow(19.99), "normal_heavy");
  assert.equal(levelRow(20), "elevated");
  assert.equal(levelRow(27.99), "elevated");
  assert.equal(levelRow(28), "stressed");
  assert.equal(levelRow(34.99), "stressed");
  assert.equal(levelRow(35), "panic");
  assert.equal(levelRow(null), null);
});

test("the chip's other words are unchanged", () => {
  assert.equal(bandChip("normal", "heavy"), "Normal · 18+");
  assert.equal(bandChip("stressed", "panic"), "Stressed · 35+");
  assert.equal(bandChip("elevated", null), "Elevated");
  assert.equal(bandChip(null, null), null);
});
