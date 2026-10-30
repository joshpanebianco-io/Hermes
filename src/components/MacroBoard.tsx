"use client";

import { memo, useMemo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import { Wire } from "@/components/panels/Wire";
import { Board } from "@/components/panels/Board";
import { Rates } from "@/components/panels/Rates";
import { Rotation } from "@/components/panels/Rotation";
import { Calendar } from "@/components/panels/Calendar";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import { Fed } from "@/components/panels/Fed";
import { CrossAsset, PrintsFed, SectorPeers } from "@/components/market/SchedulePanels";
import type { MarketFeed } from "@/lib/useMarket";
import { useWatchlistEarnings } from "@/lib/useWatchlistEarnings";
import { boardReady } from "@/lib/ready";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { ageStep } from "@/lib/format";

/**
 * Macro — what is happening, and what is scheduled. One tab for both desks
 * (lib/tabs.ts, 2026-10-30).
 *
 * THREE COLUMNS, AND THE MIDDLE ONE IS THE WIRE. The layout encodes what this
 * page is for: live state on the left, news in the middle where the eye
 * rests, what is scheduled on the right. The futures Macro tab and the stocks
 * Market tab used to show these same panels in two different orders; this is
 * the one order, cut by the owner's principle that importance descends down a
 * column (2026-09-16), with what is live above what is scheduled.
 *
 * LEFT — what the market is doing. The CONSEQUENCES of the macro lead, because
 * they are short and they are the read: which sectors are being bought, and
 * which names carried the index. Rates next, the one panel whose data is
 * daily, because the curve and the policy path are what the books are priced
 * off. The macro board — VIX, energy, rates, the dollar, metals, the global
 * indices, crypto, with day-range bars — is last for the reason it was last
 * before: it is a screen tall, and the header strip already carries its
 * headline rows, so above the others it would bury them.
 *
 * RIGHT — what the day is scheduled to throw at it. The calendar first,
 * because it is where macro lives on this screen: the print that just landed
 * and its surprise are the most important fact on a data day, and on a quiet
 * day the calendar is what says it is quiet. Today's prints against
 * consensus and the Fed path under it (the stocks desk's read of the same
 * day), then the diaries — Fed & Treasury, earnings with the watchlist's
 * names marked, the sector peers reporting — and last the cross-asset moves
 * the names' drivers are read from.
 *
 * THE MARKET CONTEXT (prints, the Fed path, peers, cross-asset) is the
 * collector's, polled every twenty seconds by the Terminal and handed down;
 * the book, ranges, gamma and the tape count live on Structure.
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
const MRotation = memo(Rotation);
const MCalendar = memo(Calendar);
const MEarnings = memo(Earnings);
const MMovers = memo(Movers);
const MFed = memo(Fed);
const MPrintsFed = memo(PrintsFed);
const MCrossAsset = memo(CrossAsset);
const MPeers = memo(SectorPeers);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
// Hoisted: an array literal in JSX is a new prop every render and would defeat the memo.
const MACRO_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["vol", "energy", "rates", "fx", "metals", "global", "crypto"];

/** The sources this page reads — the board waits for each to have reported once. */
const SOURCES = ["quotes", "wire", "calendar", "sectors", "constituents", "rates", "fed", "auctions", "earnings"];

export function MacroBoard({ data, market: feed }: { data: TerminalData; market: MarketFeed }) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { watch, extra } = useWatchlistEarnings();
  const { ctx: market, failed } = feed;
  // The context's panels show only when it answered.
  const ctx = market?.offline ? null : market;
  const loading = market === null && !failed;

  // The index-minded block plus the watchlist's own reports, once each.
  const earnings = useMemo(() => {
    const base = data.earnings ?? NONE;
    if (extra.length === 0) return base;
    const have = new Set(base.map((r) => `${r.date}:${r.symbol}`));
    const add = extra.filter((r) => !have.has(`${r.date}:${r.symbol}`));
    return [...base, ...add].sort((a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0));
  }, [data.earnings, extra]);

  if (!boardReady(data, SOURCES, feed)) {
    return (
      <main className="flex min-h-0 flex-1 items-center justify-center">
        <HelmLoader label="Loading the desk" size={64} />
      </main>
    );
  }

  return (
    <main className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
      {/* ---- left: what the market is doing ------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MRotation rows={data.sectors ?? NONE} ageMin={age("sectors")} error={st.sectors?.ok === false ? st.sectors.error : null} />
        <MMovers indices={data.constituents?.indices ?? EMPTY} ageMin={age("constituents")} error={st.constituents?.ok === false ? st.constituents.error : null} />
        <MRates rates={data.rates} pm={data.policy_meetings} ageMin={age("rates")} error={st.rates?.ok === false ? st.rates.error : null} />
        <MBoard title="Macro board" quotes={data.quotes ?? NONE} groups={MACRO_GROUPS} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
      </div>

      {/* ---- middle: the wire -------------------------------------------- */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
        <MWire items={data.wire ?? NONE} ageMin={age("wire")} error={st.wire?.ok === false ? st.wire.error : null} />
      </div>

      {/* ---- right: what is scheduled ------------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MCalendar rows={data.calendar ?? NONE} ageMin={age("calendar")} error={st.calendar?.ok === false ? st.calendar.error : null} />
        {(ctx || loading) && <MPrintsFed prints={ctx?.prints ?? NONE} fed={ctx?.fed ?? null} builtUtc={ctx?.built_utc ?? ""} loading={loading} />}
        <MFed
          rows={data.fed ?? NONE}
          auctions={data.auctions ?? NONE}
          today={data.expiry?.today ?? ""}
          ageMin={raw.fed == null ? age("auctions") : raw.auctions == null ? age("fed") : (ageStep(Math.max(raw.fed, raw.auctions)) ?? undefined)}
          error={st.fed?.ok === false ? st.fed.error : st.auctions?.ok === false ? st.auctions.error : null}
        />
        <MEarnings rows={earnings} watch={watch} today={data.expiry?.today ?? ""} ageMin={age("earnings")} error={st.earnings?.ok === false ? st.earnings.error : null} />
        {(ctx || loading) && (
          <>
            <MPeers peers={ctx?.peers ?? null} />
            <MCrossAsset rows={ctx?.macro ?? null} />
          </>
        )}
      </div>
    </main>
  );
}
