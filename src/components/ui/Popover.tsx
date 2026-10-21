"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

/**
 * A figure you can click for its long form.
 *
 * THE TRIGGER IS THE FIGURE ITSELF, not an "i" beside it (owner, 2026-10-21:
 * "if we click on the vix card it shows the ranges"). GEXYGEN's Explain does
 * the same with Radix under it; this terminal carries no Radix and one popover
 * does not earn the dependency, so the mechanism is written here: a real
 * <button> around the figure, and a panel appended to <body>.
 *
 * APPENDED TO BODY, POSITIONED FIXED, for the same reason the tooltip layer
 * is: the header strip clips its overflow (that is how it drops figures from
 * the right instead of wrapping), and a panel drawn inside it would be cut at
 * 36px. The panel is placed under the trigger's left edge, pulled inside the
 * window, and flipped above when there is no room underneath — the tooltip's
 * own rule. It follows the trigger through scroll and resize.
 *
 * It closes on Escape, on a press anywhere outside it, or on the trigger
 * again. Focus moves into the panel on open so Escape and Tab work from
 * there, and comes back to the trigger when Escape closes it.
 *
 * `title` on the trigger still gives the one-line hover (the tooltip layer
 * takes it); the click is the long form. The panel carries no titles of its
 * own, so nothing hovers over the thing being read.
 */
export function Popover({
  label,
  panel,
  title,
  className,
  panelClassName,
  children,
}: {
  /** The dialog's accessible name — what is being explained. */
  label: string;
  /** What opens. */
  panel: React.ReactNode;
  /** The trigger's hover line. */
  title?: string;
  /** Layout for the trigger — it is the figure, so the caller owns its shape. */
  className?: string;
  panelClassName?: string;
  /** The figure. Phrasing content only: this sits inside a <button>. */
  children: React.ReactNode;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  // Bumped on scroll and resize so the placement effect runs again.
  const [moved, setMoved] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);

  const close = useCallback((refocus: boolean) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      close(true);
    };
    const down = (e: PointerEvent) => {
      const t = e.target;
      if (!(t instanceof Node)) return;
      if (box.current?.contains(t) || trigger.current?.contains(t)) return;
      close(false);
    };
    const follow = () => setMoved((n) => n + 1);
    const opts = { capture: true, passive: true } as const;
    document.addEventListener("keydown", key, true);
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("scroll", follow, opts);
    window.addEventListener("resize", follow);
    box.current?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("keydown", key, true);
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("scroll", follow, opts);
      window.removeEventListener("resize", follow);
    };
  }, [open, close]);

  // Placed once it has a size: under the trigger, pulled inside the window,
  // flipped above when there is no room underneath. Hidden until then, so the
  // first frame never shows it at the origin.
  useLayoutEffect(() => {
    const el = box.current;
    const at = trigger.current;
    if (!open || !el || !at) return;
    const r = at.getBoundingClientRect();
    const { width, height } = el.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    const below = r.bottom + 6;
    const top = below + height > window.innerHeight - 8 ? Math.max(8, r.top - height - 6) : below;
    el.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
    el.style.visibility = "visible";
  }, [open, moved]);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        title={title}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "hit cursor-pointer rounded-[4px] text-left hover:bg-surface-2/70 aria-expanded:bg-surface-2",
          className,
        )}
      >
        {children}
      </button>
      {open &&
        createPortal(
          <div
            ref={box}
            id={id}
            role="dialog"
            aria-label={label}
            tabIndex={-1}
            style={{ visibility: "hidden" }}
            className={cn(
              "fixed top-0 left-0 z-50 outline-none",
              "rounded-[8px] border border-ring-2 bg-surface shadow-[0_18px_60px_rgba(0,0,0,.6)] qt:rounded-[4px]",
              panelClassName,
            )}
          >
            {panel}
          </div>,
          document.body,
        )}
    </>
  );
}
