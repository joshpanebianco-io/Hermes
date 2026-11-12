// node --experimental-strip-types --test src/lib/tabs.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { SCAN_VIEWS, SCAN_VIEW_KEYS, TAB_KEYS, askTab, deskOf, pageTitle, resolveTab, tabLabel } from "./tabs.ts";
import { UI_CLASSES, parseUi, uiClass } from "./ui.ts";

test("the bar's pages, in bar order", () => {
  assert.deepEqual(TAB_KEYS, ["dashboard", "terminal", "sectors", "scanner", "futures", "hermes", "settings"]);
  assert.equal(tabLabel("terminal"), "Macro");
  assert.equal(new Set(TAB_KEYS).size, TAB_KEYS.length);
  // The stocks page reads "Stocks" on the bar and in the title; its key did not change,
  // so an old link and the remembered tab still open it.
  assert.equal(tabLabel("scanner"), "Stocks");
  assert.equal(pageTitle("scanner"), "HERMES · Stocks");
  assert.deepEqual(resolveTab("scanner"), { tab: "scanner" });
});

test("the Scanner's views, once each, every one with a name and a hover", () => {
  assert.deepEqual(SCAN_VIEW_KEYS, ["setups", "breakouts", "extended", "day23", "index", "log", "plan"]);
  for (const v of SCAN_VIEWS) assert.ok(v.label && v.title, v.key);
});

test("Sectors is a tab of its own, between Macro and the Scanner, and no longer one of the Scanner's views", () => {
  assert.equal(TAB_KEYS.indexOf("sectors"), TAB_KEYS.indexOf("terminal") + 1);
  assert.equal(TAB_KEYS.indexOf("sectors"), TAB_KEYS.indexOf("scanner") - 1);
  assert.ok(!(SCAN_VIEW_KEYS as readonly string[]).includes("sectors"));
  assert.equal(askTab("sectors"), "sectors");
});

test("Futures sits after the Scanner, and Structure's old links land on it", () => {
  assert.equal(TAB_KEYS.indexOf("futures"), TAB_KEYS.indexOf("scanner") + 1);
  assert.deepEqual(resolveTab("structure"), { tab: "futures" });
  assert.equal(askTab("futures"), "structure");
  assert.equal(askTab("scanner", "index"), "tape");
  assert.equal(askTab("scanner", "setups"), "scanner");
});

test("Analysis is off the bar: each written note lives with its desk, and old links find it", () => {
  assert.ok(!(TAB_KEYS as readonly string[]).includes("analysis"));
  // The futures brief was always the Futures section's Brief view too.
  assert.deepEqual(resolveTab("report"), { tab: "futures", fut: "brief" });
  assert.deepEqual(resolveTab("analysis"), { tab: "futures", fut: "brief" });
  assert.deepEqual(resolveTab("analysis", "futures"), { tab: "futures", fut: "brief" });
  // The written game plan is the Scanner's last view.
  assert.deepEqual(resolveTab("plan"), { tab: "scanner", scan: "plan" });
  assert.deepEqual(resolveTab("analysis", "stocks"), { tab: "scanner", scan: "plan" });
  assert.equal(SCAN_VIEW_KEYS.at(-1), "plan");
  assert.equal(resolveTab("nonsense"), null);
  assert.equal(resolveTab(undefined), null);
  // Hermes is told each note by the name the collector already knows it by.
  assert.equal(askTab("futures", undefined, "brief"), "report");
  assert.equal(askTab("futures", undefined, "NQ"), "structure");
  assert.equal(askTab("scanner", "plan"), "plan");
});

test("a question to Hermes is labelled with the side of the terminal last read", () => {
  assert.equal(deskOf("futures"), "futures");
  for (const t of ["dashboard", "scanner", "sectors"] as const) assert.equal(deskOf(t), "stocks");
  // Macro belongs to both, and Hermes and Settings to neither: the label stays as it was.
  for (const t of ["terminal", "hermes", "settings"] as const) assert.equal(deskOf(t), null);
});

test("Luminous Glass rides on Quiet: both classes, and an unknown cookie is Quiet", () => {
  assert.equal(parseUi("lum"), "lum");
  assert.equal(parseUi("glass"), "quiet");
  assert.equal(parseUi(undefined), "quiet");
  assert.equal(uiClass("lum"), "ui-qt ui-lum");
  assert.equal(uiClass("quiet"), "ui-qt");
});

test("Sidebar rides on Luminous: all three classes, so its pages are Luminous's cards", () => {
  assert.equal(parseUi("side"), "side");
  assert.equal(uiClass("side"), "ui-qt ui-lum ui-side");
  // A live switch takes off what the new mode does not wear, and only that.
  const wears = (m: "quiet" | "lum" | "side") => UI_CLASSES.filter((c) => uiClass(m).split(" ").includes(c));
  assert.deepEqual(wears("side"), ["ui-qt", "ui-lum", "ui-side"]);
  assert.deepEqual(wears("lum"), ["ui-qt", "ui-lum"]);
  assert.deepEqual(wears("quiet"), ["ui-qt"]);
  // A cookie from a build that knew other names is Quiet, never a half-dressed page.
  assert.equal(parseUi("sidebar"), "quiet");
});

test("Classic is gone: a cookie that still names it opens Quiet, and the page always wears Quiet's class", () => {
  assert.equal(parseUi("classic"), "quiet");
  for (const m of ["quiet", "lum", "side"] as const) assert.ok(uiClass(m).split(" ").includes("ui-qt"));
});
