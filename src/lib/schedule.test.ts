// node --experimental-strip-types --test src/lib/schedule.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { diaryRows, oneSchedule, tierLit, toggleTier } from "./schedule.ts";

// Wed 18 Nov 2026, 14:00 ET (19:00 UTC).
const T1400 = Date.UTC(2026, 10, 18, 19, 0) / 1000;
const HOUR = 3600;

const fed = (kind: string, title: string, ts: number | null, date = "2026-11-18", et: string | null = "14:00") =>
  ({ kind, title, note: null, date, days: 1, et, utc: ts ? new Date(ts * 1000).toISOString() : null, ts, in_days: 5, major: true }) as never;

const auction = (term: string, ts: number, major = true, amount: number | null = null) =>
  ({ term, label: `${term} note`, security: "Note", date: "2026-11-18", et: "13:00", utc: new Date(ts * 1000).toISOString(), ts, in_days: 5, amount_bn: amount, reopening: false, major }) as never;

const cal = (event: string, ts: number | null, region = "us") =>
  ({ event, country: region === "us" ? "United States" : "Japan", region, session: null, themes: [], core: true, date: "2026-11-18", et: "14:00", utc: null, ts, actual: null, actual_raw: null, consensus: null, consensus_raw: null, previous: null, previous_raw: null, surprise: null, released: false, score: 3, note: null }) as never;

test("the minutes, the Beige Book and a decision become rows; a speech does not", () => {
  const rows = diaryRows(
    [
      fed("FOMC", "FOMC Minutes", T1400),
      fed("Beige Book", "Beige Book", T1400 + 7 * 24 * HOUR, "2026-11-25"),
      fed("FOMC", "FOMC Meeting", T1400 + 21 * 24 * HOUR, "2026-12-09"),
      // Already a calendar row, from Nasdaq or added by the collector: never added here.
      fed("Speech", "Speech - Governor Michael S. Barr", T1400 - HOUR),
      fed("Testimony", "Testimony - Chair", T1400 - 2 * HOUR),
      fed("Conference", "Community Banking Research Conference", T1400),
    ],
    [],
    [],
  );
  assert.deepEqual(rows.map((r) => [r.event, r.score]), [["FOMC Minutes", 5], ["Beige Book", 3], ["FOMC Meeting", 5]]);
  // They read as US rows that reach the books, with no figures and nothing printed.
  assert.ok(rows.every((r) => r.region === "us" && r.core && !r.released && r.actual_raw === null));
});

test("what the calendar already lists is not listed twice", () => {
  const have = [cal("FOMC Meeting Minutes", T1400), cal("10-Year Note Auction", T1400 - HOUR), cal("Beige Book", T1400 + 3 * HOUR)];
  const rows = diaryRows(
    [fed("FOMC", "FOMC Minutes", T1400), fed("Beige Book", "Beige Book", T1400 + 3 * HOUR)],
    [auction("10Y", T1400 - HOUR), auction("30Y", T1400 - HOUR)],
    have,
  );
  // Only the 30-year, which the feed did not carry.
  assert.deepEqual(rows.map((r) => r.event), ["30Y note auction"]);
});

test("a twin is the same thing near the same time, not a like-named row somewhere else", () => {
  // A member speaking on decision day is not the decision, and last meeting's minutes are not it either.
  const speaks = [cal("FOMC Member Barr Speaks", T1400 - HOUR), cal("FOMC Meeting Minutes", T1400)];
  assert.deepEqual(diaryRows([fed("FOMC", "FOMC Meeting", T1400)], [], speaks).map((r) => r.event), ["FOMC Meeting"]);
  // The statement is.
  assert.equal(diaryRows([fed("FOMC", "FOMC Meeting", T1400)], [], [cal("Fed Interest Rate Decision", T1400)]).length, 0);
  // The same name a week away, or on another country's calendar, is a different event.
  assert.equal(diaryRows([fed("FOMC", "FOMC Minutes", T1400)], [], [cal("FOMC Meeting Minutes", T1400 + 7 * 24 * HOUR)]).length, 1);
  assert.equal(diaryRows([fed("FOMC", "FOMC Minutes", T1400)], [], [cal("BoJ Meeting Minutes", T1400, "apac")]).length, 1);
  // A 2-year auction does not stand in for the 20-year.
  assert.equal(diaryRows([], [auction("20Y", T1400)], [cal("2-Year Note Auction", T1400)]).length, 1);
});

test("an auction says its size once announced, and a row with no time is left out", () => {
  const [a] = diaryRows([], [auction("30Y", T1400, true, 22)], []);
  assert.equal(a.event, "30Y note auction · $22bn");
  assert.equal(a.score, 3);
  assert.equal(diaryRows([], [auction("3Y", T1400, false)], [])[0].score, 2);
  assert.equal(diaryRows([fed("FOMC", "FOMC Meeting", null, "2026-12-09", null)], [], []).length, 0);
});

test("the schedule is in time order, and untouched when the diary adds nothing", () => {
  const rows = [cal("Retail Sales m/m", T1400 - 5 * HOUR), cal("Existing Home Sales", T1400 + HOUR)];
  const merged = oneSchedule(rows, [fed("FOMC", "FOMC Minutes", T1400)], [auction("20Y", T1400 - HOUR)]);
  assert.deepEqual(merged.map((r) => r.event), ["Retail Sales m/m", "20Y note auction", "FOMC Minutes", "Existing Home Sales"]);
  assert.equal(oneSchedule(rows, [], []), rows);
});

test("lit is what you see: three switches, no All, and the last cannot be put out", () => {
  const ALL = ["high", "medium", "low"] as const;
  // The Wire opens on High and Med.
  let lit: string[] = ["high", "medium"];
  assert.deepEqual([tierLit(lit, "high"), tierLit(lit, "medium"), tierLit(lit, "low")], [true, true, false]);
  // Lighting Low is the whole tape: stored empty, as the old All was, and every chip is lit.
  lit = toggleTier(lit, "low", ALL);
  assert.deepEqual(lit, []);
  assert.deepEqual(ALL.map((k) => tierLit(lit, k)), [true, true, true]);
  // From everything, a click takes that tier out.
  lit = toggleTier(lit, "low", ALL);
  assert.deepEqual(lit, ["high", "medium"]);
  lit = toggleTier(lit, "medium", ALL);
  assert.deepEqual(lit, ["high"]);
  // Putting out the only one lit shows everything, never nothing.
  lit = toggleTier(lit, "high", ALL);
  assert.deepEqual(lit, []);
  // Stored in the tiers' own order whatever the order of the clicks.
  assert.deepEqual(toggleTier(["low"], "high", ALL), ["high", "low"]);
});
