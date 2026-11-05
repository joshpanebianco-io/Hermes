// node --experimental-strip-types --test src/lib/ask/router.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { localAnswer, routeQuestion } from "./router.ts";

const WATCH = ["AMZN", "SPY", "QQQ", "NVDA", "ARM", "SHOP"];
const route = (q: string) => routeQuestion(q, { watchlist: WATCH });

test("a named watchlist ticker is a full question", () => {
  assert.equal(route("What is AMZN's setup right now?").tier, "full");
  assert.equal(route("$shop worth a look?").tier, "full");
});

test("a ticker's letters in prose are not a ticker", () => {
  assert.equal(route("how far will the arm extend").tier, "quick");
});

test("a why makes it full, and a check stays quick", () => {
  assert.equal(route("Why is NQ down overnight?").tier, "full");
  assert.equal(route("is the pre-market open?").tier, "quick");
  assert.equal(route("what's vix at?").tier, "quick");
});

test("every way of asking who reports thinks it through", () => {
  // These went out with no tools at all, and Hermes said it had no earnings.
  for (const q of ["who reports today?", "whats reporting today", "any reports today", "anything reporting tonight?", "did anyone beat", "earnings today"]) {
    assert.equal(route(q).tier, "full", q);
  }
});

test("a follow-up is never quick, and a read-of-the-desk word is full on its own", () => {
  const r = routeQuestion("and ES?", { watchlist: WATCH, followUp: true });
  assert.equal(r.tier, "full");
  assert.equal(route("so what's the overall lean?").tier, "full");
  assert.equal(route("macro and structure, net?").tier, "full");
});

test("length alone makes a question full", () => {
  const long = "so I was thinking about the way the morning went and whether any of it changes how I should sit tomorrow";
  assert.equal(route(long).tier, "full");
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
