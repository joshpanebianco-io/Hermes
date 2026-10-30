// node --experimental-strip-types --test src/lib/ask/router.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { localAnswer, routeQuestion } from "./router.ts";

const WATCH = ["AMZN", "SPY", "QQQ", "NVDA", "ARM", "SHOP"];
const route = (q: string, desk: "futures" | "stocks" | null = null) => routeQuestion(q, { desk, sym: null, watchlist: WATCH });

test("a named watchlist ticker is a full question on the stocks desk", () => {
  const r = route("What is AMZN's setup right now?");
  assert.equal(r.tier, "full");
  assert.equal(r.desk, "stocks");
  const dollar = route("$shop worth a look?", "futures");
  assert.equal(dollar.desk, "stocks");
});

test("a ticker's letters in prose are not a ticker", () => {
  // "arm" the word, not ARM the name; the reader's desk decides.
  const r = route("will the arm of the move extend?", "futures");
  assert.equal(r.desk, "futures");
});

test("futures words pick the futures set and a why makes it full", () => {
  const r = route("Why is NQ down overnight?", "stocks");
  assert.equal(r.tier, "full");
  assert.equal(r.desk, "futures");
});

test("a glance check is quick, on the reader's desk unless it names the other", () => {
  const r = route("is the pre-market open?", "stocks");
  assert.equal(r.tier, "quick");
  assert.equal(r.desk, "stocks");
  assert.equal(route("is london open?", "stocks").tier, "quick");
  assert.equal(route("is london open?", "stocks").desk, "futures");
  assert.equal(route("what's vix at?").tier, "quick");
  assert.equal(route("what's vix at?").desk, "both");
});

test("a follow-up is never quick, and a read-of-the-desk word is full on its own", () => {
  const r = routeQuestion("and ES?", { desk: "futures", sym: null, watchlist: WATCH, followUp: true });
  assert.equal(r.tier, "full");
  assert.equal(r.desk, "futures");
  assert.equal(route("so what's the overall lean?").tier, "full");
  assert.equal(route("macro and structure, net?").tier, "full");
});

test("length alone makes a question full", () => {
  const long = "so I was thinking about the way the morning went and whether any of it changes how I should sit tomorrow";
  assert.equal(route(long).tier, "full");
});

test("both desks' words ride both tool sets", () => {
  assert.equal(route("compare NQ's levels with the scanner's top names").desk, "both");
});

const glance = {
  as_of_et: "2026-10-30T02:39:36.917849-04:00",
  phase: "Frankfurt session",
  boxes_open: [] as string[],
  strip: [
    { key: "NQ", last: 28970, pct: -2.0025, feed: "delayed" },
    { key: "VIX", last: 17.2, pct: 1.7149, feed: "closed" },
    { key: "BTC", last: 78420.94, pct: 0.81, feed: "live" },
  ],
};

test("the phase and a box answer locally, from the glance", () => {
  assert.equal(localAnswer("what session is it?", glance), "Frankfurt session, at 02:39 ET. No session box is open.");
  assert.equal(localAnswer("is london open", glance), "No. Frankfurt session, at 02:39 ET; no box is open.");
  assert.equal(localAnswer("Is Asia open now?", { ...glance, boxes_open: ["Asia"] }), "Yes. Frankfurt session, at 02:39 ET; open: Asia.");
});

test("a strip quote answers locally with its feed, and a name off the strip does not", () => {
  assert.equal(localAnswer("what's NQ at?", glance), "NQ 28,970 (-2.00%) at 02:39 ET, delayed feed.");
  assert.equal(localAnswer("where is vix trading", glance), "VIX 17.2 (+1.71%) at 02:39 ET, closed feed.");
  assert.equal(localAnswer("what is bitcoin doing", glance), "BTC 78,420.94 (+0.81%) at 02:39 ET.");
  assert.equal(localAnswer("what's AMZN at?", glance), null);
});

test("anything with more in it falls through to the model", () => {
  assert.equal(localAnswer("what's NQ at and why?", glance), null);
  assert.equal(localAnswer("is london open and what does that mean for ES?", glance), null);
  assert.equal(localAnswer("what session is it in sydney", glance), null);
});
