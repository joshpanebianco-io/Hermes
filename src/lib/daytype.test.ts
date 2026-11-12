// node --experimental-strip-types --test src/lib/daytype.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { DayLean } from "@/types/terminal";
import { labelWords, leanTitle, nightWords } from "./daytype.ts";

const lean: DayLean = {
  call: "range",
  word: "Range day likely",
  why: "quiet night (0.31 ATR so far): 2 trend days in 142, 108 range",
  holds: [],
  base: { n: 569, trend: 39, range: 347 },
  night: { atr: 0.31, done: false, asia: 0.1, london: 0.12, pre: 0.2 },
  prev: { type: "range", dir: null, range_atr: 0.55 },
};

test("the night and yesterday in a few words", () => {
  assert.equal(nightWords(lean), "night 0.31 ATR so far · after a range day");
  assert.equal(
    nightWords({ ...lean, night: { ...lean.night, done: true }, prev: { type: "trend", dir: "down", range_atr: 1.4 } }),
    "night 0.31 ATR · after a trend day down",
  );
  assert.equal(nightWords({ ...lean, night: { ...lean.night, atr: null }, prev: { type: null, dir: null, range_atr: null } }), "night not read yet");
});

test("the day's label, once it has one", () => {
  assert.equal(labelWords({ type: "trend", dir: "up", inside: false, range_atr: 1.32, close_pos: 0.93 }), "trend day up · 1.32 ATR · closed 93% up its range");
  assert.equal(labelWords({ type: "range", dir: null, inside: true, range_atr: 0.6, close_pos: 0.4 }), "range day · 0.60 ATR · closed 40% up its range · inside yesterday");
});

test("the hover carries the counts and the one rule", () => {
  const t = leanTitle(lean);
  assert.ok(t.startsWith("quiet night (0.31 ATR so far): 2 trend days in 142, 108 range\nevery session: 39 trend days in 569, 347 range"));
  assert.ok(t.endsWith("Counts over the record, not probabilities."));
});
