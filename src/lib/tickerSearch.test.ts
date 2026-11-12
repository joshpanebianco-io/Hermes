// node --experimental-strip-types --test src/lib/tickerSearch.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { FUNDS, LIMIT, fundRank, lookupFor, lookupVerdict, matchRank, suggest, tickerShape, type StockHit } from "./tickerSearch.ts";

const stock = (sym: string, name: string, cap = 1e10): StockHit => ({ sym, name, cap, sector: "XLK" });
// What the collector answered for these on 11 Nov 2026 (scratchpad search_probe.py).
const SPY_HITS = [stock("SYRE", "Spyre Therapeutics, Inc."), stock("SGP", "SpyGlass Pharma, Inc."), stock("DNUT", "Krispy Kreme, Inc.")];
const NV_HITS = [stock("NVDA", "NVIDIA Corporation", 4e12), stock("NVS", "Novartis AG Sponsored ADR"), stock("NVO", "Novo Nordisk A/S Sponsored ADR"), stock("NVT", "nVent Electric plc"), stock("NVR", "NVR, Inc.")];

test("the funds the terminal reads are in the box: SPY is SPY, not Spyre Therapeutics", () => {
  const rows = suggest("SPY", SPY_HITS);
  assert.deepEqual(rows[0], { sym: "SPY", name: "S&P 500", cap: null, sector: null, kind: "fund" });
  assert.deepEqual(rows.slice(1).map((r) => r.sym), ["SYRE", "SGP", "DNUT"]);
  // The collector knew none of these three at all.
  for (const q of ["QQQ", "GLD", "XLK", "smh"]) assert.equal(suggest(q, [])[0]?.sym, q.toUpperCase());
});

test("typing shows stocks: the collector's order is kept, largest first", () => {
  assert.deepEqual(suggest("nv", NV_HITS).map((r) => r.sym), ["NVDA", "NVS", "NVO", "NVT", "NVR"]);
  assert.equal(suggest("nv", NV_HITS)[0].kind, "stock");
  assert.deepEqual(suggest("", NV_HITS), []);
  assert.deepEqual(suggest("   ", NV_HITS), []);
});

test("a core fund leads its letters, a stock leads the other funds", () => {
  const sp = suggest("sp", [stock("SPGI", "S&P Global Inc."), stock("SPOT", "Spotify Technology S.A.")]);
  assert.deepEqual(sp.map((r) => r.sym), ["SPY", "SPGI", "SPOT"]);
  const ar = suggest("ar", [stock("ARM", "Arm Holdings plc"), stock("ARES", "Ares Management Corporation")]);
  assert.deepEqual(ar.map((r) => r.sym), ["ARM", "ARES", "ARKK"]);
});

test("a full box keeps places for the funds that matched", () => {
  const twelve = Array.from({ length: 12 }, (_, i) => stock(`XL${String.fromCharCode(65 + i)}Q`, `Xl Company ${i}`));
  const rows = suggest("xl", twelve);
  assert.equal(rows.length, LIMIT);
  // Eleven sector funds start with XL: at least three of them are on screen beside the stocks.
  assert.ok(rows.filter((r) => r.kind === "fund").length >= 3);
  assert.ok(rows.filter((r) => r.kind === "stock").length >= 1);
  // And an exact symbol is always first, whatever else matched.
  assert.equal(suggest("xlk", twelve)[0].sym, "XLK");
});

test("a company is found by its name, and a fund by what it holds", () => {
  assert.equal(matchRank("apple", "AAPL", "Apple Inc."), 2);
  assert.equal(matchRank("micro", "AMD", "Advanced Micro Devices, Inc."), 3);
  assert.equal(matchRank("zzzz", "AAPL", "Apple Inc."), null);
  assert.deepEqual(suggest("gold", [stock("GS", "Goldman Sachs Group, Inc.")]).map((r) => r.sym), ["GLD", "GS", "GDX", "GDXJ"]);
  assert.equal(suggest("semi", [])[0].sym, "SMH");
  assert.deepEqual(suggest("oil", []).map((r) => r.sym), ["USO", "XOP"]);
});

test("a fund's name is matched by whole words, and not from two letters", () => {
  // "nv" is inside "Investment Grade Credit", "sp" inside "Aerospace & Defense" and at the head of "Space".
  assert.equal(fundRank("nv", "LQD", "Investment Grade Credit"), null);
  assert.equal(fundRank("sp", "ITA", "Aerospace & Defense"), null);
  assert.equal(fundRank("sp", "NASA", "Space"), null);
  assert.equal(fundRank("spa", "NASA", "Space"), 2);
  assert.equal(fundRank("min", "GDX", "Gold Miners"), 2);
  assert.equal(fundRank("old", "GLD", "Gold"), null);
  assert.equal(fundRank("xl", "XLK", "Technology sector"), 1);
  assert.equal(fundRank("xlk", "XLK", "Technology sector"), 0);
});

test("no symbol is listed twice, and every fund is a possible ticker", () => {
  const rows = suggest("spy", [stock("SPY", "SPDR S&P 500 ETF Trust"), ...SPY_HITS]);
  assert.equal(rows.filter((r) => r.sym === "SPY").length, 1);
  assert.equal(new Set(FUNDS.map((f) => f.sym)).size, FUNDS.length);
  for (const f of FUNDS) assert.equal(tickerShape(f.sym), f.sym);
});

test("what was typed is offered as a ticker to check only when it could be one and no row is it", () => {
  assert.equal(tickerShape(" tsll "), "TSLL");
  assert.equal(tickerShape("brk.b"), "BRK.B");
  assert.equal(tickerShape("tesla motors"), null);
  assert.equal(tickerShape("averyveryverylongname"), null);
  assert.equal(tickerShape(""), null);
  assert.equal(lookupFor("zzzz", []), "ZZZZ");
  assert.equal(lookupFor("tsll", []), "TSLL");
  assert.equal(lookupFor("brk.b", []), "BRK.B");
  assert.equal(lookupFor("spy", suggest("spy", SPY_HITS)), null); // SPY is a row already
  assert.equal(lookupFor("ge v", []), null);
  // A symbol's first letters with the stock under it still gets the offer: TSL is not TSLA.
  assert.equal(lookupFor("tsl", suggest("tsl", [stock("TSLA", "Tesla, Inc.")])), "TSL");
});

test("a company being typed is not offered as a ticker to check", () => {
  // Each of these was: the company on the first row, and "Check COREWEAVE" under it.
  assert.equal(lookupFor("coreweave", suggest("coreweave", [stock("CRWV", "CoreWeave, Inc. Class A")])), null); // too long for a ticker
  assert.equal(lookupFor("apple", suggest("apple", [stock("AAPL", "Apple Inc."), stock("APLE", "Apple Hospitality REIT, Inc.")])), null);
  assert.equal(lookupFor("nv", suggest("nv", NV_HITS)), null); // the start of NVIDIA and of nVent
  // With no company on the rows it could be one, so it is offered.
  assert.equal(lookupFor("apple", []), "APPLE");
  // Digits and long words are not how a US ticker is written.
  assert.equal(lookupFor("3m", []), null);
  assert.equal(lookupFor("alphabet", []), null);
});

test("only a plain no is a no: a name is not missing because the collector was busy", () => {
  assert.deepEqual(lookupVerdict({ ok: true, error: null }), { kind: "found" });
  assert.deepEqual(lookupVerdict({ ok: false, error: "Yahoo does not know this symbol (HTTP 404)" }), { kind: "missing" });
  assert.deepEqual(lookupVerdict({ ok: false, error: "not a ticker" }), { kind: "missing" });
  assert.deepEqual(lookupVerdict({ ok: false, error: "Yahoo is rate-limiting — paused" }), { kind: "unknown", why: "Yahoo is rate-limiting — paused" });
  assert.deepEqual(lookupVerdict({ ok: false, offline: { reason: "the collector did not answer in time" } }), {
    kind: "unknown",
    why: "the collector did not answer in time",
  });
  assert.deepEqual(lookupVerdict(null), { kind: "unknown", why: "no answer" });
  assert.deepEqual(lookupVerdict({ ok: false }), { kind: "unknown", why: "no data for this name" });
});
