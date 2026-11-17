import assert from "node:assert/strict";
import { test } from "node:test";
import type { HeatCard } from "../types/dashboard.ts";
import { cardNote, cardPct, cardRs, etHm, phaseLine, weekday } from "./sectorPhase.ts";

const card = (over: Partial<HeatCard> = {}): HeatCard =>
  ({
    key: "XLK", label: "Technology", last: 170.28, day_pct: -2.008, week_pct: 1, month_pct: 0.5,
    rs_day: -1.65, rs_week: 0.2, rs_month: 0.1, kind: "sector", top: true, parent: null, list: "sector",
    names: 2, day: { up: 0, down: 2, median: -1, leaders: [] }, week: { up: 2, down: 0, median: 3, leaders: [] },
    month: { up: 1, down: 1, median: 0, leaders: [] },
    ext_pct: -1.76, rs_ext: -1.25, ext_at: Date.UTC(2026, 10, 16, 12, 3) / 1000, ext_bars: 13,
    ...over,
  }) as HeatCard;

test("before the bell a card's day is its pre-market move, and its distance from SPY's", () => {
  assert.equal(cardPct(card(), "pre", "day"), -1.76);
  assert.equal(cardRs(card(), "pre", "day"), -1.25);
  // The week and the month are to the last close; in the session the day is the session's.
  assert.equal(cardPct(card(), "pre", "week"), 1);
  assert.equal(cardPct(card(), "rth", "day"), -2.008);
  // A fund with no pre-market trade yet has no figure, not Friday's.
  assert.equal(cardPct(card({ ext_pct: null }), "pre", "day"), null);
});

test("beside it, the last session's move before the bell and the after hours after the close", () => {
  const pre = cardNote(card(), "pre", "day", "2026-11-13");
  assert.equal(pre?.text, "Fri −2.01%");
  assert.match(pre?.title ?? "", /Last trade 07:03 ET, in 13 of the five-minute bars since 04:00/);
  const none = cardNote(card({ ext_pct: null, ext_at: null }), "pre", "day", "2026-11-13");
  assert.match(none?.title ?? "", /No pre-market trade in XLK yet/);
  const post = cardNote(card({ ext_pct: 0.35 }), "post", "day", "2026-11-16");
  assert.equal(post?.text, "AH +0.35%");
  assert.equal(cardNote(card({ ext_pct: null }), "post", "day", "2026-11-16"), null);
  assert.equal(cardNote(card(), "rth", "day", "2026-11-16"), null);
  assert.equal(cardNote(card(), "pre", "week", "2026-11-13"), null);
});

test("the header says which stretch the cards read", () => {
  const name = (iso: string) => weekday(iso);
  const at = Date.UTC(2026, 10, 16, 12, 2) / 1000;
  assert.equal(phaseLine({ cards_phase: "pre", cards_day: "2026-11-13", day: "2026-11-16", ext_day: "2026-11-16", ext_at: at }, name), "Cards read Mon pre-market · SPY last traded 07:02 ET");
  assert.equal(phaseLine({ cards_phase: "post", cards_day: "2026-11-13", day: "2026-11-16", ext_day: "2026-11-13", ext_at: Date.UTC(2026, 10, 14, 0, 55) / 1000 }, name), "Cards read Fri · after hours to 19:55 ET");
  assert.equal(phaseLine({ cards_phase: "rth", cards_day: "2026-11-13", day: "2026-11-16" }, name), "Cards read Mon");
  assert.equal(phaseLine({ cards_day: "2026-11-13", day: "2026-11-16" }, name), "Cards read Fri");
  assert.equal(etHm(null), "—");
});
