import assert from "node:assert/strict";
import { test } from "node:test";
import type { BoxRow, DriverBook, DriverVote } from "../types/terminal.ts";
import { futuresBrief, nextEvent, sessionStrip, weightsWord } from "./futDash.ts";

const v = (label: string, family: string, vote: DriverVote["vote"], value: string, live = true): DriverVote => ({
  key: label, label, layer: "macro", value, vote, note: "", live, family,
});

const book = (key: string, bias: DriverBook["bias"], score: number, grade: DriverBook["grade"], votes: DriverVote[] = []): DriverBook =>
  ({
    key, last: 1, bias, score, basis: "whole", coverage: 80, weight_label: "the New York pre-open's weight",
    families: [
      { key: "catalysts", label: "", short: "", weight: 33, score: 0, live: 1, total: 1 },
      { key: "structure", label: "", short: "", weight: 20, score: 0, live: 1, total: 1 },
      { key: "risk", label: "", short: "", weight: 20, score: 0, live: 1, total: 1 },
    ],
    agree: 0, against: 0, neutral: 0, live: 1, cannot_vote: 0, total: 1, grade, max_conviction: 3, votes,
    macro_lean: null, structure_lean: null, conflict: false, regime: null, treatment: "", context: [],
  }) as DriverBook;

const score = (b: DriverBook) => b.score;

test("the brief: where the five lean, the strongest and what carries it, and a session-type call", () => {
  const books = {
    NQ: book("NQ", "short", -30, "moderate"),
    ES: book("ES", "short", -20, "weak"),
    GC: book("GC", "short", -17, "weak"),
    SIL: book("SIL", "short", -11, "weak"),
    CL: book("CL", "short", -54, "strong", [
      v("Value area", "structure", "short", "below (VAL 88.40)"),
      v("Copper", "risk", "short", "-1.29%"),
      v("Crude inventories", "catalysts", "short", "—", false),
      v("Dollar", "rates", "neutral", "+0.06%"),
    ]),
  };
  const leans = { NQ: { call: "none", word: "No lean" }, ES: { call: "trend", word: "Trend day more possible" } };
  assert.deepEqual(futuresBrief(books, leans, score), [
    "All five lean short for the New York pre-open.",
    "Crude is the strongest (-54, strong): value area below (VAL 88.40) and copper -1.29%.",
    "ES: trend day more possible.",
  ]);
});

test("a split board, a part-lean board and an empty one say so", () => {
  const split = futuresBrief({ NQ: book("NQ", "long", 35, "moderate"), GC: book("GC", "short", -40, "moderate"), CL: book("CL", null, 0, "none") }, {}, score);
  assert.equal(split[0], "Split: NQ long, gold short for the New York pre-open.");
  assert.equal(split[1], "Gold is the strongest (-40, moderate).");
  // A figure of several parts reads in brackets.
  const cl = futuresBrief({ CL: book("CL", "short", -54, "strong", [v("Products", "risk", "short", "gasoline -0.96% · heating oil -1.46%")]) }, {}, score);
  assert.equal(cl[1], "Crude is the strongest (-54, strong): products (gasoline -0.96% · heating oil -1.46%).");
  const part = futuresBrief({ NQ: book("NQ", "short", -12, "weak"), ES: book("ES", null, -3, "none"), GC: book("GC", null, 0, "none") }, {}, score);
  assert.equal(part[0], "NQ leans short, ES and gold have no lean for the New York pre-open.");
  const none = futuresBrief({ NQ: book("NQ", null, 0, "none") }, {}, score);
  assert.deepEqual(none, ["No lean on any of the five for the New York pre-open."]);
  assert.deepEqual(futuresBrief({}, {}, score), ["The driver board has not been read yet."]);
  assert.equal(weightsWord("London's weight"), "London");
});

const box = (key: BoxRow["key"], label: string, start: string, end: string, open: boolean, next: BoxRow["next"], min: number): BoxRow => ({
  key, label, open, start_et: start, end_et: end, next, next_min: min, opens_utc: "", closes_utc: "",
});
const BOXES = [
  box("asia", "Asia", "20:00", "00:00", false, "opens", 721),
  box("london", "London", "02:00", "05:00", false, "opens", 1081),
  box("premkt", "Pre-market", "04:00", "09:30", true, "closes", 91),
  box("ny", "New York", "09:30", "16:00", false, "opens", 91),
];

test("the session strip: done, trading now, or still to come in the futures day", () => {
  assert.deepEqual(
    sessionStrip(BOXES, "07:59").map((b) => [b.key, b.state, b.at]),
    [["asia", "done", "20:00"], ["london", "done", "02:00"], ["premkt", "now", "09:30"], ["ny", "next", "09:30"]],
  );
  // After the 18:00 reopen a new futures day begins: everything is to come.
  const evening = BOXES.map((b) => ({ ...b, open: false }));
  assert.deepEqual(sessionStrip(evening, "18:30").map((b) => b.state), ["next", "next", "next", "next"]);
  // Between New York's close and the reopen, the day is done.
  assert.deepEqual(sessionStrip(evening, "17:00").map((b) => b.state), ["done", "done", "done", "done"]);
});

test("the next thing the clock does: an opening before a closing at the same minute", () => {
  assert.deepEqual(nextEvent(BOXES), { label: "New York", next: "opens", min: 91 });
  assert.equal(nextEvent([]), null);
});
