// node --experimental-strip-types --test src/lib/futNews.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { WireItem } from "@/types/terminal";
import { bookStories, storyRead } from "./futNews.ts";

// Real headlines from the wire at 03:20 ET on Tue 10 Nov 2026, the morning the rule was built.
test("a story reaches the books its subject moves", () => {
  assert.deepEqual(storyRead("Fed Hike Odds Hit 84% After Bitcoin ETFs Lose $1.28 Billion"), { books: ["NQ", "ES", "GC", "SIL"], tags: ["Fed"] });
  assert.deepEqual(storyRead("Anthropic Prepares to Market IPO as Nvidia Scandal Stokes AI Jitters").books, ["NQ", "ES"]);
  assert.deepEqual(storyRead("Trump says more US attacks on Iran 'highly unlikely'"), { books: ["GC", "CL"], tags: ["Middle East", "War"] });
  assert.deepEqual(storyRead("Attack Targets Saudi Arabia's East-West Oil Pipeline in Medina").books, ["GC", "CL"]);
  assert.deepEqual(storyRead("Saudi Oil Tanker Firm Crossing Hormuz With US Coordination").books, ["GC", "CL"]);
  assert.deepEqual(storyRead("Singapore Central Bank Rolls Out Gold-Vaulting Services"), { books: ["GC", "SIL"], tags: ["Gold"] });
  assert.deepEqual(storyRead("Global markets soar amid tech rebound, cooling oil as all eyes turn to US inflation").books, ["NQ", "ES", "GC", "SIL", "CL"]);
  assert.deepEqual(storyRead("Falling Oil and Gas Prices Give Gilt Traders Some Relief"), { books: ["CL"], tags: ["Oil"] });
});

test("another country's central bank or data reaches none of them", () => {
  for (const t of [
    "ECB's Lane Sees December Hike as Prudent If Data Don't Shift",
    "BOE's Lombardelli does not rule out December rate hike, she tells the Guardian",
    "Hungary Inflation Accelerates for Third Month as Key Rate Steady",
    "Norway Core Prices Cool, Likely Reducing Pressure for Rate Hike",
    "6.7167: PBOC fixes USD/CNY reference rate, compared with 6.7188 previously",
    "Congress returns to a changed Washington after GOP's election wipeout",
    "One Nation dumps Victorian election candidate who praised Adolf Hitler as 'GOAT'",
  ]) {
    assert.deepEqual(storyRead(t).books, [], t);
  }
  // A US word makes the same themes American.
  assert.deepEqual(storyRead("US inflation cools in October, Treasuries rally").books, ["NQ", "ES", "GC", "SIL"]);
});

const item = (title: string, ts: number, impact: WireItem["impact"] = "medium"): WireItem => ({
  title,
  url: `u${ts}`,
  publisher: "Reuters",
  section: "",
  category: "markets",
  summary: "",
  utc: null,
  ts,
  impact,
  region: "us",
});

test("a book's stories are the ones that reach it, newest first, high and medium only", () => {
  const wire = [
    item("Fed Hike Odds Hit 84%", 100),
    item("Attack Targets Saudi Arabia's Oil Pipeline", 300, "high"),
    item("Gold climbs as the dollar slips", 200, "low"),
    item("ECB's Lane Sees December Hike as Prudent", 400),
    item("Micron soars on HBM demand", 500),
  ];
  assert.deepEqual(
    bookStories(wire, "CL").map((s) => [s.item.ts, s.tags]),
    [[300, ["Oil", "Middle East", "War"]]],
  );
  assert.deepEqual(
    bookStories(wire, "NQ").map((s) => s.item.ts),
    [100],
  );
  // No book: every story that reaches any of them.
  assert.deepEqual(
    bookStories(wire).map((s) => [s.item.ts, s.books]),
    [
      [300, ["GC", "CL"]],
      [100, ["NQ", "ES", "GC", "SIL"]],
    ],
  );
  assert.equal(bookStories(wire, "SIL", 0).length, 0);
});
