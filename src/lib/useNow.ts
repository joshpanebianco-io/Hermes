"use client";

import { useSyncExternalStore } from "react";

/**
 * The wall clock, for the few components that print it.
 *
 * IT USED TO TICK AT THE ROOT, and the whole terminal paid for it: Terminal
 * held `now` in state and set it every second, so every panel on the board —
 * the wire's 150 rows, the calendar's 200, the movers map — re-rendered once a
 * second to move four clocks (measured 2026-10-13: 18 long tasks per 20s on
 * the Terminal tab, median 84ms, against ~17 DOM changes a second that actually
 * needed making). Now the tick lives here and only its readers re-render: the
 * header clock and the session countdowns each second, the "14m" ages every
 * thirty, because an age that moves in whole minutes has nothing to say in
 * between.
 *
 * ONE TIMER PER STEP, SHARED. Every reader of the one-second clock is woken by
 * the same interval, so the header and the countdowns can never disagree by a
 * tick, and ten readers cost one timer.
 *
 * NULL ON THE SERVER AND THROUGH HYDRATION, for the reason Terminal.tsx gives:
 * the server has no business guessing the reader's clock, and a time string
 * rendered on both sides is a hydration mismatch on every load. React hydrates
 * with `getServerSnapshot` (null) and then renders the live value.
 *
 * BOTH FUNCTIONS HANDED TO REACT ARE STABLE PER STEP, and the first cut proved
 * why that matters: a fresh `subscribe` each render makes React unsubscribe and
 * resubscribe every render, a resubscribe restarts the timer and re-pins the
 * time, the new time re-renders — "Maximum update depth exceeded".
 */

interface Ticker {
  now: number | null;
  listeners: Set<() => void>;
  timer: ReturnType<typeof setInterval> | null;
  subscribe: (cb: () => void) => () => void;
  /*
   * THE SNAPSHOT IS CACHED. React calls it repeatedly within one render and
   * treats a different answer as "the store changed under me", so it returns
   * the pinned time and only the interval moves it.
   */
  snapshot: () => number;
}

const TICKERS = new Map<number, Ticker>();

const serverSnapshot = () => null;

function ticker(step: number): Ticker {
  const existing = TICKERS.get(step);
  if (existing) return existing;
  const t: Ticker = {
    now: null,
    listeners: new Set(),
    timer: null,
    subscribe: (cb) => {
      t.listeners.add(cb);
      if (t.timer === null) {
        // Restarting after every reader left: the pinned time may be stale.
        // React re-reads the snapshot after subscribing, so this lands at once.
        t.now = Date.now();
        t.timer = setInterval(() => {
          t.now = Date.now();
          for (const l of t.listeners) l();
        }, step);
      }
      return () => {
        t.listeners.delete(cb);
        if (t.listeners.size === 0 && t.timer !== null) {
          clearInterval(t.timer);
          t.timer = null;
        }
      };
    },
    snapshot: () => {
      if (t.now === null) t.now = Date.now();
      return t.now;
    },
  };
  TICKERS.set(step, t);
  return t;
}

/** Epoch ms, refreshed every `step` ms; null until mounted. */
export function useNow(step = 1000): number | null {
  const t = ticker(step);
  return useSyncExternalStore(t.subscribe, t.snapshot, serverSnapshot);
}
