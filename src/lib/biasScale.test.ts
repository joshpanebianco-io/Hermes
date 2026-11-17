import assert from "node:assert/strict";
import { test } from "node:test";
import { scaleLabel, scalePos, wholeScore } from "./biasScale.ts";

test("the score is a place on the scale: neutral in the middle, the extremes at the ends", () => {
  assert.equal(scalePos(0), 50);
  assert.equal(scalePos(-100), 0);
  assert.equal(scalePos(100), 100);
  assert.equal(scalePos(-31), 34.5);
  assert.equal(scalePos(56), 78);
});

test("a short reads as far left of the middle as the same long reads right of it", () => {
  for (const s of [3, 10, 31, 50, 77, 100]) {
    assert.equal((scalePos(s) as number) - 50, 50 - (scalePos(-s) as number));
  }
});

test("a score past the ends sits on the end, and no score has no place", () => {
  assert.equal(scalePos(140), 100);
  assert.equal(scalePos(-140), 0);
  assert.equal(scalePos(null), null);
  assert.equal(scalePos(undefined), null);
  assert.equal(scalePos(Number.NaN), null);
});

test("a read scored over the whole weight is used as it is", () => {
  assert.equal(wholeScore({ score: -35, coverage: 35, basis: "whole" }), -35);
  assert.equal(wholeScore({ score: 48, coverage: 100, basis: "whole" }), 48);
});

test("a read from before the rule is its old score times the weight that was live", () => {
  // Saturday 14 Nov 2026, 17:39 ET, as the pages had them under the old rule.
  assert.equal(wholeScore({ score: -100, coverage: 35 }), -35); // the Stocks tape, 2 reads of 11
  assert.equal(wholeScore({ score: -31, coverage: 68 }), -21); // NQ, 6 of 14
  assert.equal(wholeScore({ score: -21, coverage: 68 }), -14); // ES
  assert.equal(wholeScore({ score: -56, coverage: 63 }), -35); // GC
  // With everything live the two rules are one figure.
  assert.equal(wholeScore({ score: 62, coverage: 100 }), 62);
  // A small short rounds to nought, not to minus nought.
  assert.equal(wholeScore({ score: -1, coverage: 30 }), 0);
});

test("with no coverage to go by the score is all there is, and no score is none", () => {
  assert.equal(wholeScore({ score: 40 }), 40);
  assert.equal(wholeScore({ score: 40, coverage: null }), 40);
  assert.equal(wholeScore({ coverage: 35 }), null);
  assert.equal(wholeScore({ score: null, coverage: 35 }), null);
  assert.equal(wholeScore({ score: Number.NaN, coverage: 35 }), null);
});

test("the scale says what it shows in words", () => {
  assert.equal(scaleLabel(-31), "Bias -31 on a scale from -100, bearish, to +100, bullish");
  assert.equal(scaleLabel(100), "Bias +100 on a scale from -100, bearish, to +100, bullish");
  assert.equal(scaleLabel(null), "No bias score yet");
});
