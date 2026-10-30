// node --experimental-strip-types --test src/lib/ask/prompt.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { numeralsIn, splitUnverified, unverifiedNumerals } from "./prompt.ts";

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
