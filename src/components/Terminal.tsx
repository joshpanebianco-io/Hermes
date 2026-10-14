"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { CalendarRow, ReportFeed, Terminal as TerminalData } from "@/types/terminal";
import { Header } from "@/components/shell/Header";
import { StatusRail } from "@/components/shell/StatusRail";
import { Wire } from "@/components/panels/Wire";
import { Board } from "@/components/panels/Board";
import { Gamma } from "@/components/panels/Gamma";
import { Rates } from "@/components/panels/Rates";
import { Rotation } from "@/components/panels/Rotation";
import { Calendar } from "@/components/panels/Calendar";
import { Sessions } from "@/components/panels/Sessions";
import { Report } from "@/components/panels/Report";
import { Scanner } from "@/components/panels/Scanner";
import { StockPlan } from "@/components/panels/StockPlan";
import { MarketBoard } from "@/components/MarketBoard";
import { Settings } from "@/components/panels/Settings";
import { SessionRanges } from "@/components/panels/SessionRanges";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import { Volatility } from "@/components/panels/Volatility";
import { VolumeProfile } from "@/components/panels/VolumeProfile";
import { Fed } from "@/components/panels/Fed";
import { AlertStrip } from "@/components/shell/AlertStrip";
import { ScanAlerts } from "@/components/shell/ScanAlerts";
import { AskPanel } from "@/components/ask/AskPanel";
import { openAsk } from "@/lib/ask/open";
import { DEFAULT_THEME, type ThemeChoice } from "@/lib/theme";
import { DEFAULT_UI, type UiMode } from "@/lib/ui";
import { UiProvider } from "@/components/state/UiMode";
import { OfflineProvider } from "@/components/state/Offline";
import { cn } from "@/lib/cn";
import { useReport } from "@/lib/useReport";
import { useStockPlan } from "@/lib/useStockPlan";
import { useFrameLight, type FrameFx } from "@/lib/useFrameLight";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { DESK_HOME, TAB_KEYS, deskOf, isDesk, pageTitle, tabsFor, type Desk, type Tab } from "@/lib/tabs";
import { useNow } from "@/lib/useNow";
import { shareUnchanged } from "@/lib/share";
import { ageStep } from "@/lib/format";

/**
 * The terminal.
 *
 * THREE COLUMNS, AND THE MIDDLE ONE IS THE WIRE. The layout encodes what this
 * product is for: context on the left (the clock, the gamma structure, the
 * curve), news in the middle where the eye rests, prices and rotation on the
 * right. A four-column grid of equal panes would be prettier and would say
 * nothing about which of them you are meant to be reading.
 *
 * THE CHASSIS IS EXACTLY ONE VIEWPORT AND THE COLUMNS SCROLL INSIDE IT.
 *
 * The first cut let the page grow and scroll as a whole, which read fine until
 * you noticed the status rail had scrolled off the bottom — the one element
 * that must never be out of sight, because it is the only thing that says
 * whether what you are looking at is live. A terminal's state line is pinned
 * or it is decoration.
 *
 * Three scroll regions rather than nine: the columns, not the panels. The
 * right-hand column alone is around 1700px of board and calendar, so something
 * has to scroll; doing it per COLUMN keeps each one a single continuous
 * reading position instead of turning the grid into a filing cabinet of
 * independently-lost boxes.
 *
 * THE CLOCK TICKS LOCALLY — but not HERE. It used to: `now` lived in this
 * component and changed every second, so the whole board re-rendered once a
 * second to move four clocks. The tick now lives in `useNow`, read only by
 * the components that print a time (the header, the session table, the ages
 * on the crawl and the wire), and the panels are memoised so a poll re-renders
 * only those whose data moved — see `shareUnchanged` and `ageStep`.
 */

const POLL_SEC = Number(process.env.NEXT_PUBLIC_POLL_SEC ?? 20);
/** A poll still unanswered after this is abandoned and counted as failed. */
const POLL_TIMEOUT_MS = 15_000;

/*
 * The panels, memoised. Their props are the payload's blocks, which a poll
 * keeps by reference when they did not change (`shareUnchanged`), and ages
 * rounded to what the chip prints (`ageStep`) — so a twenty-second poll
 * re-renders the board, not the calendar that refreshes every ten minutes.
 */
const MSessionRanges = memo(SessionRanges);
const MVolumeProfile = memo(VolumeProfile);
const MGamma = memo(Gamma);
const MVolatility = memo(Volatility);
const MRates = memo(Rates);
const MSessions = memo(Sessions);
const MWire = memo(Wire);
const MBoard = memo(Board);
const MCalendar = memo(Calendar);
const MMovers = memo(Movers);
const MRotation = memo(Rotation);
const MFed = memo(Fed);
const MEarnings = memo(Earnings);
const MStatusRail = memo(StatusRail);

// Hoisted: an array literal in JSX is a new prop every render and would defeat
// the memo above.
const BOOK_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["core"];
const MACRO_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["vol", "energy", "rates", "fx", "metals", "global", "crypto"];

export function Terminal({
  initial,
  initialReport,
  initialTab = "terminal",
  initialTabPinned,
  initialTheme = DEFAULT_THEME,
  initialUi = DEFAULT_UI,
}: {
  initial: TerminalData;
  initialReport: ReportFeed | null;
  initialTab?: Tab;
  /** The URL named a tab — see `urlPinned` below. */
  initialTabPinned?: boolean;
  initialTheme?: ThemeChoice;
  initialUi?: UiMode;
}) {
  // Held here rather than in Settings so the tab can be left and returned to
  // without the picker forgetting what is selected. The cookie is the durable
  // copy; this is only what the open page believes.
  const [theme, setTheme] = useState<ThemeChoice>(initialTheme);
  // The interface, held for the same reason; the cookie and the class on
  // <html> are the durable copy (Settings writes both).
  const [ui, setUi] = useState<UiMode>(initialUi);

  /*
   * The report's state is owned HERE rather than in its panel, so a generation
   * survives switching tabs — see `useReport`. It takes minutes on a free
   * model, and the panel unmounting was cancelling it.
   */
  const report = useReport(initialReport);
  // The Game plan's state, owned here for the same reason as the report's.
  const plan = useStockPlan(null);

  /*
   * The chassis light. Held here because the frame it draws on lives here, and
   * persisted so the choice survives a reload like every other preference.
   * `useFrameLight` only drives "travel" — breathe is pure CSS and off hides
   * the ring, and for both the hook stands down and cancels any comet left
   * running from a live switch.
   */
  const [fx, setFx] = usePersisted<FrameFx>(
    "frame.fx",
    "travel",
    oneOf("off", "travel", "breathe"),
  );
  const frameRef = useRef<HTMLDivElement | null>(null);
  useFrameLight(frameRef, fx);
  /*
   * The URL wins over storage when it says something. `?tab=report` is an
   * explicit instruction from whoever followed the link; the remembered tab is
   * only what this browser last looked at, and a deep link that silently landed
   * somewhere else would be worse than not remembering at all.
   */
  const [storedTab, setStoredTab] = usePersisted<Tab>("tab", initialTab, oneOf(...TAB_KEYS));
  const [tab, setTabState] = useState<Tab>(initialTab);
  /*
   * INFERRING THIS FROM THE TAB ITSELF IS WHAT BROKE IT. `initialTab !== "terminal"`
   * reads a pin off the destination, which cannot tell `?tab=terminal` — an
   * instruction — from a bare `/`, which is not one. Both resolve to "terminal",
   * so both fell through to the remembered tab, and the desktop shortcut opened
   * on the report. The server knows which of the two it saw; it says so.
   */
  const urlPinned = useRef(initialTabPinned ?? initialTab !== "terminal");
  useEffect(() => {
    if (!urlPinned.current && storedTab !== tab) setTabState(storedTab);
    // Runs when storage lands after mount; a later user click owns it from
    // then on and this must not fight them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storedTab]);

  /*
   * THE DESK IS THE TAB'S, except on Settings, which belongs to both — there
   * the desk you came from stays, so the header keeps its strip and its tabs.
   * Each desk remembers its own last tab, so the switch returns you to the
   * Scanner you left rather than to the desk's front page.
   */
  const [savedDesk, setSavedDesk] = usePersisted<Desk>("desk", deskOf(initialTab) ?? "futures", isDesk);
  const desk: Desk = deskOf(tab) ?? savedDesk;
  const [lastFutures, setLastFutures] = usePersisted<Tab>("tab.futures", DESK_HOME.futures, oneOf("terminal", "report"));
  const [lastStocks, setLastStocks] = usePersisted<Tab>("tab.stocks", DESK_HOME.stocks, oneOf("market", "scanner", "plan"));

  /*
   * The tab is written to the URL with replaceState rather than a navigation.
   * Both tabs are already mounted with their data in hand, so routing would
   * re-run the server component and re-fetch the collector to show something
   * the client is holding — all to change one query parameter.
   */
  const setTab = useCallback((t: Tab) => {
    setTabState(t);
    setStoredTab(t);
    const d = deskOf(t);
    if (d) {
      setSavedDesk(d);
      if (d === "futures") setLastFutures(t);
      else setLastStocks(t);
    }
    urlPinned.current = false;
    if (typeof window !== "undefined") {
      const u = new URL(window.location.href);
      if (t === "terminal") u.searchParams.delete("tab");
      else u.searchParams.set("tab", t);
      window.history.replaceState(null, "", u);
    }
  }, [setStoredTab, setSavedDesk, setLastFutures, setLastStocks]);

  const switchDesk = useCallback(
    (d: Desk) => setTab(d === "futures" ? lastFutures : lastStocks),
    [setTab, lastFutures, lastStocks],
  );

  /*
   * THE KEYBOARD. 1–4 reach the current desk's tabs in bar order (Settings
   * last), D flips the desk, A opens Hermes. Never while typing — the
   * watchlist editor, the inputs and Hermes's own box own their keys — and
   * never with a modifier held, so the browser's own shortcuts are untouched.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (e.key === "d" || e.key === "D") {
        e.preventDefault();
        switchDesk(desk === "futures" ? "stocks" : "futures");
        return;
      }
      // A — ask Hermes; again to put it away.
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        openAsk();
        return;
      }
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1) {
        const t = tabsFor(desk)[n - 1];
        if (t) {
          e.preventDefault();
          setTab(t.key);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desk, setTab, switchDesk]);

  // The browser tab says where you are: "HERMESX · Stocks & Options · Scanner".
  useEffect(() => {
    document.title = pageTitle(tab, desk);
  }, [tab, desk]);

  const [data, setData] = useState<TerminalData>(initial);
  const [lastPoll, setLastPoll] = useState<Date | null>(null);
  // Guards against a slow response landing after a newer one — with a fixed
  // interval and a variable round trip this is not hypothetical.
  const seq = useRef(0);
  // The previous poll's block serialisations — see `shareUnchanged`.
  const seen = useRef(new Map<string, string>());

  // A failed poll, remembered. The previous payload stays on screen — it is
  // still the best there is — but the header stops calling it live and a
  // banner says since when (audit, 2026-10-14: sixty-five seconds of failed
  // polls still read LIVE beside a green dot).
  const [lost, setLost] = useState<Date | null>(null);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    // A poll that never answers is a failure too, not a pending forever.
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), POLL_TIMEOUT_MS);
    try {
      const r = await fetch("/api/terminal", { cache: "no-store", signal: ctl.signal });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const next = (await r.json()) as TerminalData;
      if (mine === seq.current) {
        setData((prev) => shareUnchanged(prev, next, seen.current));
        setLastPoll(new Date());
        setLost(null);
      }
    } catch {
      // The route handler already turns a dead collector into a body with an
      // `offline` block; reaching here means the Next server itself is gone
      // or hung. The previous payload with its ages climbing is the honest
      // render — said as such.
      if (mine === seq.current) setLost((was) => was ?? new Date());
    } finally {
      clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    const id = setInterval(load, POLL_SEC * 1000);
    return () => clearInterval(id);
  }, [load]);

  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;

  return (
    <UiProvider value={ui}>
    <OfflineProvider value={Boolean(data.offline)}>
    <div className="h-screen overflow-hidden p-2 sm:p-3 qt:p-0 qt:sm:p-0">
      <div
        ref={frameRef}
        className={cn(
          "app-frame flex h-full w-full flex-col overflow-hidden",
          `fx-${fx}`,
          // Every figure that changes glitches before it glows. Subtle is the
          // whole useful range at this type size — see the note in globals.css
          // — so it is a constant rather than another switch in Settings.
          "fx-glitch-subtle",
        )}
      >
        {/* The travelling light's ring and the gradient that turns inside it —
            see `.frame-light` in globals.css and useFrameLight. */}
        <div className="frame-light" aria-hidden>
          <div className="frame-light__spin" />
        </div>

        <Header
          clock={data.clock ?? null}
          quotes={data.quotes ?? []}
          link={data.offline || !data.ok ? "offline" : lost ? "lost" : "live"}
          onRefresh={load}
          tab={tab}
          onTab={setTab}
          desk={desk}
          onDesk={switchDesk}
        />

        <AlertStrip items={data.wire ?? NONE} />
        {/* Raises the scanner's alerts on every tab — see the file. */}
        <ScanAlerts />
        {/* The assistant, mounted once; the rail's key and A open it. */}
        <AskPanel tab={tab} />

        {lost && !data.offline && (
          <div className="border-b border-warn/40 bg-warn/10 px-3 py-2 text-[11px] text-warn">
            <strong className="font-semibold">Lost contact with the terminal&apos;s server</strong> at{" "}
            {lost.toLocaleTimeString("en-US", { hour12: false })}. Everything below is from the last refresh that
            landed{lastPoll ? ` (${lastPoll.toLocaleTimeString("en-US", { hour12: false })})` : ""} and is not
            updating; it retries every {POLL_SEC}s.
          </div>
        )}
        {data.offline && (
          <div className="border-b border-err/40 bg-err/10 px-3 py-2 text-[11px] text-err">
            <strong className="font-semibold">Collector offline.</strong> {data.offline.reason} —
            expected at <code>{data.offline.api}</code>. Every panel below is empty because there is
            nothing behind it; nothing here is cached or fabricated. Start it with{" "}
            <code className="text-ink-2">.\dev.ps1</code>.
          </div>
        )}

        {tab === "settings" ? (
          <Settings theme={theme} onTheme={setTheme} fx={fx} onFx={setFx} ui={ui} onUi={setUi} />
        ) : tab === "report" ? (
          <Report {...report} />
        ) : tab === "scanner" ? (
          <ScannerTab calendar={data.calendar ?? NONE} />
        ) : tab === "plan" ? (
          <StockPlan {...plan} />
        ) : tab === "market" ? (
          <MarketBoard data={data} />
        ) : (
        <main className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
          {/* ---- left: the context the news is read against ------------- */}
          <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
            {/*
             * ORDERED BY WHAT YOU ACT ON, not by what orients you. The two
             * panels you trade against lead: where price sits inside each
             * session's range is the handover read this terminal exists for,
             * and the seven gamma levels are the prices you place orders at.
             *
             * The vol term structure is fourth because it is the regime read
             * that frames the three above it — contango or backwardation says
             * whether a wall is likely to hold — and it reprices every twenty
             * seconds. Rates follows DESPITE being an explicit requirement,
             * because it is the only panel here whose data is daily: the curve
             * stamps a date, not a time, and cannot move during a session.
             *
             * The session clock is LAST, moved down from third (owner,
             * 2026-09-16: most important at the top, descending). The header
             * already carries the ET time and the phase ("NY midday"); what
             * this panel uniquely adds is the city table and the NEXT marker —
             * reference you consult, not a figure you act on. Ordering by how
             * often something can change you is the only ordering that
             * survives contact with a fold, and a clock never changes you.
             */}
            <MSessionRanges
              assets={data.ranges?.assets ?? EMPTY}
              expiry={data.expiry}
              ageMin={age("ranges")}
              error={st.ranges?.ok === false ? st.ranges.error : null}
            />
            <MVolumeProfile
              data={data.profiles}
              ageMin={age("profiles")}
              error={st.profiles?.ok === false ? st.profiles.error : null}
            />
            <MGamma
              assets={data.gex?.assets ?? EMPTY}
              enabled={data.gex?.enabled ?? false}
              ageMin={age("gex")}
              error={st.gex?.ok === false ? st.gex.error : null}
            />
            <MVolatility vol={data.volterm} ageMin={age("quotes")} />
            <MRates
              rates={data.rates}
              pm={data.policy_meetings}
              ageMin={age("rates")}
              error={st.rates?.ok === false ? st.rates.error : null}
            />
            {data.clock && <MSessions clock={data.clock} />}
          </div>

          {/* ---- middle: the wire --------------------------------------- */}
          <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
            <MWire
              items={data.wire ?? NONE}
              ageMin={age("wire")}
              error={st.wire?.ok === false ? st.wire.error : null}
            />
          </div>

          {/* ---- right: prices and rotation ----------------------------- */}
          <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
            <MBoard
              title="The book"
              quotes={data.quotes ?? NONE}
              groups={BOOK_GROUPS}
              ageMin={age("quotes")}
              error={st.quotes?.ok === false ? st.quotes.error : null}
            />
            <MCalendar
              rows={data.calendar ?? NONE}
              ageMin={age("calendar")}
              error={st.calendar?.ok === false ? st.calendar.error : null}
            />
            <MMovers
              indices={data.constituents?.indices ?? EMPTY}
              ageMin={age("constituents")}
              error={st.constituents?.ok === false ? st.constituents.error : null}
            />
            {/*
             * THE BOOK, THEN THE MACRO, THEN WHAT THE MACRO DID TO THE BOOK,
             * then the diaries. Reordered 2026-09-16 on the owner's principle
             * that importance descends down the column, and their view that
             * macro is what moves these books.
             *
             * The CALENDAR is second because it is where macro lives on this
             * screen: the print that just landed and its surprise are the most
             * important fact on a data day, and on a quiet day the calendar is
             * what says it is quiet — which is itself the frame. It used to sit
             * fourth, behind Movers and Rotation, on the grounds that a
             * 221-row list buried everything below it; it is now capped at
             * 340px with its own scroll, so that objection no longer holds.
             * Movers and Rotation follow as the CONSEQUENCES of the macro —
             * which names and which sectors carried the move — not its causes.
             *
             * The MACRO BOARD moved up from last, where it sat below three
             * diaries in a column whose own rule was "live state above what is
             * scheduled": it is live prices. It stays below the panels above it
             * only because the header strip already carries its headline rows
             * (VIX, US10Y, DXY, WTI). Fed and Earnings are diaries, and go last.
             */}
            <MRotation
              rows={data.sectors ?? NONE}
              ageMin={age("sectors")}
              error={st.sectors?.ok === false ? st.sectors.error : null}
            />
            <MBoard
              title="Macro board"
              quotes={data.quotes ?? NONE}
              groups={MACRO_GROUPS}
              ageMin={age("quotes")}
            />
            <MFed
              rows={data.fed ?? NONE}
              auctions={data.auctions ?? NONE}
              today={data.expiry?.today ?? ""}
              ageMin={
                raw.fed == null
                  ? age("auctions")
                  : raw.auctions == null
                    ? age("fed")
                    : (ageStep(Math.max(raw.fed, raw.auctions)) ?? undefined)
              }
              error={
                st.fed?.ok === false
                  ? st.fed.error
                  : st.auctions?.ok === false
                    ? st.auctions.error
                    : null
              }
            />
            <MEarnings
              rows={data.earnings ?? NONE}
              today={data.expiry?.today ?? ""}
              ageMin={age("earnings")}
              error={st.earnings?.ok === false ? st.earnings.error : null}
            />
          </div>
        </main>
        )}

        <MStatusRail status={st} ages={raw} pollSec={POLL_SEC} lastPoll={lastPoll} />
      </div>
    </div>
    </OfflineProvider>
    </UiProvider>
  );
}

/*
 * Stable empties for a block the payload does not carry yet, so a missing
 * block is the same prop every render rather than a fresh `[]` or `{}`.
 */
const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;

/**
 * The Scanner with its own thirty-second clock for the headline ages — the
 * only time it prints — so its tick re-renders the scanner, not the shell.
 */
function ScannerTab({ calendar }: { calendar: CalendarRow[] }) {
  const now = useNow(30_000);
  return <Scanner now={now} calendar={calendar} />;
}
