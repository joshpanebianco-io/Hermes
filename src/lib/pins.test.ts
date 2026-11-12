// node --experimental-strip-types --test src/lib/pins.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { KEEP, KEEP_MS, putBack, readUnpins, withUnpin, withoutUnpin } from "./pins.ts";

const NOW = Date.UTC(2026, 10, 11, 4, 0, 0);
const u = (sym: string, index: number, agoMin: number) => ({ sym, index, at: NOW - agoMin * 60_000 });

test("a name goes back where it left, or at the end of a shorter list", () => {
  const list = ["SPY", "QQQ", "AAPL", "TSLA"];
  // NVDA sat after AAPL, at 3.
  assert.deepEqual(putBack(list, { sym: "NVDA", index: 3 }), ["SPY", "QQQ", "AAPL", "NVDA", "TSLA"]);
  assert.deepEqual(putBack(list, { sym: "NVDA", index: 0 }), ["NVDA", "SPY", "QQQ", "AAPL", "TSLA"]);
  // The list has lost names since: it goes on the end rather than past it.
  assert.deepEqual(putBack(["SPY"], { sym: "NVDA", index: 11 }), ["SPY", "NVDA"]);
  assert.deepEqual(putBack([], { sym: "NVDA", index: -4 }), ["NVDA"]);
  // Already pinned again by another hand: nothing moves and nothing doubles.
  assert.deepEqual(putBack(["SPY", "NVDA", "QQQ"], { sym: "NVDA", index: 0 }), ["SPY", "NVDA", "QQQ"]);
  // The list handed in is never changed.
  assert.deepEqual(list, ["SPY", "QQQ", "AAPL", "TSLA"]);
});

test("the week's unpins are kept newest first, a name once", () => {
  let list = withUnpin([], u("NVDA", 11, 30));
  list = withUnpin(list, u("GEV", 33, 20));
  assert.deepEqual(list.map((x) => x.sym), ["GEV", "NVDA"]);
  // Unpinned again later: it moves to the front with its new place, not listed twice.
  list = withUnpin(list, u("NVDA", 4, 5));
  assert.deepEqual(list.map((x) => [x.sym, x.index]), [["NVDA", 4], ["GEV", 33]]);
  assert.deepEqual(withoutUnpin(list, "NVDA").map((x) => x.sym), ["GEV"]);
  assert.deepEqual(withoutUnpin(list, "AAPL").length, 2);
  // No more than KEEP are held.
  let many: ReturnType<typeof withUnpin> = [];
  for (let i = 0; i < KEEP + 5; i++) many = withUnpin(many, u(`S${i}`, i, KEEP + 5 - i));
  assert.equal(many.length, KEEP);
  assert.equal(many[0].sym, `S${KEEP + 4}`);
});

test("what storage holds is read back without the old, the malformed or the unparseable", () => {
  const good = [u("NVDA", 11, 30), u("GEV", 33, 600)];
  const raw = JSON.stringify([
    good[1],
    good[0],
    { sym: "OLD", index: 2, at: NOW - KEEP_MS - 1 },
    { sym: "", index: 2, at: NOW },
    { sym: "BAD", index: 1.5, at: NOW },
    { sym: "NOAT", index: 1 },
    "NVDA",
    null,
  ]);
  assert.deepEqual(readUnpins(raw, NOW), good);
  assert.deepEqual(readUnpins(null, NOW), []);
  assert.deepEqual(readUnpins("not json", NOW), []);
  assert.deepEqual(readUnpins('{"sym":"NVDA"}', NOW), []);
  // A clock set forward and back again must not strand an entry "from the future".
  assert.deepEqual(readUnpins(JSON.stringify([{ sym: "FUT", index: 0, at: NOW + 3_600_000 }]), NOW), []);
});
