// node --experimental-strip-types --test src/lib/chartShade.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { extKind, shadeRuns } from "./chartShade.ts";

test("the collector's span decides, and a regular bar is in neither half", () => {
  assert.equal(extKind("pre", "08:00"), "pre");
  assert.equal(extKind("post", "17:00"), "post");
  assert.equal(extKind("rth", "10:00"), null);
  // A half day: the collector calls 13:30 after-hours, whatever the clock would say.
  assert.equal(extKind("post", "13:30"), "post");
  // An hour bar that holds the open is the session's.
  assert.equal(extKind("rth", "09:00"), null);
});

test("a bar in no span goes by New York's clock", () => {
  assert.equal(extKind(undefined, "03:10"), "pre");
  assert.equal(extKind(undefined, "09:29"), "pre");
  assert.equal(extKind(undefined, "09:30"), null);
  assert.equal(extKind(undefined, "15:59"), null);
  assert.equal(extKind(undefined, "16:00"), "post");
  assert.equal(extKind(undefined, "21:45"), "post");
  // Midnight as some engines write it.
  assert.equal(extKind(undefined, "24:05"), "pre");
  assert.equal(extKind(null, "00:05"), "pre");
});

test("the evening and the next morning are two runs, though no bar lies between them", () => {
  //             rth   rth   post    post    pre    pre    pre    rth   rth   post
  const kinds = [null, null, "post", "post", "pre", "pre", "pre", null, null, "post"] as const;
  const { runs, opens } = shadeRuns(kinds);
  assert.deepEqual(runs, [
    { from: 2, to: 3, kind: "post" },
    { from: 4, to: 6, kind: "pre" },
    { from: 9, to: 9, kind: "post" },
  ]);
  // The hairline stands on the bar the regular session opens on, once.
  assert.deepEqual(opens, [7]);
});

test("a series that starts or ends in extended hours, and one with none", () => {
  assert.deepEqual(shadeRuns(["pre", "pre", null]), { runs: [{ from: 0, to: 1, kind: "pre" }], opens: [2] });
  assert.deepEqual(shadeRuns([null, "post"]), { runs: [{ from: 1, to: 1, kind: "post" }], opens: [] });
  assert.deepEqual(shadeRuns([null, null]), { runs: [], opens: [] });
  assert.deepEqual(shadeRuns([]), { runs: [], opens: [] });
});
