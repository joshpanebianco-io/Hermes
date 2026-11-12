"use client";

import { ScanSectors } from "@/components/panels/ScanSectors";
import { Glyph } from "@/components/panels/ScanWide";
import { useSide } from "@/components/state/UiMode";
import { openSearch } from "@/lib/ticker";

/**
 * Sectors — where the money is, and the stocks in it, on a tab of its own.
 *
 * A SCANNER VIEW UNTIL 2026-11-10 (owner: "do you think sector and themes should be
 * moved out of scanner and into it's own tab in the top nav?" — yes). It answers a
 * market question, which group is working today, before the Scanner's, which stock
 * and which level, so it sits on the bar beside Macro and Futures,
 * and can stay open on a side screen all session while the main screen holds Setups.
 *
 * The page is the Scanner's Sectors view unchanged (ScanSectors: the heat map, the
 * themes, the industries, a group's stocks with Track), under a band like the
 * Scanner's own: the index prices and the search. Macro's rotation panel keeps the
 * eleven sectors and no longer toggles to the themes, which are these cards.
 */
export function SectorsBoard({ prices }: { prices?: React.ReactNode }) {
  // The Sidebar interface names the page and carries the prices and the search in its
  // header: there the band has nothing left to say.
  const side = useSide();
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {!side && (
      <div className="qt-mast flex min-h-[44px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 qt:px-4">
        <p className="flex items-baseline gap-2 whitespace-nowrap">
          <span className="qt-cap text-ink-2">Sectors</span>
          <span className="text-[11.5px] text-ink-3">where the money is, and the stocks in it</span>
        </p>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          {prices && <div className="mr-2 flex min-w-0 items-center">{prices}</div>}
          <span className="contents">
            <button
              type="button"
              onClick={openSearch}
              title="Find any ticker or company (Ctrl+K)"
              className="hit flex h-[30px] w-[clamp(170px,17vw,320px)] items-center gap-2 rounded-[4px] border border-ring-2 px-2.5 text-[12px] whitespace-nowrap text-ink-3"
            >
              <Glyph name="search" size={13} />
              <span className="min-w-0 flex-1 truncate text-left">Search ticker or company…</span>
              <span className="fig shrink-0 rounded-[3px] border border-ring-2 px-1.5 text-[10px]">Ctrl K</span>
            </button>
          </span>
        </div>
      </div>
      )}
      {/* The page sits in one framed card under the band, as the Scanner's views do. */}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
        <ScanSectors />
      </div>
    </main>
  );
}
