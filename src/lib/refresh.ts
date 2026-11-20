"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * THE REFRESH BUTTON, FELT (owner, 2026-11-20: "can we make the refresh button at the top
 * right corner a bit more responsive or feedback so that we know its been clicked ... so you
 * can feel it more").
 *
 * It read the shell's payload again and said nothing: no press, no sign of the read, and
 * on the Dashboard, Stocks or Sectors nothing on screen moved, because those pages read
 * their own feeds. Now a click also asks the open page to read again (`REFRESH_EVENT`,
 * `useRefresh`), and the button presses in, spins while the read is in flight (for long
 * enough to be seen), and shows a tick for a moment when it has landed.
 */
export const REFRESH_EVENT = "hermes:refresh";

/** Ask whatever page is open to read its own feed again. */
export function refreshPages(): void {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

/** Read again when the refresh button is pressed. */
export function useRefresh(load: () => void): void {
  useEffect(() => {
    window.addEventListener(REFRESH_EVENT, load);
    return () => window.removeEventListener(REFRESH_EVENT, load);
  }, [load]);
}

/** The spin is held at least this long, or a fast read is a flicker nobody sees. */
const MIN_SPIN_MS = 650;
/** The tick after it. */
const DONE_MS = 1100;

export type RefreshPhase = "idle" | "busy" | "done";

/** The button's state through a press: busy while `run` is in flight, then done briefly. */
export function useRefreshPress(run: () => void | Promise<void>): { phase: RefreshPhase; press: () => void } {
  const [phase, setPhase] = useState<RefreshPhase>("idle");
  const busy = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const press = useCallback(() => {
    if (busy.current) return;
    busy.current = true;
    window.clearTimeout(timer.current);
    setPhase("busy");
    const t0 = Date.now();
    void Promise.resolve()
      .then(run)
      .catch(() => undefined)
      .then(() => {
        timer.current = window.setTimeout(() => {
          busy.current = false;
          setPhase("done");
          timer.current = window.setTimeout(() => setPhase("idle"), DONE_MS);
        }, Math.max(0, MIN_SPIN_MS - (Date.now() - t0)));
      });
  }, [run]);
  return { phase, press };
}
