// node --experimental-strip-types --test src/lib/ask/prompt.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { numeralsIn, prefsBlock, splitUnverified, TOOL_RULES, unverifiedNumerals } from "./prompt.ts";

test("a figure the data carries passes, to two places", () => {
  const known = numeralsIn("VWAP 28971.374 · VIX 17.2 · WTI 103.31");
  assert.deepEqual(unverifiedNumerals("VWAP is 28971.37 and VIX 17.2", known), []);
  assert.deepEqual(unverifiedNumerals("WTI at 103.3", known), ["103.3"]); // one place is rounding, not quoting
});

test("an index or a moving average is a name, not a figure", () => {
  assert.deepEqual(unverifiedNumerals("the S&P 500 and the Nasdaq-100 fell; NVDA is above its 200-day and the 50-day", []), []);
  assert.deepEqual(unverifiedNumerals("the Russell 2000 lagged, the 10-year held, 0DTE flow was heavy in 2026", []), []);
  // With a unit or a currency it is a figure again.
  assert.deepEqual(unverifiedNumerals("Google erased $500 billion", []), ["500"]);
  assert.deepEqual(unverifiedNumerals("a 500 point move", []), ["500"]);
});

test("a figure carried from an earlier answer is named apart from one from nowhere", () => {
  const known = numeralsIn("NQ 28916 · VIX 18.47");
  const earlier = numeralsIn("VWAP since 18:00 is 28971.37, the overnight low 28821.5");
  const got = splitUnverified("VWAP 28971.37, the ON low 28821.5, VIX 18.47, and a put wall at 28940", known, earlier);
  assert.deepEqual(got.carried, ["28971.37", "28821.5"]);
  assert.deepEqual(got.unverified, ["28940"]);
});

test("a question across names is sent to the scanner table, and nothing is missing before the panel is asked", () => {
  const stocks = TOOL_RULES(["scanner", "scanner_row", "bars", "wire", "earnings", "calendar", "sessions", "digest", "note", "panel"]);
  assert.match(stocks, /starts with scanner/);
  assert.match(stocks, /A table line carries no contract/);
  assert.match(stocks, /Never tell the reader the terminal does not show something until you have called the tool or the panel/);
  assert.match(stocks, /panel for every other panel on every tab/);
  const futures = TOOL_RULES(["levels", "heavyweights", "event_risk", "wire", "earnings", "calendar", "sessions", "digest", "note", "panel"]);
  assert.doesNotMatch(futures, /starts with scanner|prefer scanner|scanner_row/);
  assert.match(futures, /prefer panel, the narrower tools/);
  assert.match(futures, /levels for a futures book's ladder/);
});

test("the reader's settings read as the Settings tab sets them", () => {
  assert.equal(prefsBlock(null), "");
  const on = prefsBlock({ budget: 500, zeroDte: false, alerts: { on: true, desktop: false, sound: true, kinds: ["L", "BO"], minScore: 40 } });
  assert.match(on, /Options budget: \$500 of premium at risk on one trade\./);
  assert.match(on, /off, so every name gets the weekly/);
  assert.match(on, /on, for the \(L\) retest, the ◆ breakout, names scoring 40 or more; sound on, desktop notifications off/);
  const unset = prefsBlock({ budget: null, zeroDte: true, alerts: { on: false, desktop: false, sound: false, kinds: [], minScore: 0 } });
  assert.match(unset, /not set, so the Scanner shows no contract count/);
  assert.match(unset, /Alerts: off\./);
});
