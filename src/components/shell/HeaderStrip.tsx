"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { Quote } from "@/types/terminal";
import { dir, feedNote, num, quoteChg } from "@/lib/format";
import { cn } from "@/lib/cn";
import { fitCount, lagText, stripTiles, type StripTile } from "@/lib/headerStrip";
import { Popover } from "@/components/ui/Popover";
import { Tick } from "@/components/ui/Tick";
import { VixPopover, type VixFacts } from "@/components/vol/VixBands";

/**
 * The instruments in the header band, in two forms.
 *
 * FULL SCREEN KEEPS ITS AIR (owner, 2026-11-06: "it should be dynamic so in our
 * full screen on our pc, the header should be the way it was before"). On the
 * owner's 2560 monitor everything fits with a label over a price and the move
 * beside it, so that form stays. The `roomy:` variant in globals.css is the width
 * at which it stops fitting. Below that a tile stacks, a name and its move over
 * its price, about a third narrower.
 *
 * NOTHING SILENTLY GONE (owner, 2026-11-06: "without removing important info").
 * What did not fit used to fall away unmarked: at 1920 that was six of the eleven,
 * VIX among them, and only while the Overlap label took up room, so the row changed
 * through the day. Whatever does not fit now sits behind a count that opens it.
 *
 * IT FITS ITSELF, with no table of breakpoints to fall out of date: every tile is
 * measured and a tile is shown whole or not at all (lib/headerStrip.fitCount). One
 * that does not fit leaves the row but stays measurable, out of the flow and
 * `invisible`, so Tab cannot land on VIX's button out of sight. The box still wraps
 * and clips: before hydration, and for the full-screen form's New York countdown,
 * which goes first when it does not fit.
 *
 * The compact form's group divider belongs to the tile, not the row, so it cannot
 * be left hanging at the end of the row when the tile after it does not fit.
 */

/** The count's own width, fixed so "+2" and "+11" reserve the same room. */
const COUNT_W = 40;

export function HeaderStrip({
  quotes,
  ny,
  vixFacts,
  vixTitle,
}: {
  quotes: readonly Quote[];
  /** The New York countdown. The full-screen form draws it here; the compact one beside the clock. */
  ny: { label: string; value: string; title: string } | null;
  vixFacts: (q: Quote) => VixFacts;
  vixTitle: (note: string | null) => string;
}) {
  const tiles = stripTiles(quotes);
  const room = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState<number | null>(null);
  const roster = tiles.map((t) => t.quote.key).join();

  useLayoutEffect(() => {
    const whole = room.current;
    const el = box.current;
    if (!whole || !el) return;
    const kids = () => [...el.querySelectorAll<HTMLElement>(":scope > [data-tile]")];
    const read = () => {
      const widths = kids().map((k) => k.getBoundingClientRect().width);
      // Read off the box: the two forms set different gaps.
      const gap = parseFloat(getComputedStyle(el).columnGap) || 0;
      setFit(fitCount(widths, gap, whole.getBoundingClientRect().width, COUNT_W));
    };
    // On the next frame, not inside the observer: the count changes the box's width,
    // and resizing what is being observed from its own callback is a browser error.
    let frame = 0;
    const later = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    const watch = new ResizeObserver(later);
    watch.observe(whole);
    // A tile widens when a figure gains a digit, which can push the last one off.
    for (const kid of kids()) watch.observe(kid);
    read();
    return () => {
      cancelAnimationFrame(frame);
      watch.disconnect();
    };
  }, [roster]);

  const shown = fit ?? tiles.length;
  const rest = tiles.slice(shown);
  const tile = (q: Quote) => {
    const note = feedNote(q);
    return q.key === "VIX" ? (
      <VixPopover facts={vixFacts(q)} title={vixTitle(note)} className="-mx-1.5 flex px-1.5">
        <Figure q={q} />
      </VixPopover>
    ) : (
      <div className="flex" title={note ?? undefined}>
        <Figure q={q} />
      </div>
    );
  };

  return (
    <div ref={room} className="hidden min-w-0 flex-1 items-center gap-2.5 qt:flex">
      <div
        ref={box}
        className="relative flex h-[36px] min-w-0 flex-1 flex-wrap content-start justify-end gap-x-[9px] gap-y-4 overflow-hidden roomy:gap-x-4"
      >
        {tiles.map((t: StripTile, i) => (
          <div
            key={t.quote.key}
            data-tile
            className={cn(
              "relative flex h-[36px] shrink-0",
              t.startsGroup &&
                "pl-[9px] before:absolute before:top-[5px] before:bottom-[5px] before:left-0 before:w-px before:bg-ring-2 roomy:pl-0 roomy:before:hidden",
              i >= shown && "invisible absolute top-0 left-0",
            )}
          >
            {tile(t.quote)}
          </div>
        ))}
        {ny && (
          <div
            className="hidden h-[36px] shrink-0 flex-col justify-center gap-1 border-l border-ring pl-4 roomy:flex"
            title={ny.title}
          >
            <span className="qt-cap text-[10.5px] text-ink-3">{ny.label}</span>
            <span className="fig text-[14.5px] leading-none text-ink">{ny.value}</span>
          </div>
        )}
      </div>
      {rest.length > 0 && (
        <Popover
          label="The rest of the strip"
          title={rest.map((t) => t.quote.key).join(" · ")}
          className="fig flex h-[26px] w-[40px] shrink-0 items-center justify-center border border-ring-2 text-[11.5px] leading-none text-ink-2"
          panelClassName="w-[min(372px,calc(100vw-24px))]"
          panel={
            <div className="flex flex-wrap gap-x-5 gap-y-3 px-3.5 py-3">
              {rest.map((t) => (
                <div key={t.quote.key}>{tile(t.quote)}</div>
              ))}
            </div>
          }
        >
          +{rest.length}
        </Popover>
      )}
    </div>
  );
}

/** One instrument, in both forms. Phrasing content only: on VIX this sits inside a <button>. */
function Figure({ q }: { q: Quote }) {
  const chg = quoteChg(q);
  const lag = lagText(q);
  // A print two or three minutes behind is not late enough to spend width on in
  // the compact form, where its hover still says so. A real delay stays on the tile.
  const realLag = lagText(q, 5);
  return (
    <>
      <span className="flex flex-col justify-center gap-1 roomy:hidden">
        {/* The move beside its own name, left-aligned: pushed to the tile's right
            edge it read as the next instrument's. */}
        <span className="flex items-baseline gap-[5px]">
          <span className="qt-cap text-[10.5px] text-ink-3">{q.key}</span>
          <Tick value={chg.text} className={cn("fig text-[10.5px] leading-none", dir(chg.v))} />
        </span>
        {/* Lower case on purpose: under the caps label "NQ · 10m" read as "NQ · 10M",
            which looks like ten million or a ten-minute chart. */}
        <span className="flex items-baseline gap-[3px]">
          <Tick value={num(q.last)} className={cn("fig text-[14px] leading-none", stripInk(q))} />
          {realLag && <span className="fig text-[9px] leading-none text-ink-3">{realLag}</span>}
        </span>
      </span>
      <span className="hidden flex-col justify-center gap-1 roomy:flex">
        {/* How late a delayed print is rides under its own label — ES and NQ trail
            CME by ten minutes on this feed; a closed market's figure dims. */}
        <span className="qt-cap text-[10.5px] text-ink-3">
          {q.key}
          {lag && <span className="text-ink-4"> · {lag}</span>}
        </span>
        <span className="flex items-baseline gap-1.5">
          <Tick value={num(q.last)} className={cn("fig text-[14.5px] leading-none", stripInk(q))} />
          <Tick value={chg.text} className={cn("fig text-[11px] leading-none", dir(chg.v))} />
        </span>
      </span>
    </>
  );
}

/** A strip figure's ink: dimmed when its market is shut or has not printed in half an hour. */
export function stripInk(q: Quote): string {
  return q.feed === "closed" || q.feed === "stale" ? "text-ink-3" : "text-ink";
}
