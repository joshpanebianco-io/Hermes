// node --experimental-strip-types --test src/lib/ratesRead.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  dayLabel,
  decisionLine,
  isoDate,
  meetingSize,
  monthLabel,
  monthsApart,
  moveSize,
  moveText,
  pathSize,
  slope,
  slopeMove,
  tenYearRead,
} from "./ratesRead.ts";

test("a date reads one way: the day first, and a contract month with its year", () => {
  // The card printed "Jan 28" for January 2028 over "Dec 09" for the ninth of December.
  assert.equal(dayLabel("2026-12-09"), "Wed 9 Dec");
  assert.equal(dayLabel("2027-01-27"), "Wed 27 Jan");
  assert.equal(dayLabel("2026-11-13"), "Fri 13 Nov");
  assert.equal(dayLabel("not a date"), "not a date");
  assert.equal(monthLabel("2028-01"), "Jan 2028");
  assert.equal(monthLabel("2026-11"), "Nov 2026");
  assert.equal(monthsApart("2026-11", "2028-01"), 14);
  assert.equal(monthsApart("2026-11", "2026-11"), 0);
  assert.equal(monthsApart("", "2028-01"), null);
});

test("the Treasury's month-first date and the New York Fed's ISO one become the same thing", () => {
  assert.equal(isoDate("11/13/2026"), "2026-11-13");
  assert.equal(isoDate("1/5/2027"), "2027-01-05");
  assert.equal(isoDate("2026-11-12"), "2026-11-12");
  assert.equal(isoDate("2026-11-12T00:00:00"), "2026-11-12");
  assert.equal(isoDate("13 Nov"), null);
  assert.equal(isoDate(null), null);
});

test("a priced move is said in quarter points: the live path of 13 Nov 2026", () => {
  // What policy.meetings_priced gave for each meeting that day.
  assert.equal(moveSize(26.8), "a full hike");
  assert.equal(moveSize(17.2), "about two thirds of a hike");
  assert.equal(moveSize(16.6), "about two thirds of a hike");
  assert.equal(moveSize(8.4), "about a third of a hike");
  assert.equal(moveSize(10.7), "about half a hike");
  assert.equal(moveSize(3.8), "about a sixth of a hike");
  // The whole strip, Nov 2026 to Jan 2028.
  assert.equal(moveSize(86.2), "about 3½ hikes");
  assert.equal(pathSize(86.2, 14), "about 3½ hikes in 14 months");
});

test("cuts carry their own word, and nothing is priced inside the hold band", () => {
  assert.equal(moveSize(-25), "a full cut");
  assert.equal(moveSize(-12), "about half a cut");
  assert.equal(moveSize(-50), "about 2 cuts");
  assert.equal(moveSize(-62), "about 2½ cuts");
  assert.equal(moveSize(3), null);
  assert.equal(moveSize(-2.9), null);
  assert.equal(moveSize(null), null);
  assert.equal(moveSize(Number.NaN), null);
  assert.equal(pathSize(1.2, 14), "nothing priced in 14 months");
  assert.equal(pathSize(-25, 1), "a full cut in 1 month");
  assert.equal(pathSize(-25, null), "a full cut");
});

test("the words follow the collector's stance, so a row and its sentence cannot disagree", () => {
  // The click-through had its own 5bp hold band over the collector's 3: +4bp was a
  // hike on the row and "a hold is priced" in the words.
  assert.equal(meetingSize({ stance: "hike", move_bp: 4 }), "about a sixth of a hike");
  assert.equal(meetingSize({ stance: "hold", move_bp: 2.5 }), "a hold");
  assert.equal(meetingSize({ stance: "hold", move_bp: -0.5 }), "a hold");
  assert.equal(decisionLine({ stance: "hike", move_bp: 26.8, date: "2026-12-09" }), "A full hike is priced for Wed 9 Dec.");
  assert.equal(decisionLine({ stance: "hold", move_bp: 1, date: "2026-12-09" }), "A hold is priced for Wed 9 Dec.");
  assert.equal(decisionLine({ stance: "cut", move_bp: -17, date: "2027-01-27" }), "About two thirds of a cut is priced for Wed 27 Jan.");
  assert.equal(decisionLine({ stance: "hike", move_bp: 50, date: "2027-01-27" }), "About 2 hikes are priced for Wed 27 Jan.");
});

test("a yield's day change is a move with an arrow, never a sign with a colour", () => {
  assert.equal(moveText(5), "↑ 5bp");
  assert.equal(moveText(-2), "↓ 2bp");
  assert.equal(moveText(0), "unch");
  assert.equal(moveText(0.4), "unch");
  assert.equal(moveText(-0.4), "unch");
  assert.equal(moveText(null), "—");
});

test("the 10Y is the board's live vote while it trades", () => {
  const close = { value: 5.15, chgBp: 5, day: "2026-11-13" };
  assert.deepEqual(tenYearRead({ live: { last: 5.154, chgBp: 5.1, vote: "short" }, close }), {
    text: "The 10Y is up 5.1bp today at 5.15%:",
    wind: "headwind",
  });
  assert.deepEqual(tenYearRead({ live: { last: 5.04, chgBp: -6, vote: "long" }, close }), {
    text: "The 10Y is down 6bp today at 5.04%:",
    wind: "tailwind",
  });
  // Friday closed +5bp, Monday morning it is down 1.2: the close's headwind is not said.
  assert.deepEqual(tenYearRead({ live: { last: 5.14, chgBp: -1.2, vote: "neutral" }, close }), {
    text: "The 10Y is down 1.2bp today at 5.14%: inside ±4bp, no read from rates.",
    wind: null,
  });
});

test("with no live 10Y it is the Treasury's last close, and the close has its day on it", () => {
  assert.deepEqual(tenYearRead({ live: null, close: { value: 5.15, chgBp: 5, day: "2026-11-13" } }), {
    text: "The 10Y closed up 5bp at 5.15% on Fri 13 Nov:",
    wind: "headwind",
  });
  assert.deepEqual(tenYearRead({ live: null, close: { value: 4.4, chgBp: -7, day: "2026-11-13" } }), {
    text: "The 10Y closed down 7bp at 4.40% on Fri 13 Nov:",
    wind: "tailwind",
  });
  assert.deepEqual(tenYearRead({ live: null, close: { value: 5.15, chgBp: 2, day: "2026-11-13" } }), {
    text: "The 10Y closed up 2bp at 5.15% on Fri 13 Nov: inside ±4bp, no read from rates.",
    wind: null,
  });
  assert.deepEqual(tenYearRead({ live: null, close: { value: 5.15, chgBp: null, day: null } }), {
    text: "The 10Y closed at 5.15%.",
    wind: null,
  });
  assert.equal(tenYearRead({ live: null, close: null }), null);
});

test("27bp of 2s10s is nearly flat, not steep, and the day's change comes from the two legs", () => {
  assert.equal(slope(-12), "inverted");
  assert.equal(slope(27), "nearly flat");
  assert.equal(slope(49.9), "nearly flat");
  assert.equal(slope(50), "moderate");
  assert.equal(slope(100), "steep");
  // 13 Nov 2026: the 10Y +5bp, the 2Y +2bp.
  assert.equal(slopeMove(5, 2), "steeper by 3bp");
  assert.equal(slopeMove(-1, 3), "flatter by 4bp");
  assert.equal(slopeMove(2, 2), "unchanged");
  assert.equal(slopeMove(null, 2), null);
});
