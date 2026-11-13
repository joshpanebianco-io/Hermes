// node --experimental-strip-types --test src/lib/walls.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { wallRank } from "./walls.ts";

test("a wall's rank is triangles: three for the heaviest, one for the third", () => {
  assert.deepEqual(wallRank("Call wall"), { word: "Call wall", n: 3, up: true });
  assert.deepEqual(wallRank("Call wall 2"), { word: "Call wall", n: 2, up: true });
  assert.deepEqual(wallRank("Call wall 3"), { word: "Call wall", n: 1, up: true });
  assert.deepEqual(wallRank("Put wall"), { word: "Put wall", n: 3, up: false });
  assert.deepEqual(wallRank("Put wall 3"), { word: "Put wall", n: 1, up: false });
});

test("any other level is not a wall", () => {
  assert.equal(wallRank("Gamma flip"), null);
  assert.equal(wallRank("Prior settle"), null);
  assert.equal(wallRank("PDH"), null);
});
