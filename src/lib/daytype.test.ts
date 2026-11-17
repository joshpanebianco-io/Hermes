// node --experimental-strip-types --test src/lib/daytype.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { DayHold, DayLean } from "@/types/terminal";
import { labelWords, leanLine, leanTitle, nightWords, voteWord } from "./daytype.ts";

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

// ---- the one line a card has room for (leanLine, 2026-11-15) ---------------------------

const hold = (condition: string, n: number, trend: number, range: number, vote: DayHold["vote"] = null) => ({ condition, shown: null, n, trend, range, vote });

// ES on Saturday 14 Nov 2026, for Monday's session.
const ES: DayLean = {
  call: "trend",
  word: "Trend day more possible",
  why: "yesterday was a normal day: 24 trend days in 189, 96 range",
  holds: [hold("yesterday was a normal day", 189, 24, 96, "trend"), hold("VIX 18 to 28", 215, 21, 112), hold("Monday", 105, 3, 69)],
  base: { n: 573, trend: 41, range: 341 },
  night: { atr: null, done: null, asia: null, london: 0.177, pre: 0.44 },
  prev: { type: "normal", dir: null, range_atr: 0.82 },
};

test("a call's line leads with the called side's count, then the condition that carries it", () => {
  assert.equal(leanLine(ES), "24 trend days in 189 · yesterday was a normal day");
  const range: DayLean = { ...ES, call: "range", word: "Range day likely", holds: [hold("quiet night after a range day", 114, 1, 96, "range")] };
  assert.equal(leanLine(range), "96 range days in 114 · quiet night after a range day");
});

test("two conditions voting the same way: the first, and how many more", () => {
  const two: DayLean = { ...ES, holds: [hold("yesterday was a normal day", 189, 24, 96, "trend"), hold("big night", 117, 12, 40, "trend"), hold("Monday", 105, 3, 69)] };
  assert.equal(leanLine(two), "24 trend days in 189 · yesterday was a normal day +1");
});

test("no lean has no count to show: the night so far and yesterday's shape", () => {
  // NQ the same evening.
  const nq: DayLean = { ...ES, call: "none", word: "No lean", why: "nothing in the record separates today", holds: [hold("yesterday was a range day", 352, 16, 243)], prev: { type: "range", dir: null, range_atr: 0.74 } };
  assert.equal(leanLine(nq), "night not read yet · after a range day");
  assert.equal(leanLine(nq), nightWords(nq));
});

test("a mixed record has two sides and keeps the server's own line", () => {
  const mixed: DayLean = { ...ES, call: "mixed", word: "Mixed record", why: "big night: 12 trend days in 117; quiet London: 80 range in 97", holds: [hold("big night", 117, 12, 40, "trend"), hold("quiet London", 97, 2, 80, "range")] };
  assert.equal(leanLine(mixed), mixed.why);
});

test("a call with no voting condition on its side falls back to the server's line", () => {
  assert.equal(leanLine({ ...ES, holds: [hold("Monday", 105, 3, 69)] }), ES.why);
});

test("a halved trend rate is printed as a vote against the trend call", () => {
  // ES at 08:57 ET on 16 Nov 2026: after a normal day it votes trend, Mondays against.
  assert.equal(voteWord("trend"), "votes trend");
  assert.equal(voteWord("range"), "votes range");
  assert.equal(voteWord("no_trend"), "against trend");
  assert.equal(voteWord(null), "");
  const mixed: DayLean = {
    ...ES,
    call: "mixed",
    word: "Mixed record",
    why: "yesterday was a normal day: 24 trend days in 189, 96 range · Monday: 3 trend days in 105, 69 range",
    holds: [hold("yesterday was a normal day", 189, 24, 96, "trend"), hold("Monday", 105, 3, 69, "no_trend")],
  };
  assert.equal(leanLine(mixed), mixed.why);
});
