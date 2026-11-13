"use client";

import { memo, useMemo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import { Wire } from "@/components/panels/Wire";
import { Board } from "@/components/panels/Board";
import { Rates } from "@/components/panels/Rates";
import { Calendar } from "@/components/panels/Calendar";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import { Fed } from "@/components/panels/Fed";
import type { MarketFeed } from "@/lib/useMarket";
import { useWatchlistEarnings } from "@/lib/useWatchlistEarnings";
import { boardReady } from "@/lib/ready";
import { PageLoader } from "@/components/ui/HelmLoader";
import { ageStep } from "@/lib/format";

/**
 * Macro — what is happening, and what is scheduled. One tab for both desks
 * (lib/tabs.ts, 2026-10-30).
 *
 * THREE COLUMNS, AND THE MIDDLE ONE IS THE WIRE: live state on the left, the news in
 * the middle where the eye rests, what is scheduled on the right, importance descending
 * down each column (owner's principle, 2026-09-16).
 *
 * LEFT: the index movers (which names carried the index), then Earnings (owner,
 * 2026-11-13: "move the earnings card to the left and under index movers"), with the
 * Scanner's names marked, then Rates & policy, the curve and the Fed path.
 *
 * RIGHT: the calendar, then the macro board under it, then the Fed & Treasury diary.
 *
 * THREE PANELS WENT, AND THE BOARD CAME UP (owner, 2026-11-14, after a review of the
 * page: "yes do that"). Each repeated another panel on the same page:
 *   - Prints & the Fed: the calendar already lists the session's releases with actual,
 *     consensus and previous; its next-FOMC line is Rates & policy's path; its speakers
 *     are the Fed diary's.
 *   - Cross-asset: the 2Y, the 10Y, 2s10s, the dollar, high yield, long bonds, crude,
 *     gold and bitcoin are every one on the board or in Rates.
 *   - Sector peers reporting: the same reports are in the Earnings card.
 * The macro board was last in the left column, under Earnings and Rates, a scroll down,
 * though since the header stopped carrying prices (2026-11-12) it is the only place in
 * the app for the VIX term structure, VVIX, MOVE, the dollar, crude, gold and bitcoin.
 * It took the right column's freed room, under the calendar. Hermes still reads the
 * prints, the cross-asset moves and the peers through its panels.
 *
 * NO SECTORS AND NO BREADTH HERE SINCE 2026-11-13 (owner: "streamline the app and make it
 * have the most useful informaiton visible without clutter and noise"): the sectors are
 * the Sectors tab and the Dashboard's rotation row, breadth the Dashboard's card.
 *
 * THE MACRO CONTEXT the removed panels read (prints, the Fed path, peers, cross-asset)
 * is still polled every twenty seconds by the Terminal: the page waits on it below.
 *
 * ONE LOADER, NOT ONE PER PANEL (owner, 2026-10-30: "instead of having
 * individual loading spinners for each module, lets just make it the whole
 * page have one loading spinner until everything loads"). While the
 * collector is still warming — a cold start, or the minute after a restart —
 * the board used to be a grid of nine helms, each panel waiting on its own
 * source. Now the board waits as one: the helm in the middle until every
 * source this page reads has reported once (lib/ready.ts), then the whole
 * page at once. A source that fails AFTER that still says so in its own
 * panel, which is the right place for it.
 */

const MWire = memo(Wire);
const MBoard = memo(Board);
const MRates = memo(Rates);
const MCalendar = memo(Calendar);
const MEarnings = memo(Earnings);
const MMovers = memo(Movers);
const MFed = memo(Fed);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
// Hoisted: an array literal in JSX is a new prop every render and would defeat the memo.
// The order drawn: VIX and its curve, then rates, then the rest as they were.
const MACRO_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["vol", "rates", "global", "fx", "energy", "metals", "crypto"];

/** The sources this page reads — the board waits for each to have reported once. */
const SOURCES = ["quotes", "wire", "calendar", "constituents", "rates", "fed", "auctions", "earnings"];

export function MacroBoard({ data, market: feed }: { data: TerminalData; market: MarketFeed }) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { watch, extra } = useWatchlistEarnings();

  // The index-minded block plus the watchlist's own reports, once each.
  const earnings = useMemo(() => {
    const base = data.earnings ?? NONE;
    if (extra.length === 0) return base;
    const have = new Set(base.map((r) => `${r.date}:${r.symbol}`));
    const add = extra.filter((r) => !have.has(`${r.date}:${r.symbol}`));
    return [...base, ...add].sort((a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0));
  }, [data.earnings, extra]);

  // Waiting is a card where the board will be (ui/HelmLoader PageLoader), inset as the
  // board's cards are under Luminous; Quiet gives the wait no paint or inset.
  if (!boardReady(data, SOURCES, feed)) {
    return (
      <main className="flex min-h-0 flex-1 flex-col lum:p-[var(--lum-gap)]">
        <PageLoader label="Loading the desk" size={64} />
      </main>
    );
  }

  // New York's box: the cash figures on this page are the last session's outside it.
  const cashOpen = data.clock?.boxes?.some((b) => b.key === "ny" && b.open) ?? true;

  return (
    <main className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
      {/* ---- left: what the market is doing ------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MMovers indices={data.constituents?.indices ?? EMPTY} cashOpen={cashOpen} ageMin={age("constituents")} error={st.constituents?.ok === false ? st.constituents.error : null} />
        <MEarnings rows={earnings} watch={watch} today={data.expiry?.today ?? ""} ageMin={age("earnings")} error={st.earnings?.ok === false ? st.earnings.error : null} />
        <MRates rates={data.rates} pm={data.policy_meetings} ageMin={age("rates")} error={st.rates?.ok === false ? st.rates.error : null} />
      </div>

      {/* ---- middle: the wire -------------------------------------------- */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
        <MWire items={data.wire ?? NONE} ageMin={age("wire")} error={st.wire?.ok === false ? st.wire.error : null} />
      </div>

      {/* ---- right: what is scheduled ------------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MCalendar rows={data.calendar ?? NONE} holidays={data.holidays ?? NONE} ageMin={age("calendar")} error={st.calendar?.ok === false ? st.calendar.error : null} />
        <MBoard title="Macro board" quotes={data.quotes ?? NONE} groups={MACRO_GROUPS} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
        <MFed
          rows={data.fed ?? NONE}
          auctions={data.auctions ?? NONE}
          today={data.expiry?.today ?? ""}
          ageMin={raw.fed == null ? age("auctions") : raw.auctions == null ? age("fed") : (ageStep(Math.max(raw.fed, raw.auctions)) ?? undefined)}
          error={st.fed?.ok === false ? st.fed.error : st.auctions?.ok === false ? st.auctions.error : null}
        />
      </div>
    </main>
  );
}
