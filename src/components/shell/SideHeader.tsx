"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Clock } from "@/types/terminal";
import { nyClock } from "@/components/shell/Header";
import { Glyph } from "@/components/panels/ScanWide";
import { cn } from "@/lib/cn";
import { localClock, readerClock } from "@/lib/clock";
import { openSearch } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";

/**
 * The Sidebar interface's header: one card across the top of the page with the page's
 * name, the prices, the search, the session and the clock.
 *
 * WHY IT IS NOT THE OTHER HEADER RESTYLED (owner, 2026-11-12, of the reference
 * screenshots: "follow this layout closely - keeping our stuff we have"). In that
 * layout the pages are down the left, so the top carries no navigation: it says which
 * page this is, and beside that holds what every page needs in reach. The other
 * interfaces' header is the lockup, the tabs and the clock; here the lockup and the
 * pages are the sidebar's (shell/Sidebar), and what a page's own band carried (its
 * prices, the search box) is here, once, instead of on each page.
 *
 * `SHELL_ACTIONS_ID` is a slot a page fills with a button of its own (the Stocks
 * pages' Watchlist): the band it used to sit in is not drawn in this interface.
 */
export const SHELL_ACTIONS_ID = "shell-actions";

/**
 * A page's own button, drawn in the header's slot. The header is mounted before any
 * page, so the slot is there by the time a page's first effect looks for it; in an
 * interface with no such header there is no slot and nothing is drawn.
 */
export function ShellAction({ children }: { children: React.ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setSlot(document.getElementById(SHELL_ACTIONS_ID));
  }, []);
  return slot ? createPortal(children, slot) : null;
}

export function SideHeader({
  title,
  quotes,
  search,
  clock: rawClock,
  link,
  onRefresh,
}: {
  /** The page's name: "Dashboard", "Extended hours", "NQ · Nasdaq 100". */
  title: string;
  /** The prices for this page's desk, as capsules (market/QuoteTiles `pills`). */
  quotes?: React.ReactNode;
  /** The ticker search box: every page but the Futures ones, where it finds nothing they trade. */
  search: boolean;
  clock: Clock | null;
  /** The page's link to its data, as the other header says it (shell/Header). */
  link: "live" | "lost" | "offline";
  onRefresh: () => void;
}) {
  // The header owns its own second hand: the rest of the shell does not tick.
  const now = useNow(1000);
  const clock = localClock(rawClock, now);
  const local = readerClock(now);
  const ny = nyClock(clock);
  const nyOpen = Boolean(clock?.sessions.find((x) => x.key === "newyork")?.open);
  const phase = clock?.phase.label ?? null;
  // The session's mark: New York trading, the hours before it, or nothing open here.
  const dot = nyOpen ? "bg-call live-dot" : phase && /pre-?market/i.test(phase) ? "bg-flip-fig" : "bg-ink-4";

  return (
    <header className="qt-sidehead flex min-h-[58px] shrink-0 flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2.5">
      <h1 className="text-[18px] leading-none font-semibold whitespace-nowrap text-ink">{title}</h1>
      {quotes && <div className="flex min-w-0 items-center">{quotes}</div>}

      <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-2">
        {search && (
          <button
            type="button"
            onClick={openSearch}
            title="Find any ticker or company (Ctrl+K)"
            className="hit flex h-[32px] w-[clamp(170px,15vw,300px)] items-center gap-2 rounded-[8px] border border-ring-2 px-2.5 text-[12px] whitespace-nowrap text-ink-3"
          >
            <Glyph name="search" size={13} />
            <span className="min-w-0 flex-1 truncate text-left">Search ticker or company…</span>
            <span className="fig shrink-0 rounded-[4px] border border-ring-2 px-1.5 text-[10px]">Ctrl K</span>
          </button>
        )}
        {/* A page's own button (the Stocks pages' Watchlist), put here by the page. */}
        <span id={SHELL_ACTIONS_ID} className="flex items-center gap-2 empty:hidden" />

        {/*
          * TWO SHORT STACKS, NOT ONE LONG LINE. Side by side on one line ("Overlap · NY
          * opens in 50m 08:40:28 ET 23:40 AEST") the session and the clock were 400px,
          * and with a longer page name the header ran to a second line on a 1920
          * screen. Stacked, the session sits over New York's countdown and New York's
          * time over the reader's own: under half the width, and the header is one
          * line on every page.
          */}
        {clock && (
          <span className="flex shrink-0 flex-col justify-center gap-[5px] whitespace-nowrap" title={[clock.phase.label, clock.phase.note, ny?.title].filter(Boolean).join(" · ") || undefined}>
            <span className="flex items-center gap-1.5 text-[12px] leading-none text-ink-2">
              <span aria-hidden className={cn("h-[7px] w-[7px] rounded-full", dot)} />
              {clock.overlap ? <span className="text-flip-fig">Overlap</span> : phase}
            </span>
            {ny && (
              <span className="text-[11.5px] leading-none text-ink-3">
                {ny.label} <span className="fig text-ink">{ny.value}</span>
              </span>
            )}
          </span>
        )}
        {clock && (
          <span className="flex shrink-0 flex-col justify-center gap-[5px] whitespace-nowrap">
            <span className="flex items-baseline gap-1">
              <span className="fig text-[14.5px] leading-none text-ink">{clock.et_time}</span>
              <span className="eyebrow text-[9px]">ET</span>
            </span>
            {local && (
              <span className="flex items-baseline gap-1" title={`Your local time (${local.zone})`}>
                <span className="fig text-[11px] leading-none text-ink-3">{local.time}</span>
                <span className="eyebrow text-[9px]">{local.zone}</span>
              </span>
            )}
          </span>
        )}
        {/* Quiet when all is well, in words the moment it is not: as the other header. */}
        {link !== "live" && (
          <span
            className={cn("fig text-[10.5px] uppercase", link === "lost" ? "text-warn" : "text-err")}
            title={link === "lost" ? "The last refresh failed — the figures on screen are from the last one that landed" : "The collector is not answering"}
          >
            {link === "lost" ? "Stale" : "Offline"}
          </span>
        )}
        <button
          type="button"
          onClick={onRefresh}
          aria-label="Refresh"
          title={link === "live" ? "Live — refresh now" : "Refresh"}
          className="hit inline-flex h-[30px] w-[30px] items-center justify-center rounded-[8px] border border-ring-2 text-ink-3 hover:text-ink"
        >
          <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" />
            <path d="M21 3v5h-5" />
          </svg>
        </button>
      </div>
    </header>
  );
}
