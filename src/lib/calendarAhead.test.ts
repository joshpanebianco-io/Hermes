import assert from "node:assert/strict";
import { test } from "node:test";
import { aheadShown } from "./calendarAhead.ts";

type R = { day: string; score: number; name: string };
const r = (day: string, score: number, name = `${day}-${score}`): R => ({ day, score, name });
const day = (x: R) => x.day;
const score = (x: R) => x.score;

const WEEK: R[] = [
  r("Mon", 1), r("Mon", 3), r("Tue", 2), r("Tue", 5),
  r("Wed", 2), r("Wed", 4, "FOMC Minutes"), r("Thu", 3), r("Fri", 5, "Payrolls"), r("Tue+1", 5, "CPI"),
];

test("the first day is whole, later days only what stops the tape, one line each", () => {
  const got = aheadShown(WEEK, day, score, false);
  assert.deepEqual(got.shown.map((x) => x.name), ["Mon-1", "Mon-3", "Tue-5", "FOMC Minutes", "Payrolls", "CPI"]);
  assert.equal(got.hidden, 3);
  assert.equal(got.lastDay, "Tue+1");
  // Tuesday, Wednesday and Thursday lost a release; Monday and Friday are whole.
  assert.deepEqual(["Mon", "Tue", "Wed", "Thu", "Fri"].map(got.whole), [true, false, false, false, true]);
  // Every day past the first is folded, whole or not.
  assert.deepEqual(["Mon", "Tue", "Fri"].map(got.folded), [false, true, true]);
});

test("See more shows every release, unfolded", () => {
  const got = aheadShown(WEEK, day, score, true);
  assert.equal(got.shown.length, WEEK.length);
  assert.equal(got.hidden, 0);
  assert.deepEqual(["Mon", "Wed"].map(got.whole), [true, true]);
  assert.deepEqual(["Mon", "Wed"].map(got.folded), [false, false]);
});

test("the whole day is the first that has a release, whatever it is", () => {
  // Saturday has nothing: Sunday is the day in full.
  const got = aheadShown([r("Sun", 1), r("Mon", 1), r("Tue", 1)], day, score, false);
  assert.deepEqual(got.shown.map((x) => x.day), ["Sun"]);
  const none = aheadShown([], day, score, false);
  assert.deepEqual([none.shown, none.hidden, none.lastDay], [[], 0, null]);
});
