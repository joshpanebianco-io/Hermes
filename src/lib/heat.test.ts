import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_TINT, heatMax, heatStyle, heatVar, tintPct } from "./heat.ts";

test("the tint is strongest at the board's biggest move and clear with no figure", () => {
  assert.equal(tintPct(9, 9), MAX_TINT);
  assert.equal(tintPct(-9, 9), MAX_TINT);
  assert.equal(tintPct(null, 9), 0);
  assert.equal(tintPct(NaN, 9), 0);
});

test("a sector's move stays visible on a day a theme runs nine percent", () => {
  // In a straight line +1.45 against +9.04 would tint 5%; on the root it is 14%.
  assert.equal(tintPct(1.45, 9.04), 14);
});

test("a card next to nothing stays clear", () => {
  assert.equal(tintPct(0.03, 9.04), 0);
});

test("the tint takes the side's hue", () => {
  assert.match(String(heatStyle(2, 4)?.background), /--call/);
  assert.match(String(heatStyle(-2, 4)?.background), /--put/);
  assert.equal(heatStyle(0, 4), undefined);
});

test("the same tint as a layer, for a card whose ground lifts under the pointer", () => {
  // The Sectors cards: the tint is `--heat`, never an inline background that would beat
  // the hover. A card too flat to tint carries nothing, and is a plain card.
  const up = heatVar(2, 4) as Record<string, string> | undefined;
  assert.equal(up?.["--heat"], heatStyle(2, 4)?.background);
  assert.equal(up && "background" in up, false);
  assert.equal(heatVar(0, 4), undefined);
});

test("a dead day is never scaled past a point", () => {
  assert.equal(heatMax([0.1, -0.2, null]), 1);
  assert.equal(heatMax([0.1, -9.04, 2]), 9.04);
});
