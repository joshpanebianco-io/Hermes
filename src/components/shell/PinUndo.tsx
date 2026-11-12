"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { UNPINNED_EVENT, restorePin, type Unpinned } from "@/lib/pins";
import { segItem } from "@/lib/seg";

/**
 * The notice an unpin raises, with its Undo (lib/pins.ts has the why: a name left the
 * owner's list on one click of a star, and nothing on screen said so).
 *
 * AT THE FOOT OF THE PAGE, IN THE MIDDLE, where it cannot be under the pointer that
 * made it and is not where the scanner's alerts stack (the right). It stays twenty
 * seconds, long enough to be seen by someone who was reading a row, and it is the
 * latest unpin only: a reader pruning the list on purpose gets one line that keeps
 * up, not a pile. Whatever it no longer shows is still in the Watchlist editor's
 * "unpinned recently" for a week.
 */

const STAY_MS = 20_000;
const DONE_MS = 2_600;

type Shown = { u: Unpinned; state: "ask" | "busy" | "back" | "failed"; why?: string };

export function PinUndo() {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef(0);

  const leaveIn = useCallback((ms: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(null), ms);
  }, []);

  useEffect(() => {
    const onUnpin = (e: Event) => {
      const u = (e as CustomEvent<Unpinned>).detail;
      if (!u?.sym) return;
      setShown({ u, state: "ask" });
      leaveIn(STAY_MS);
    };
    window.addEventListener(UNPINNED_EVENT, onUnpin);
    return () => {
      window.removeEventListener(UNPINNED_EVENT, onUnpin);
      window.clearTimeout(timer.current);
    };
  }, [leaveIn]);

  if (!shown) return null;
  const { u, state, why } = shown;

  const undo = () => {
    window.clearTimeout(timer.current);
    setShown({ u, state: "busy" });
    void restorePin(u).then((err) => {
      // A refusal stays up with its reason; the name is still in the editor's list.
      setShown(err ? { u, state: "failed", why: err } : { u, state: "back" });
      leaveIn(err ? STAY_MS : DONE_MS);
    });
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-12 z-[900] flex justify-center px-4" aria-live="polite" role="status">
      <div className="qt-undo pointer-events-auto flex max-w-full items-center gap-3 rounded-[4px] border border-ring-2 bg-surface-2 py-2 pr-2 pl-3.5 shadow-[0_12px_36px_-12px_rgb(0_0_0/0.9)] lum:rounded-[14px]">
        <p className="min-w-0 text-[12.5px] text-ink-2">
          {state === "back" ? (
            <>
              <span className="font-semibold text-ink">{u.sym}</span> is pinned again, where it was.
            </>
          ) : state === "failed" ? (
            <>
              <span className="font-semibold text-ink">{u.sym}</span> could not be put back: <span className="text-err">{why}</span>
            </>
          ) : (
            <>
              <span className="font-semibold text-ink">{u.sym}</span> unpinned: it is off your list.
            </>
          )}
        </p>
        {(state === "ask" || state === "busy" || state === "failed") && (
          <button type="button" onClick={undo} disabled={state === "busy"} {...segItem(true, { className: "shrink-0 border border-ring-2 disabled:opacity-50" })}>
            {state === "busy" ? "Putting it back…" : state === "failed" ? "Try again" : "Undo"}
          </button>
        )}
        <button type="button" aria-label="Dismiss" onClick={() => setShown(null)} className="hit shrink-0 px-1.5 text-[14px] leading-none text-ink-3 hover:text-ink">
          ×
        </button>
      </div>
    </div>
  );
}
