// node --experimental-strip-types --test src/lib/releases.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { countryCode, family, groupReleases, placedName } from "./releases.ts";

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

test("GDP and its parts are one release, led by the growth rate", () => {
  // Japan's GDP of Sun 15 Nov 2026 came as six rows and filled the Macro calendar.
  const names = ["GDP Price Index y/y", "GDP Capital Expenditure q/q", "GDP q/q", "GDP Annualized", "GDP Private Consumption q/q", "GDP External Demand q/q"];
  const rows = names.map((event) => ({ event, when: 1794786600, country: "Japan", score: 4, figures: ["0.1%"] }));
  const out = groupReleases(rows, (r) => r);
  assert.equal(out.length, 1);
  assert.equal(out[0].lead.event, "GDP q/q");
  assert.equal(out[0].subs.length, 5);
  for (const n of [...names, "GDP y/y", "German GDP q/q", "GDP 3-Month Avg", "GDP Sales q/q"]) assert.equal(family(n), "gdp");
  // Not GDP: a nowcast by another name, and the price index of something else.
  assert.equal(family("GDPNow"), "gdpnow");
  assert.equal(family("Import Price Index m/m"), "import price");
  // Another country's, or another minute's, is another release.
  const two = groupReleases([...rows, { ...rows[2], country: "Germany" }, { ...rows[2], when: 1794790200 }], (r) => r);
  assert.equal(two.length, 3);
});
