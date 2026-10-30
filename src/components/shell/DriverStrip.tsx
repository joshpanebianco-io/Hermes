"use client";

import type { Drivers } from "@/types/terminal";
import { DriverPopover, biasWord, gradeTone, voteTone } from "@/components/vol/DriverBoard";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { cn } from "@/lib/cn";

/**
 * The driver strip — the futures Terminal's top line: per book, which way the
 * engine's count leans, how many reads agree, and one line on how to treat it.
 *
 * THE STOCKS DESK'S STRIP, FOR NQ, ES AND GC (owner, 2026-10-22). The Market
 * tab opens on its tape conviction; the futures Terminal opened on the panels
 * and left the macro read to the Analysis brief. This is the same shape — a
 * figure, a count and a sentence — and each cell is the trigger for the full
 * board (DriverBoard), the way every VIX figure opens the bands.
 *
 * NOTHING HERE IS COMPUTED IN THE BROWSER. Every word is the collector's
 * (drivers.py), so the strip, the board and the brief agree.
 */
export function DriverStrip({ drivers }: { drivers: Drivers | undefined }) {
  const books = drivers?.books ?? {};
  const keys = (["NQ", "ES", "GC"] as const).filter((k) => books[k]);
  return (
    <section
      aria-label="Driver board"
      className={cn(
        "mx-2 mt-2 shrink-0 overflow-hidden rounded-lg border border-ring bg-surface",
        "qt:mx-0 qt:mt-0 qt:rounded-none qt:border-x-0 qt:border-t-0 qt:bg-transparent",
      )}
    >
      {keys.length === 0 ? (
        drivers?.error ? (
          <p className="px-4 py-2 text-[11px] text-err qt:px-6">
            <strong className="font-semibold">Driver board unavailable.</strong> {drivers.error}
          </p>
        ) : (
          <HelmLoader label="Counting the drivers" size={26} minHeight={64} className="py-2" />
        )
      ) : (
        <div className="grid grid-cols-1 divide-y divide-ring md:grid-cols-3 md:divide-x md:divide-y-0">
          {keys.map((k) => {
            const b = books[k]!;
            return (
              <DriverPopover
                key={k}
                book={b}
                // Half a page wide since Structure split in two (2026-10-30): tighter
                // padding, and the head wraps as a row rather than inside a figure.
                className="flex min-w-0 flex-col items-start rounded-none px-3 py-2 text-left qt:px-4 qt:py-2.5"
              >
                <span className="flex w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 whitespace-nowrap">
                  <span className="qt-cap text-[10px] text-ink-3">{k}</span>
                  <span className={cn("text-[14px] leading-none font-semibold", voteTone(b.bias))}>
                    {biasWord(b.bias)}
                  </span>
                  <span className="fig text-[11px] text-ink-2">
                    {b.agree} of {b.total}
                  </span>
                  <span className={cn("qt-cap text-[10px]", gradeTone(b))}>{b.grade}</span>
                  {b.conflict && <span className="qt-cap text-[10px] text-flip-fig">conflict</span>}
                  {b.regime && (
                    <span className={cn("qt-cap ml-auto text-[9.5px]", b.regime === "POS" ? "text-call-fig" : "text-put-fig")}>
                      {b.regime === "POS" ? "positive γ" : "negative γ"}
                    </span>
                  )}
                </span>
                <span className="mt-1 line-clamp-2 text-[11px] leading-[1.4] text-ink-3">{b.treatment}</span>
              </DriverPopover>
            );
          })}
        </div>
      )}
    </section>
  );
}
