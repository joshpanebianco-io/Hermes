import { useSyncExternalStore } from "react";
import { closeTicker } from "@/lib/ticker";

/**
 * Which futures book's bias is out in the slide-out, if any (owner, 2026-11-16: "can we
 * make it so when you click on the bias the pop up card comes from the right similar to
 * when you click on a stock and the charts appears").
 *
 * A small store like the stock slide-out's (lib/ticker.ts), for the same reason: the
 * drawer is mounted once beside the page, in the Terminal, and the card that opens it
 * is deep in the Futures board. The two drawers take the same place on the right, so
 * one opening puts the other away: opening a bias closes the stock, and the bias
 * drawer closes itself when a stock opens (vol/BiasDrawer).
 */

let current: string | null = null;
const subs = new Set<() => void>();

function set(v: string | null): void {
  if (current === v) return;
  current = v;
  subs.forEach((f) => f());
}

export function openBias(book: string): void {
  closeTicker();
  set(book);
}

export function closeBias(): void {
  set(null);
}

/** The card's click: open this book's, or put it away when it is the one already out. */
export function toggleBias(book: string): void {
  if (current === book) closeBias();
  else openBias(book);
}

/** The book out now, read outside React (a view changing while the drawer is open). */
export function biasOut(): string | null {
  return current;
}

function subscribe(f: () => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

export function useBias(): string | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
