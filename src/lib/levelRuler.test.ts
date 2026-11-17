import assert from "node:assert/strict";
import { test } from "node:test";
import { fromLast, layoutRuler, MAX_LANES, priceText, RULER_PAD, type LevelMark } from "./levelRuler.ts";

// The Nasdaq's levels on the night the report was reworked: value low sits 20 under last.
const NQ: LevelMark[] = [
  { price: 29900, label: "Fri low", kind: "range" },
  { price: 30050, label: "Overnight low", kind: "range" },
  { price: 30100, label: "Value low", kind: "value" },
  { price: 30120, label: "Last", kind: "last" },
  { price: 30251, label: "POC", kind: "poc" },
  { price: 30400, label: "Value high", kind: "value" },
  { price: 30500, label: "Fri high", kind: "range" },
  { price: 30610, label: "Overnight high", kind: "range" },
];

test("the lowest level is at the left end, the highest at the right, the rest in proportion", () => {
  const r = layoutRuler(NQ, 800, 0);
  assert.ok(r);
  assert.equal(r.marks[0].x, RULER_PAD);
  assert.equal(r.marks.at(-1)?.x, 800 - RULER_PAD);
  assert.deepEqual(r.marks.map((m) => m.price), [29900, 30050, 30100, 30251, 30400, 30500, 30610]);
  const poc = r.marks.find((m) => m.kind === "poc");
  assert.equal(Math.round(poc?.x ?? 0), Math.round(RULER_PAD + ((30251 - 29900) / 710) * (800 - 2 * RULER_PAD)));
});

test("the last price is the dot on the line and not one of the labelled rows", () => {
  const r = layoutRuler(NQ, 800, 0);
  assert.ok(r?.last);
  assert.equal(r.last.price, 30120);
  assert.ok(!r.marks.some((m) => m.labels.includes("Last")));
  assert.ok(r.last.x > r.marks[2].x && r.last.x < r.marks[3].x);
});

test("the value area is the stretch between its low and its high", () => {
  const r = layoutRuler(NQ, 800, 0);
  assert.ok(r?.value);
  assert.equal(r.value[0], r.marks.find((m) => m.labels[0] === "Value low")?.x);
  assert.equal(r.value[1], r.marks.find((m) => m.labels[0] === "Value high")?.x);
  // With one end of it missing there is no stretch to draw.
  assert.equal(layoutRuler(NQ.filter((m) => m.label !== "Value high"), 800, 0)?.value, null);
});

test("no two labels on one row print over each other, wide or narrow", () => {
  for (const width of [1200, 800, 560, 420]) {
    const r = layoutRuler(NQ, width, 0);
    assert.ok(r);
    assert.ok(r.lanes <= MAX_LANES);
    for (let lane = 0; lane < r.lanes; lane++) {
      const row = r.marks.filter((m) => m.lane === lane).sort((a, b) => a.left - b.left);
      for (let i = 1; i < row.length; i++) {
        assert.ok(row[i].left >= row[i - 1].left + row[i - 1].width, `${width}px, row ${lane}`);
      }
    }
    for (const m of r.marks) assert.ok(m.left >= 0 && m.left + m.width <= width, `${width}px inside the line`);
  }
});

test("levels that bunch drop to the next row and the rest stay on the first", () => {
  const r = layoutRuler(NQ, 800, 0);
  assert.ok(r);
  const lane = (label: string) => r.marks.find((m) => m.labels[0] === label)?.lane;
  assert.equal(lane("Fri low"), 0);
  assert.equal(lane("Value low"), 1); // 50 points over the overnight low: under it
  assert.equal(lane("Value high"), 0);
  assert.equal(r.lanes, 2);
});

test("two levels at one printed price are one mark with both names", () => {
  const r = layoutRuler(
    [
      { price: 4000.2, label: "Fri low", kind: "range" },
      { price: 4100.04, label: "Fri high", kind: "range" },
      { price: 4100.0, label: "Overnight high", kind: "range" },
      { price: 4100.0, label: "POC", kind: "poc" },
    ],
    600,
    1,
  );
  assert.ok(r);
  assert.equal(r.marks.length, 2);
  assert.deepEqual(r.marks[1].labels, ["Fri high", "Overnight high", "POC"]);
  assert.equal(r.marks[1].kind, "poc");
});

test("one level, one price or no room is no ruler", () => {
  assert.equal(layoutRuler([NQ[0]], 800, 0), null);
  assert.equal(layoutRuler([NQ[0], { ...NQ[1], price: 29900 }], 800, 0), null);
  assert.equal(layoutRuler(NQ, 0, 0), null);
  assert.equal(layoutRuler([], 800, 0), null);
});

test("a price prints at the book's decimals and a distance carries its sign", () => {
  assert.equal(priceText(30251, 0), "30,251");
  assert.equal(priceText(49.8, 2), "49.80");
  assert.equal(fromLast(30500, 30120, 0), "+380");
  assert.equal(fromLast(30100, 30120, 0), "−20");
  assert.equal(fromLast(49.13, 49.8, 2), "−0.67");
  assert.equal(fromLast(30120, 30120, 0), "0");
  assert.equal(fromLast(30120, null, 0), null);
});
