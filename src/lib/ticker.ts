import { useSyncExternalStore } from "react";

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

/** Add a name to the pinned list, or take it off. Null on success, or why not. */
export async function togglePin(sym: string): Promise<string | null> {
  try {
    const got = (await (await fetch("/api/scanner/watchlist", { cache: "no-store" })).json()) as {
      symbols?: string[];
      error?: string;
    };
    if (!got.symbols) return got.error ?? "could not read the list";
    const has = got.symbols.includes(sym);
    if (has && got.symbols.length === 1) return "the list cannot be empty";
    const next = has ? got.symbols.filter((s) => s !== sym) : [...got.symbols, sym];
    const r = await fetch("/api/scanner/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: next }),
    });
    const after = (await r.json()) as { error?: string; rejected?: string[] };
    if (!r.ok || after.error) return after.error ?? `HTTP ${r.status}`;
    if (after.rejected?.includes(sym)) return `${sym} was refused`;
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
