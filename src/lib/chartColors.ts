"use client";

import { useSyncExternalStore } from "react";

/**
 * The colours the charts are drawn in: the interface's own, or "Josh".
 *
 * WHY (owner, 2026-11-11, with a screenshot of the charts they trade from: "on the charts
 * can we add a chart color theme option for default or Josh ... just for the chart
 * colors"). Josh is blue candles up and black down on light grey, a red dotted line at
 * the last price, no grid; the after-hours shaded blue and the pre-market sand, with
 * the candles in them at full strength (2026-11-12, measured off a second screenshot).
 * Default is what the chart has always done: the interface's green and pink on its own
 * ground, extended hours one neutral shade and their candles at half.
 *
 * ONLY THE CHART. The choice sets one attribute on the chart's area and the variables it
 * means are scoped there (globals.css, "the chart's own colours"), so the page round the
 * chart, the tables and the rest of the slide-out keep the interface's colours.
 *
 * ONE CHOICE FOR EVERY CHART, SO NOT `usePersisted`. That hook keeps a value per
 * component: the menu on one chart would leave a second chart on the same page (a
 * futures book with a slide-out open over it) in the old colours until it was mounted
 * again. This is one value with subscribers, and the browser's storage event carries it
 * to the other windows too, so a chart on a side screen changes with the one in front.
 */

export type ChartColors = "default" | "josh";

export const CHART_COLORS: ReadonlyArray<{ value: ChartColors; label: string }> = [
  { value: "default", label: "Default" },
  { value: "josh", label: "Josh" },
];

const KEY = "nt.chart.colors";

/** What is stored, as a choice: anything this build does not know is Default. Pure. */
export function parseChartColors(raw: string | null): ChartColors {
  if (raw === null) return "default";
  try {
    return JSON.parse(raw) === "josh" ? "josh" : "default";
  } catch {
    return "default";
  }
}

let current: ChartColors = "default";
let loaded = false;
const subs = new Set<() => void>();

function load(): void {
  loaded = true;
  try {
    current = parseChartColors(window.localStorage.getItem(KEY));
    // Another window chose: follow it.
    window.addEventListener("storage", (e) => {
      if (e.key !== KEY) return;
      const next = parseChartColors(e.newValue);
      if (next === current) return;
      current = next;
      subs.forEach((f) => f());
    });
  } catch {
    /* no storage: the default, for this visit */
  }
}

function subscribe(f: () => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

/** Read on the client only, so a chart mounted later starts in the stored colours. */
function snapshot(): ChartColors {
  if (!loaded && typeof window !== "undefined") load();
  return current;
}

export function useChartColors(): ChartColors {
  // The server's markup is always Default; the stored choice arrives with the first
  // client render after hydration, the way every other preference does (usePersisted).
  return useSyncExternalStore(subscribe, snapshot, () => "default");
}

export function setChartColors(v: ChartColors): void {
  if (!loaded && typeof window !== "undefined") load();
  if (v === current) return;
  current = v;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(v));
  } catch {
    /* applies to this visit; it just will not be remembered */
  }
  subs.forEach((f) => f());
}
