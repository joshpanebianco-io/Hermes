"use client";

import { memo, useMemo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import { Wire } from "@/components/panels/Wire";
import { Board } from "@/components/panels/Board";
import { Rates, type TenLive } from "@/components/panels/Rates";
import { Calendar } from "@/components/panels/Calendar";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import type { MarketFeed } from "@/lib/useMarket";
import { useWatchlistEarnings } from "@/lib/useWatchlistEarnings";
import { inWindow } from "@/lib/earningsOrder";
import { boardReady } from "@/lib/ready";
import { PageLoader } from "@/components/ui/HelmLoader";
import { Module } from "@/components/ui/Module";
import { OutlookBody } from "@/components/panels/MarketOutlook";
import type { MarketOutlook } from "@/types/outlook";
import { ageStep } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

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
 * Scanner's names marked, then the macro board. Earnings is the card that gives: it takes
 * the room the other two leave and scrolls inside it, so the whole board is on screen.
 *
 * RIGHT: the calendar, then Rates & policy, the curve and the Fed path, under it.
 *
 * THE BOARD AND RATES & POLICY CHANGED PLACES (owner, 2026-11-15: "switch rate and policy
 * with macro board"). What is said further down of the board sitting under the calendar
 * is how it stood from 2026-11-14 until then.
 *
 * THE FED & TREASURY DIARY IS IN THE CALENDAR (owner, 2026-11-14, of an audit of these
 * cards: "do what you recommend"). It was the third card here, a screen below the fold
 * under a 1,567px board, and its speakers were already calendar rows. Its decisions,
 * minutes, Beige Books and coupon auctions are rows of the calendar now (lib/schedule),
 * the calendar reaches a week ahead instead of three days and takes the room the board
 * leaves, and the board draws in two columns on a wide card. Hermes still reads the
 * diary and the auctions through its own panels.
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

type BoardView = "board" | "outlook";
const BOARD_VIEWS: ReadonlyArray<{ key: BoardView; label: string; title: string }> = [
  { key: "board", label: "Board", title: "Every price, by group" },
  { key: "outlook", label: "Market Pulse", title: "Today's risk appetite, and stocks, bonds, the dollar, metals, oil and bitcoin read against each other" },
];

/**
 * THE MACRO BOARD, OR THE MARKET PULSE IN ITS CARD (owner, 2026-11-21, of the card then
 * named Market Outlook: "have it as a toggle option on the MAcro Board in MAcro"). One
 * switch in the card's head, as Index movers has its two, remembered like every other
 * choice. The board is every price a row each; the pulse is eight of those prices read
 * against each other under a fear-to-greed scale (panels/MarketOutlook), the same body the
 * Dashboard's card draws, with the board's own quotes for its lines.
 */
function BoardCard({
  quotes,
  groups,
  outlook,
  ageMin,
  error,
}: {
  quotes: React.ComponentProps<typeof Board>["quotes"];
  groups: React.ComponentProps<typeof Board>["groups"];
  outlook: MarketOutlook | null | undefined;
  ageMin?: number | null;
  error?: string | null;
}) {
  const [view, setView] = usePersisted<BoardView>("macro.board", "board", oneOf("board", "outlook"));
  const pick = (
    <div className="seg">
      {BOARD_VIEWS.map((v) => (
        <button key={v.key} type="button" onClick={() => setView(v.key)} title={v.title} {...segItem(v.key === view, { className: "text-[10px] normal-case tracking-normal" })}>
          {v.label}
        </button>
      ))}
    </div>
  );
  if (view === "board") return <Board title="Macro board" twoUp quotes={quotes} groups={groups} ageMin={ageMin} error={error} right={pick} />;
  return (
    <Module title="Macro board" sub={outlook?.ok ? outlook.label : undefined} ageMin={ageMin} error={error} right={pick} bodyClassName="px-0 py-0">
      <OutlookBody d={outlook} quotes={quotes} dense />
    </Module>
  );
}

const MWire = memo(Wire);
const MBoard = memo(BoardCard);
const MRates = memo(Rates);
const MCalendar = memo(Calendar);
const MEarnings = memo(Earnings);
const MMovers = memo(Movers);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
// Hoisted: an array literal in JSX is a new prop every render and would defeat the memo.
// The order drawn: VIX and its curve, then rates, then the rest as they were.
const MACRO_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["vol", "rates", "global", "fx", "energy", "metals", "crypto"];
/**
 * THE ROWS FURTHEST FROM THE BOOKS, OFF THE CARD (owner, 2026-11-17: "reduce the height of
 * the macro board card a bit and increase the Earnings card", the third such ask; the rows
 * were already at their 16.5px floor, so the room came from rows). Shanghai, KOSPI and the
 * ASX (Nikkei and Hang Seng carry Asia), the CAC (Stoxx 50 and the DAX carry Europe),
 * platinum, wheat and corn. Hidden here only: the collector still reads them, and Hermes
 * and the bias still have them.
 */
const OFF_BOARD = new Set(["SHCOMP", "KOSPI", "ASX", "CAC", "PLAT", "WHEAT", "CORN"]);

/** The sources this page reads — the board waits for each to have reported once. */
const SOURCES = ["quotes", "wire", "calendar", "constituents", "rates", "fed", "auctions", "earnings"];

export function MacroBoard({ data, market: feed }: { data: TerminalData; market: MarketFeed }) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { watch, extra } = useWatchlistEarnings();

  // The index-minded block plus the watchlist's own reports, once each, and the
  // watchlist's only inside the block's own window (lib/earningsOrder inWindow).
  const today = data.expiry?.today ?? "";
  const earnings = useMemo(() => {
    const base = data.earnings ?? NONE;
    if (extra.length === 0) return base;
    const have = new Set(base.map((r) => `${r.date}:${r.symbol}`));
    const add = extra.filter((r) => !have.has(`${r.date}:${r.symbol}`) && inWindow(r.date, today));
    return [...base, ...add].sort((a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0));
  }, [data.earnings, extra, today]);

  // GOLD LEADS METALS & AGS (owner, 2026-11-14: "i dont see gold in the metals and
  // ags?"). The collector files the gold future with the books (group "core", which
  // this board does not draw: it is the Futures tab's), so silver, copper and platinum
  // were listed here and gold was not. It is the same GC row, drawn again at the head
  // of the metals. A copy made here, not a second row in the collector: one fetch,
  // one price, and nothing else that reads the books sees gold twice.
  const boardQuotes = useMemo(() => {
    const all = (data.quotes ?? NONE).filter((q) => !OFF_BOARD.has(q.key));
    const gc = all.find((q) => q.key === "GC");
    const at = all.findIndex((q) => q.group === "metals");
    if (!gc || at < 0) return all;
    return [...all.slice(0, at), { ...gc, group: "metals" as const }, ...all.slice(at)];
  }, [data.quotes]);

  // The 10Y for the Rates card's first line, WHILE THE DRIVER BOARD SAYS IT IS LIVE
  // (drivers._yields: the cash 10Y trading, no bond holiday). Outside that the card
  // falls back to the Treasury's last close with its day. Primitives, so the memoised
  // card redraws when the figure changes and not on every poll.
  const tenQ = (data.quotes ?? NONE).find((q) => q.key === "US10Y");
  const tenV = data.drivers?.books?.NQ?.votes?.find((v) => v.key === "yields");
  const tenLast = tenV?.live && tenQ ? tenQ.last : null;
  const tenChg = tenV?.live && tenQ ? tenQ.chg : null;
  const tenVote = tenV?.vote ?? "neutral";
  const ten = useMemo<TenLive | null>(
    () => (tenLast != null && tenChg != null ? { last: tenLast, chgBp: Math.round(tenChg * 1000) / 10, vote: tenVote } : null),
    [tenLast, tenChg, tenVote],
  );

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
  // The session is over: from the 16:00 ET close to midnight, and through a weekend.
  // The Earnings card then lists what is coming above what has been traded.
  const afterClose = !cashOpen && (data.clock?.weekend === true || Number.parseInt(data.clock?.et_time ?? "", 10) >= 16);

  // A source showing its last good copy says why in its status even while it is ok
  // (the holdings file behind Index movers, 37 hours old on 2026-11-14 with live
  // prices on top): the age chip's hover carries it, so a red age names its cause.
  const why = (k: string) => (st[k]?.ok && st[k]?.error ? st[k].error : null);

  return (
    <main className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
      {/* ---- left: what the market is doing ------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MMovers indices={data.constituents?.indices ?? EMPTY} cashOpen={cashOpen} ageMin={age("constituents")} ageNote={why("constituents")} error={st.constituents?.ok === false ? st.constituents.error : null} />
        <MEarnings rows={earnings} watch={watch} today={data.expiry?.today ?? ""} afterClose={afterClose} ageMin={age("earnings")} error={st.earnings?.ok === false ? st.earnings.error : null} />
        {/* The board and Rates & policy changed places (owner, 2026-11-15: "switch rate and
            policy with macro board"): prices sit with the movers on the left, the Fed's path
            with the calendar it is priced off on the right. */}
        <MBoard quotes={boardQuotes} groups={MACRO_GROUPS} outlook={data.outlook} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
      </div>

      {/* ---- middle: the wire -------------------------------------------- */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
        <MWire items={data.wire ?? NONE} ageMin={age("wire")} error={st.wire?.ok === false ? st.wire.error : null} />
      </div>

      {/* ---- right: what is scheduled ------------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MCalendar
          rows={data.calendar ?? NONE}
          fed={data.fed ?? NONE}
          auctions={data.auctions ?? NONE}
          holidays={data.holidays ?? NONE}
          expiry={data.expiry ?? null}
          ageMin={age("calendar")}
          // The diary and the auctions are rows of this card now: if either source is
          // down, this is the card that says so.
          error={st.calendar?.ok === false ? st.calendar.error : st.fed?.ok === false ? `Fed diary: ${st.fed.error}` : st.auctions?.ok === false ? `Treasury auctions: ${st.auctions.error}` : null}
        />
        <MRates rates={data.rates} pm={data.policy_meetings} ten={ten} ageMin={age("rates")} error={st.rates?.ok === false ? st.rates.error : null} />
      </div>
    </main>
  );
}
