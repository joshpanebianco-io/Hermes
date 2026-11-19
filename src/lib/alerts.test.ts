// node --experimental-strip-types --test src/lib/alerts.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_ALERTS, parseAlertPrefs } from "./alerts.ts";

test("a choice saved before the (V) existed takes it on, and keeps what it switched off", () => {
  // Saved 2026-11-18: (L) and the breakout on, the (E) switched off, Near never asked for.
  const old = parseAlertPrefs(JSON.stringify({ on: true, desktop: false, sound: true, kinds: ["L", "BO"], minScore: 40 }));
  assert.deepEqual(old.kinds, ["L", "BO", "V"]);
  assert.equal(old.minScore, 40);
});

test("a choice saved since keeps the (V) off when it was switched off", () => {
  const now = parseAlertPrefs(
    JSON.stringify({ on: true, desktop: false, sound: true, kinds: ["L", "E"], minScore: 0, known: ["L", "E", "V", "BO", "NEAR"] }),
  );
  assert.deepEqual(now.kinds, ["L", "E"]);
});

test("nothing saved is the defaults, the (V) among them", () => {
  assert.deepEqual(parseAlertPrefs(null), DEFAULT_ALERTS);
  assert.ok(DEFAULT_ALERTS.kinds.includes("V"));
});
