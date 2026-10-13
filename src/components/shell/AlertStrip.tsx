"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { WireItem } from "@/types/terminal";
import { Ago } from "@/components/ui/Ago";

/**
 * The alert line — high-impact headlines, crawling, on every tab.
 *
 * A CRAWL, MATCHING GEXYGEN (owner instruction, 2026-08-31). The first cut was
 * a fixed row that scrolled by hand, on the argument that a moving target
 * cannot be scanned. That argument is right about the WIRE COLUMN and wrong
 * here: this strip is one line tall, it holds sixteen items on a day like
 * today, and a fixed row shows three of them and hides the rest behind a
 * scrollbar nobody drags. A crawl shows all sixteen without being asked, which
 * is the entire job of an alert line.
 *
 * IT PAUSES UNDER THE POINTER, so a line can be read or clicked, and under
 * reduced motion it does not move at all and becomes the hand-scrolled row
 * instead.
 *
 * THE MECHANISM IS GEXYGEN'S. Two copies of the run back to back, translated by
 * exactly half the width so the seam is invisible, with the duration computed
 * from the measured width rather than fixed — that is what keeps a long tape
 * and a short one crawling at the same READING PACE instead of the same
 * duration.
 *
 * IT DISAPPEARS WHEN THERE IS NOTHING. An always-present bar reading "no
 * alerts" trains you to ignore exactly the space that has to catch your eye
 * when something does land.
 */

/** Pixels per second. Reading pace for a one-line headline at this size. */
const SPEED_PX_S = 52;

export function AlertStrip({
  items,
}: {
  items: WireItem[];
}) {
  const runRef = useRef<HTMLDivElement | null>(null);
  const [duration, setDuration] = useState(60);

  const alerts = useMemo(() => items.filter((i) => i.impact === "high").slice(0, 20), [items]);

  /*
   * Measure one copy of the run and set the loop's duration from it. Re-measured
   * on resize because the strip is the full width of the chassis and the
   * chassis is the full width of the window.
   */
  useEffect(() => {
    const el = runRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.scrollWidth / 2;
      if (w > 0) setDuration(Math.max(20, w / SPEED_PX_S));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [alerts]);

  if (alerts.length === 0) return null;

  const line = (h: WireItem, i: number, copy: number) => (
    <a
      key={`${copy}-${h.url}-${i}`}
      href={h.url}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-2 pr-7 pl-1 whitespace-nowrap hover:[&>span:nth-child(2)]:underline hover:[&>span:nth-child(2)]:underline-offset-4"
      title={`${h.publisher} · ${h.category}`}
      // OUT OF THE TAB ORDER, BOTH COPIES (review, 2026-10-13: a keyboard had
      // to walk twenty crawl links before reaching the page). The crawl is a
      // moving target and a poor keyboard surface, and every one of these
      // headlines is also a link on the wire, where the tab key can reach it.
      // The first copy stays readable to a screen reader; the second exists
      // only for the loop.
      tabIndex={-1}
      aria-hidden={copy === 1}
    >
      <span aria-hidden className="h-[7px] w-[7px] shrink-0 rounded-full bg-err qt:h-[6px] qt:w-[6px] qt:rounded-[1px]" />
      <span className="text-[12.5px] leading-none text-ink qt:text-[13px]">{h.title}</span>
      <span className="fig text-[9.5px] leading-none text-ink-3 qt:text-[10.5px] qt:font-semibold qt:tracking-[0.06em] qt:uppercase qt:[font-family:var(--font-cond)]">{h.publisher}</span>
      <Ago utc={h.utc} className="fig text-[9.5px] leading-none text-ink-3 qt:text-[11px]" />
    </a>
  );

  return (
    <div
      className="flex items-stretch border-b border-ring bg-err/[0.07] qt:bg-transparent"
      role="region"
      aria-label="High-impact headlines"
    >
      <div className="flex shrink-0 items-center gap-1.5 border-r border-ring/60 px-3 qt:border-ring qt:px-6">
        <span className="h-[6px] w-[6px] rounded-full bg-err live-dot qt:rounded-[1px]" aria-hidden />
        <span className="fig text-[9px] tracking-[0.14em] text-err uppercase qt:text-[11px]">High</span>
        <span className="fig text-[9px] text-ink-3 qt:text-[11px]">{alerts.length}</span>
      </div>
      <div className="wire-track relative min-w-0 flex-1 overflow-hidden py-2.5">
        <div
          ref={runRef}
          className="wire-run flex w-max items-center"
          style={{ animationDuration: `${duration}s` }}
        >
          {alerts.map((h, i) => line(h, i, 0))}
          {alerts.map((h, i) => line(h, i, 1))}
        </div>
      </div>
    </div>
  );
}
