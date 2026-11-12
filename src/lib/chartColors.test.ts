// node --experimental-strip-types --test src/lib/chartColors.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { CHART_COLORS, parseChartColors } from "./chartColors.ts";

test("what is stored is read as a choice, and anything else is Default", () => {
  assert.equal(parseChartColors('"josh"'), "josh");
  assert.equal(parseChartColors('"default"'), "default");
  assert.equal(parseChartColors(null), "default");
  // A value from another build, a bare word that is not JSON, an object, a number.
  assert.equal(parseChartColors('"midnight"'), "default");
  assert.equal(parseChartColors("josh"), "default");
  assert.equal(parseChartColors("{}"), "default");
  assert.equal(parseChartColors("1"), "default");
  assert.equal(parseChartColors(""), "default");
});

test("the menu offers exactly the two, Default first", () => {
  assert.deepEqual(CHART_COLORS.map((c) => c.value), ["default", "josh"]);
  assert.deepEqual(CHART_COLORS.map((c) => c.label), ["Default", "Josh"]);
});
