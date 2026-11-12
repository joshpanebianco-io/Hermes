"use client";

import { useEffect } from "react";
import { PINS_EVENT } from "@/lib/pins";

/**
 * Read a page's data again when the pinned list changes by any hand: a star on
 * another table, the slide-out's, or the Undo on the unpin notice (shell/PinUndo),
 * which is not any page's own and so cannot call a page's refresh itself. Without
 * it a name put back by Undo reappeared only on the page's next poll.
 */
export function usePinsChanged(refresh: () => void): void {
  useEffect(() => {
    window.addEventListener(PINS_EVENT, refresh);
    return () => window.removeEventListener(PINS_EVENT, refresh);
  }, [refresh]);
}
