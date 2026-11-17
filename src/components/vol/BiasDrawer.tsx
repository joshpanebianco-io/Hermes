"use client";

import { useEffect } from "react";
import type { Drivers } from "@/types/terminal";
import { DriverBoard } from "@/components/vol/DriverBoard";
import { closeBias, useBias } from "@/lib/biasDrawer";
import { useTicker } from "@/lib/ticker";
import { segItem } from "@/lib/seg";

/**
 * A futures book's bias, slid out from the right (owner, 2026-11-16: "can we make it so
 * when you click on the bias the pop up card comes from the right similar to when you
 * click on a stock and the charts appears").
 *
 * THE STOCK SLIDE-OUT'S FRAME (ticker/TickerDrawer): the same place inside the page,
 * between the header and the status rail, the same `qt-drawer` card under Luminous and
 * the Sidebar interface, the same edge and shadow, and like it no backdrop: the chart
 * and the cards behind stay live and can be clicked. Esc closes it, as it closes the
 * stock's. 920px wide, the sheet's own width with its margins, where the stock's is a
 * share of the page, because a chart is better wide and a report is not.
 *
 * IT IS THE BOARD OF THE LAST REFRESH. The Terminal hands it `drivers` from the page's
 * own poll, so it moves while it is open, as the card does.
 *
 * ONE DRAWER AT A TIME. Opening a bias puts a stock away (lib/biasDrawer), and a stock
 * opened from the search puts this away. A change of page closes it (Terminal setTab);
 * a change of contract on the Futures tab moves it to that contract (FuturesBoard).
 */
export function BiasDrawer({ drivers }: { drivers: Drivers | undefined }) {
  const book = useBias();
  const sym = useTicker();

  useEffect(() => {
    if (sym) closeBias();
  }, [sym]);

  useEffect(() => {
    if (!book) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (e.key === "Escape") {
        e.preventDefault();
        closeBias();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [book]);

  if (!book) return null;
  const b = drivers?.books?.[book];
  return (
    <aside
      aria-label={`${book}, bias`}
      className="qt-drawer absolute inset-y-0 right-0 z-40 flex min-w-0 flex-col border-l border-ring-2 bg-bg shadow-[-18px_0_60px_rgba(0,0,0,.45)]"
      style={{ width: "min(100%, 920px)" }}
    >
      {b ? (
        <DriverBoard book={b} asOf={drivers?.built_utc} onClose={closeBias} />
      ) : (
        <div className="flex items-start justify-between gap-4 px-7 py-6">
          <p className="text-[12.5px] text-ink-3">
            {drivers?.error ? `The driver board is unavailable: ${drivers.error}` : `No bias for ${book} on the last refresh.`}
          </p>
          <button type="button" onClick={closeBias} title="Close (Esc)" {...segItem(false, { className: "border border-ring-2" })}>
            ✕
          </button>
        </div>
      )}
    </aside>
  );
}
