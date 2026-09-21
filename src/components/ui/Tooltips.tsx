"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Every hover explanation in the app, drawn by the app.
 *
 * WHY THIS EXISTS. The terminal explains itself through `title` attributes —
 * ninety-odd of them, on column heads, chips, bars and rows — and the browser
 * draws those as its own pale system box in its own font, which on a
 * near-black instrument reads as a different program interrupting (owner,
 * 2026-09-22). The content was right; the box was not ours.
 *
 * ONE LAYER, NOT NINETY CALL SITES. Mounted once in the root layout, it
 * listens at the document, finds the nearest element carrying a `title`, and
 * TAKES the attribute for as long as the pointer is there — moved to
 * `data-tip`, because a `title` still on the element is a native tooltip
 * still coming. It is given back on the way out. So `title="…"` stays the way
 * to explain something, every existing one is restyled without being touched,
 * and the next one written is restyled without anyone remembering to.
 *
 * REACT KEEPS WRITING `title` WHILE WE HOLD IT. A figure that refreshes under
 * the cursor has its attribute set again by React, which would bring the
 * native box back alongside ours. A MutationObserver on the held element takes
 * it again and updates the text in place — so a tooltip over a live number
 * ticks with the number, which the native one never did.
 *
 * IT APPEARS WHERE THE CURSOR IS WHEN THE DELAY ENDS and then stays put, the
 * way the native one does; a box that chases the pointer is a box you cannot
 * read. Moving straight from one explained thing to the next skips the delay,
 * because by then you are clearly reading them.
 *
 * NEWLINES IN A TITLE ARE KEPT (`pre-line`) — several rows use them to put the
 * range, the window and the read on separate lines.
 */

const DELAY_MS = 350;
const WARM_MS = 600;

type Tip = { text: string; x: number; y: number };

export function Tooltips() {
  const [tip, setTip] = useState<Tip | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let target: Element | null = null;
    let timer: number | undefined;
    let watch: number | undefined;
    let shown = false;
    let warmUntil = 0;
    let mx = 0;
    let my = 0;

    const take = (el: Element): string => {
      const t = el.getAttribute("title");
      if (t !== null) {
        el.removeAttribute("title");
        el.setAttribute("data-tip", t);
        return t;
      }
      return el.getAttribute("data-tip") ?? "";
    };

    const giveBack = (el: Element) => {
      const t = el.getAttribute("data-tip");
      if (t === null) return;
      el.removeAttribute("data-tip");
      if (!el.hasAttribute("title")) el.setAttribute("title", t);
    };

    const observer = new MutationObserver(() => {
      // Our own removal lands here too; only a `title` that is BACK is news.
      if (!target?.hasAttribute("title")) return;
      const text = take(target);
      if (shown) setTip((p) => (p ? { ...p, text } : p));
    });

    /** Stop showing, but keep hold of the element so it does not re-open. */
    const hide = () => {
      window.clearTimeout(timer);
      window.clearInterval(watch);
      if (shown) warmUntil = performance.now() + WARM_MS;
      shown = false;
      setTip(null);
    };

    const leave = () => {
      hide();
      observer.disconnect();
      if (target) giveBack(target);
      target = null;
    };

    const enter = (el: Element | null) => {
      if (el === target) return;
      leave();
      if (!el) return;
      target = el;
      if (!take(el)) return; // an empty title explains nothing, and blocks its parents
      observer.observe(el, { attributes: true, attributeFilter: ["title"] });
      const show = () => {
        const text = target?.getAttribute("data-tip");
        if (!target?.isConnected || !text) return;
        shown = true;
        setTip({ text, x: mx, y: my });
        // A row that re-renders away under a still cursor fires no event.
        watch = window.setInterval(() => {
          if (!target?.isConnected) leave();
        }, 500);
      };
      if (performance.now() < warmUntil) show();
      else timer = window.setTimeout(show, DELAY_MS);
    };

    const tipOf = (t: EventTarget | null) =>
      t instanceof Element ? t.closest("[title], [data-tip]") : null;

    const over = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      mx = e.clientX;
      my = e.clientY;
      enter(tipOf(e.target));
    };
    const move = (e: PointerEvent) => {
      mx = e.clientX;
      my = e.clientY;
    };
    // Keyboard users get the same explanation, anchored under the control.
    const focus = (e: FocusEvent) => {
      const el = tipOf(e.target);
      if (!el || !(e.target instanceof Element) || !e.target.matches(":focus-visible")) return;
      const r = el.getBoundingClientRect();
      mx = r.left + Math.min(r.width / 2, 24) - 12;
      my = r.bottom - 12;
      enter(el);
    };

    const opts = { capture: true, passive: true } as const;
    document.addEventListener("pointerover", over, opts);
    document.addEventListener("pointermove", move, opts);
    document.addEventListener("pointerdown", hide, opts);
    document.addEventListener("keydown", hide, opts);
    document.addEventListener("scroll", hide, opts);
    document.addEventListener("focusin", focus, opts);
    document.addEventListener("focusout", leave, opts);
    document.documentElement.addEventListener("pointerleave", leave);
    window.addEventListener("blur", leave);
    return () => {
      leave();
      document.removeEventListener("pointerover", over, opts);
      document.removeEventListener("pointermove", move, opts);
      document.removeEventListener("pointerdown", hide, opts);
      document.removeEventListener("keydown", hide, opts);
      document.removeEventListener("scroll", hide, opts);
      document.removeEventListener("focusin", focus, opts);
      document.removeEventListener("focusout", leave, opts);
      document.documentElement.removeEventListener("pointerleave", leave);
      window.removeEventListener("blur", leave);
    };
  }, []);

  // Placed after it has a size: below-right of the cursor, pulled back inside
  // the window, and flipped above when there is no room underneath.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el || !tip) return;
    const { width, height } = el.getBoundingClientRect();
    const left = Math.max(8, Math.min(tip.x + 12, window.innerWidth - width - 8));
    const below = tip.y + 20;
    const top =
      below + height > window.innerHeight - 8 ? Math.max(8, tip.y - height - 12) : below;
    el.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
    el.style.visibility = "visible";
  }, [tip]);

  if (!tip) return null;
  return (
    <div ref={box} role="tooltip" className="tip" style={{ visibility: "hidden" }}>
      {tip.text}
    </div>
  );
}
