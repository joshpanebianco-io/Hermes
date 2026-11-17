import assert from "node:assert/strict";
import { test } from "node:test";
import { shareUnchanged } from "./share.ts";

/** A poll's payload as the page gets it: fresh objects every time. */
const poll = (score: number, built: string) =>
  JSON.parse(
    JSON.stringify({
      ok: true,
      built_utc: built,
      calendar: [{ event: "CPI", ts: 1 }],
      drivers: { built_utc: built, books: { NQ: { bias: score > 0 ? "long" : null, score } } },
    }),
  ) as { ok: boolean; built_utc: string; calendar: unknown[]; drivers: { built_utc: string; books: { NQ: { bias: string | null; score: number } } } };

test("a block that moved is the new one; a block that did not keeps the object the page holds", () => {
  const first = poll(0, "03:19:35");
  const second = poll(37, "03:19:55");
  const got = shareUnchanged(first, second);
  assert.equal(got.drivers, second.drivers);
  assert.equal(got.drivers.books.NQ.score, 37);
  assert.equal(got.calendar, first.calendar);
  assert.equal(got.built_utc, "03:19:55");
});

test("asked twice it says the same thing: strict mode runs a state updater twice and keeps the second answer", () => {
  // The page stood at its first paint because the first run remembered the new poll
  // and the second then found every block equal to itself (2026-11-16).
  const first = poll(0, "03:19:35");
  const second = poll(37, "03:19:55");
  shareUnchanged(first, second);
  const kept = shareUnchanged(first, second);
  assert.equal(kept.drivers.books.NQ.score, 37);
  assert.equal(kept.drivers, second.drivers);
  assert.equal(kept.calendar, first.calendar);
});

test("poll after poll, each run twice, the page follows every one and comes back", () => {
  let held = poll(0, "03:19:35");
  for (const [score, built] of [[37, "03:19:55"], [0, "03:20:15"], [-64, "03:20:35"]] as const) {
    const next = poll(score, built);
    shareUnchanged(held, next);
    held = shareUnchanged(held, next);
    assert.equal(held.drivers.books.NQ.score, score);
    assert.equal(held.drivers.built_utc, built);
  }
});

test("a block the page did not have before is taken as it comes", () => {
  const first = poll(0, "03:19:35");
  const second = { ...poll(0, "03:19:55"), daytype: { books: {} } };
  const got = shareUnchanged(first, second);
  assert.equal(got.daytype, second.daytype);
});
