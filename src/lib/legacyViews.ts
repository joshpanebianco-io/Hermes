"use client";

import { useSyncExternalStore } from "react";

/*
 * THE OLD STOCKS VIEWS, FOR A WEEK (2026-11-13). Setups, Breakouts, Extended hours and
 * Day 2/3 gave way to the one Today list (lib/tabs.ts SCAN_VIEWS). While Today settles
 * they can be shown again from Settings → Interface; the strip, the sidebar and the
 * Terminal all read this one switch, so it is a store and not a per-component state.
 * Off by default. Kept in the browser, like the chart colours.
 */

const KEY = "nt.scan.legacy";
const subs = new Set<() => void>();
let current = false;
let loaded = false;

function load(): void {
  loaded = true;
  try {
    current = JSON.parse(window.localStorage.getItem(KEY) ?? "false") === true;
    window.addEventListener("storage", (e) => {
      if (e.key !== KEY) return;
      current = e.newValue === "true";
      subs.forEach((f) => f());
    });
  } catch {
    /* no storage: off, for this visit */
  }
}

function subscribe(f: () => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

function snapshot(): boolean {
  if (!loaded && typeof window !== "undefined") load();
  return current;
}

export function useLegacyViews(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}

export function setLegacyViews(on: boolean): void {
  if (!loaded && typeof window !== "undefined") load();
  if (on === current) return;
  current = on;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(on));
  } catch {
    /* applies to this visit */
  }
  subs.forEach((f) => f());
}
