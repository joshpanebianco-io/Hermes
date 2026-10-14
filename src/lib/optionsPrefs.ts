"use client";

import { useSyncExternalStore } from "react";

/**
 * The stocks desk's options preferences — Settings writes them, the Scanner
 * reads them, live (the same one-store construction as lib/alerts.ts, for the
 * same reason: usePersisted reads storage once per component).
 *
 * THE BUDGET IS OPTIONAL. With none set, the contract helper prints the
 * premium at risk per contract and stops there; with one, it also says how
 * many contracts that budget buys. It is a convenience for sizing, not advice,
 * and the helper's risk figure is an approximation it names (entry to stop,
 * re-marked through delta and gamma, plus half the bid-ask).
 */

export interface OptionsPrefs {
  /** Premium you are willing to lose on one trade, in dollars. Null = not set. */
  budget: number | null;
  /** Offer same-day (0DTE) contracts when one is listed — off, every name gets the weekly. */
  zeroDte: boolean;
}

export const DEFAULT_OPTIONS: OptionsPrefs = { budget: null, zeroDte: true };

const KEY = "nt.options";
let cache: OptionsPrefs | null = null;
const subs = new Set<() => void>();

function parse(raw: string | null): OptionsPrefs {
  if (!raw) return DEFAULT_OPTIONS;
  try {
    const v = JSON.parse(raw) as Partial<OptionsPrefs>;
    const b = typeof v.budget === "number" && Number.isFinite(v.budget) && v.budget > 0 ? v.budget : null;
    return { budget: b, zeroDte: typeof v.zeroDte === "boolean" ? v.zeroDte : true };
  } catch {
    return DEFAULT_OPTIONS;
  }
}

function read(): OptionsPrefs {
  if (cache) return cache;
  try {
    cache = parse(window.localStorage.getItem(KEY));
  } catch {
    cache = DEFAULT_OPTIONS;
  }
  return cache;
}

function subscribe(fn: () => void): () => void {
  subs.add(fn);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
      cache = null;
      fn();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    subs.delete(fn);
    window.removeEventListener("storage", onStorage);
  };
}

export function setOptionsPrefs(patch: Partial<OptionsPrefs>): void {
  cache = { ...read(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    /* applies to this session; it just will not persist */
  }
  for (const fn of subs) fn();
}

export function useOptionsPrefs(): OptionsPrefs {
  return useSyncExternalStore(subscribe, read, () => DEFAULT_OPTIONS);
}
