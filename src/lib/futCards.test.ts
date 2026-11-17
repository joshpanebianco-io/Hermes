// node --experimental-strip-types --test src/lib/futCards.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { countryShort, levelsFrom } from "./futCards.ts";

// The chart's own four on Saturday 14 Nov 2026: Thursday's cash range, Friday's pre-market.
const CHART = { pdh: 28652.25, pdl: 28044.5, pmh: 28583.75, pml: 28260 };

test("the chart's levels, highest first, each with its distance from the print", () => {
  // Friday's close, 28,034.75: under all four.
  const all = levelsFrom(CHART, 28034.75);
  assert.deepEqual(all.map((l) => l.key), ["PDH", "PMH", "PML", "PDL"]);
  assert.deepEqual(all.map((l) => l.dist), [617.5, 549, 225.25, 9.75]);
  // Between the pre-market low and high: two above, two below.
  assert.deepEqual(levelsFrom(CHART, 28300).map((l) => Math.sign(l.dist)), [1, 1, -1, -1]);
});

test("a day with no pre-market yet has two levels, and one with none has none", () => {
  assert.deepEqual(levelsFrom({ pdh: 28399, pdl: 27695.25, pmh: null, pml: null }, 28034.75).map((l) => l.key), ["PDH", "PDL"]);
  assert.deepEqual(levelsFrom({ pdh: null, pdl: null, pmh: null, pml: null }, 28034.75), []);
  assert.deepEqual(levelsFrom(CHART, null), []);
  assert.deepEqual(levelsFrom(null, 28034.75), []);
  assert.deepEqual(levelsFrom(CHART, Number.NaN), []);
});

test("a country is said as a card has room for it", () => {
  assert.equal(countryShort("United States"), "US");
  assert.equal(countryShort("United Kingdom"), "UK");
  assert.equal(countryShort("Japan"), "Japan");
  assert.equal(countryShort(null), "");
});
