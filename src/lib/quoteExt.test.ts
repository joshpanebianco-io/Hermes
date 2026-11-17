import assert from "node:assert/strict";
import { test } from "node:test";
import type { IndexMovers, Quote } from "../types/terminal.ts";
import { shownMovers, shownQuote } from "./quoteExt.ts";

const spy = (ext: Quote["ext"]): Quote =>
  ({
    key: "SPY", symbol: "SPY", label: "SPY", name: "SPY", group: "core", fmt: "px", last: 754.37, prev: 757.12,
    chg: -2.75, pct: -0.36, high: null, low: null, range_pos: null, wk52_high: null, wk52_low: null, volume: null,
    currency: "USD", exchange: "PCX", quote_time: 1, feed: "closed", lag_min: 0, spark: [], ext,
  }) as Quote;

test("before the bell a board fund shows its pre-market price and move, tagged, with the session on the hover", () => {
  const s = shownQuote(spy({ kind: "pre", px: 749.89, pct: -0.59, at: Date.UTC(2026, 10, 16, 13, 16) / 1000 }));
  assert.equal(s.tag, "pre");
  assert.equal(s.q.last, 749.89);
  assert.equal(s.q.pct, -0.59);
  assert.equal(s.q.feed, "live");
  assert.equal(s.note, "Pre-market 749.89 (−0.59% against the last close), last trade 08:16 ET. The regular session closed 754.37 (−0.36% on the day).");
});

test("after the close it is the after hours, and in the session the quote is as it was", () => {
  assert.equal(shownQuote(spy({ kind: "post", px: 755.1, pct: 0.1, at: 0 })).tag, "AH");
  const plain = shownQuote(spy(null));
  assert.equal(plain.tag, null);
  assert.equal(plain.q.last, 754.37);
});

test("before the bell the index movers are the names' own pre-market moves", () => {
  const m: IndexMovers = {
    label: "Nasdaq 100", index: "NDX", as_of: null, covered_weight: 16, net_contribution: -0.14,
    members: [
      { symbol: "NVDA", name: "NVIDIA", sector: "", weight: 8.4, last: 162.85, pct: -2.01, contribution: -0.17, pre_pct: -2.92, pre_contribution: -0.2453 },
      { symbol: "QUIET", name: "Quiet", sector: "", weight: 0.5, last: 1, pct: 0.1, contribution: 0.0005, pre_pct: null, pre_contribution: null },
    ],
    pre_net: -0.245, pre_traded: 1,
  };
  const s = shownMovers(m);
  assert.equal(s.pre, true);
  assert.equal(s.m.net_contribution, -0.245);
  assert.deepEqual(s.m.members.map((x) => [x.pct, x.contribution]), [[-2.92, -0.2453], [null, 0]]);
  // In the session (no pre-market figures) the panel is as it was.
  assert.equal(shownMovers({ ...m, pre_net: null }).pre, false);
});
