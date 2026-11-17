import assert from "node:assert/strict";
import { test } from "node:test";
import type { DriverBook, DriverVote } from "../types/terminal.ts";
import { familyTag, sessionName, sheetOf } from "./driverSheet.ts";

const vote = (key: string, family: string | null, vote: DriverVote["vote"], live = true, value = "x"): DriverVote => ({
  key, label: key, layer: "macro", value, vote, note: `${key} note`, live, family,
});

/** NQ as the live board printed it on Mon 16 Nov, London's weights. */
const nq = (): DriverBook & { session_key: string } => ({
  key: "NQ", last: 27943, bias: null, score: 0, basis: "whole", coverage: 81, weight_label: "London's weight",
  session_key: "london",
  families: [
    { key: "structure", label: "Intraday structure", short: "Structure", weight: 44, score: 0, live: 2, total: 2 },
    { key: "rates", label: "Rates & dollar", short: "Rates & dollar", weight: 31, score: 0, live: 1, total: 2 },
    { key: "catalysts", label: "Catalysts", short: "Catalysts", weight: 19, score: null, live: 0, total: 2 },
    { key: "risk", label: "Risk appetite", short: "Risk", weight: 6, score: -50, live: 2, total: 3 },
    { key: "participation", label: "Participation", short: "Participation", weight: 0, score: null, live: 0, total: 2 },
  ],
  agree: 0, against: 0, neutral: 3, live: 5, cannot_vote: 6, total: 11, grade: "none", max_conviction: 1,
  votes: [
    vote("yields", "rates", "neutral", false),
    vote("dollar", "rates", "neutral"),
    vote("credit", "risk", "short"),
    vote("vix_dir", "risk", "neutral"),
    vote("vix_curve", "risk", "neutral", false),
    vote("prints", "catalysts", "neutral", false),
    vote("hw_prints", "catalysts", "neutral", false),
    vote("gamma", null, "neutral", true, "negative γ · below flip 28,238"),
    vote("value", "structure", "neutral"),
    vote("session", "structure", "neutral"),
    vote("sectors", "participation", "neutral", false),
    vote("leaders", "participation", "neutral", false),
    vote("event_risk", null, "neutral", true, "4 since the close"),
  ],
  macro_lean: null, structure_lean: null, conflict: false, regime: "NEG", treatment: "No lean on NQ.",
  context: [{ key: "cot", label: "COT · Leveraged funds", value: "net short", note: "As of Tue." }],
});

test("the factors are the report's, heaviest first, a family off this session after them, events last", () => {
  const s = sheetOf(nq());
  assert.deepEqual(
    s.factors.map((f) => [f.name, f.sub, f.weight, f.tag]),
    [
      ["Volume profile & structure", null, 44, "Neutral"],
      ["Macro", "rates & dollar", 31, "Neutral"],
      ["News & data", null, 19, "Nothing yet"],
      ["Risk appetite", null, 6, "Bearish"],
      ["Participation", "sectors & leaders", 0, "Not weighed now"],
      ["Geopolitics & events", "lowers conviction, not a side", null, "4 stories"],
    ],
  );
  assert.equal(s.factors.at(-1)?.lean, "damp");
  // Every read the score is made of is under its factor, and none twice.
  assert.equal(s.factors.flatMap((f) => f.reads).length, 12);
});

test("dealer gamma is context, never a factor, and heads the context rows", () => {
  const s = sheetOf(nq());
  assert.ok(!s.factors.some((f) => f.reads.some((r) => r.key === "gamma")));
  assert.deepEqual(s.context.map((c) => c.label), ["gamma", "COT · Leveraged funds"]);
  assert.equal(s.context[0].value, "negative γ · below flip 28,238");
});

test("silver and crude keep their own names for a family", () => {
  const cl = { ...nq(), key: "CL" };
  assert.deepEqual(
    sheetOf(cl).factors.slice(0, 4).map((f) => [f.name, f.sub]),
    [["Volume profile & structure", null], ["Macro", "dollar & products"], ["Inventories & data", null], ["Demand", "credit & copper"]],
  );
  assert.equal(sheetOf({ ...nq(), key: "SIL" }).factors[1].sub, "rates, dollar & metals");
});

test("the tag is the report's rule: a level family with reads both ways is Mixed, a shut one is not live", () => {
  const r = (vote: DriverVote["vote"], live = true) => ({ key: "k", label: "k", value: "", note: "", vote, live });
  assert.deepEqual(familyTag("rates", 0, [r("long"), r("short")]), { lean: "mixed", tag: "Mixed" });
  assert.deepEqual(familyTag("rates", 0, [r("neutral")]), { lean: "neutral", tag: "Neutral" });
  assert.deepEqual(familyTag("rates", 40, [r("long")]), { lean: "bull", tag: "Bullish" });
  assert.deepEqual(familyTag("rates", null, [r("long", false)]), { lean: "none", tag: "Not live yet" });
  assert.deepEqual(familyTag("catalysts", null, [r("neutral", false)]), { lean: "none", tag: "Nothing yet" });
});

test("the session is named from its key, or from the label when an older board has none", () => {
  assert.equal(sessionName({ weight_label: "London's weight", session_key: "london" }), "London");
  assert.equal(sessionName({ weight_label: "x", session_key: "ny_pre" }), "New York pre-open");
  assert.equal(sessionName({ weight_label: "Asia's weight" }), "Asia");
  assert.equal(sessionName({ weight_label: "the session's weight" }), "session");
});
