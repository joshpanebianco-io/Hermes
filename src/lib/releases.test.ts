// node --experimental-strip-types --test src/lib/releases.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { countryCode, placedName } from "./releases.ts";

test("a release with no country column beside it says whose it is", () => {
  // 02:00 ET on Wed 11 Nov 2026: Germany's final CPI, listed as "CPI m/m".
  assert.equal(placedName("CPI m/m", "Germany"), "DE CPI m/m");
  assert.equal(placedName("PPI m/m", "Japan"), "JP PPI m/m");
  assert.equal(placedName("GDP q/q", "Euro Zone"), "EZ GDP q/q");
  assert.equal(placedName("GDP q/q", "United Kingdom"), "UK GDP q/q");
});

test("America's are as they are, and a name that already says is left alone", () => {
  assert.equal(placedName("Core CPI m/m", "United States"), "Core CPI m/m");
  assert.equal(placedName("FOMC Member Barr Speaks", "United States"), "FOMC Member Barr Speaks");
  assert.equal(placedName("German CPI m/m", "Germany"), "German CPI m/m");
  assert.equal(placedName("U.K. Construction Output", "United Kingdom"), "U.K. Construction Output");
  assert.equal(placedName("Trade Balance", null), "Trade Balance");
});

test("two letters a country, the listed ones by their own code", () => {
  assert.equal(countryCode("New Zealand"), "NZ"); // its first two letters read as "NE"
  assert.equal(countryCode("Spain"), "ES");
  assert.equal(countryCode("Euro Zone"), "EZ");
  assert.equal(countryCode("Norway"), "NO");
});
