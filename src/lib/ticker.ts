import { useSyncExternalStore } from "react";
import { notePinned, noteUnpinned } from "@/lib/pins";

/**
 * Open any ticker from anywhere: a row in any table, the search box, an alert.
 *
 * A small store rather than a context, for the same reason Hermes's opener is a
 * window event (lib/ask/open.ts): the slide-out is mounted once beside the page,
 * and what opens it sits in different branches of the tree.
 */

let current: string | null = null;
const subs = new Set<() => void>();

function set(v: string | null): void {
  if (current === v) return;
  current = v;
  subs.forEach((f) => f());
}

export function openTicker(sym: string): void {
  set(sym.trim().toUpperCase());
}

export function closeTicker(): void {
  set(null);
}

function subscribe(f: () => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

export function useTicker(): string | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}

export const OPEN_SEARCH_EVENT = "hermes:search";

export function openSearch(): void {
  window.dispatchEvent(new Event(OPEN_SEARCH_EVENT));
}

/**
 * Always on the list, and nobody's favourite (server sources/scanner.BENCHMARKS): the
 * funds on the S&P 500, the Nasdaq 100 and the Russell 2000. The Scanner's Index chip
 * is this set.
 */
export const BENCHMARKS: ReadonlySet<string> = new Set(["SPY", "QQQ", "IWM"]);

/**
 * Add a name to the favourites, or take it off. Null on success, or why not. The
 * last favourite can go (owner, 2026-11-13: "reset it so nothing is favourited"):
 * the benchmarks keep the list, and the store, from ever being empty.
 */
export async function togglePin(sym: string): Promise<string | null> {
  if (BENCHMARKS.has(sym)) return `${sym} is a benchmark: always on the list, never a favourite`;
  try {
    const got = (await (await fetch("/api/scanner/watchlist", { cache: "no-store" })).json()) as {
      symbols?: string[];
      error?: string;
    };
    if (!got.symbols) return got.error ?? "could not read the list";
    const has = got.symbols.includes(sym);
    const next = has ? got.symbols.filter((s) => s !== sym) : [...got.symbols, sym];
    const r = await fetch("/api/scanner/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: next }),
    });
    const after = (await r.json()) as { error?: string; rejected?: string[] };
    if (!r.ok || after.error) return after.error ?? `HTTP ${r.status}`;
    if (after.rejected?.includes(sym)) return `${sym} was refused`;
    // An unpin is said out loud and can be undone (lib/pins.ts); a pin clears the
    // name from the ones offered back. Either way the pages read the list again.
    if (has) noteUnpinned({ sym, index: got.symbols.indexOf(sym), at: Date.now() });
    else notePinned(sym);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : "request failed";
  }
}

/** Put a name on today's list. Null on success, or why not. */
export async function trackName(sym: string): Promise<string | null> {
  try {
    const r = await fetch("/api/scanner/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sym }),
    });
    const got = (await r.json()) as { ok?: boolean; error?: string | null };
    return got.ok ? null : (got.error ?? `HTTP ${r.status}`);
  } catch (e) {
    return e instanceof Error ? e.message : "request failed";
  }
}
