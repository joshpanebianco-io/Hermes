// node --experimental-strip-types --test src/lib/intParam.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { intParam } from "./intParam.ts";

test("a missing or empty value takes the fallback, not zero", () => {
  assert.equal(intParam(null, 200, 500), 200);
  assert.equal(intParam("", 200, 500), 200);
  assert.equal(intParam("  ", 200, 500), 200);
});

test("a real value is clamped, and zero is still a value", () => {
  assert.equal(intParam("100", 200, 500), 100);
  assert.equal(intParam("9000", 200, 500), 500);
  assert.equal(intParam("0", 200, 500), 0);
  assert.equal(intParam(String(Number.MAX_SAFE_INTEGER), 0, Number.MAX_SAFE_INTEGER), Number.MAX_SAFE_INTEGER);
});

test("anything else falls back", () => {
  assert.equal(intParam("-1", 200, 500), 200);
  assert.equal(intParam("1.5", 200, 500), 200);
  assert.equal(intParam("abc", 200, 500), 200);
});
