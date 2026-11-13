"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { CalendarRow, ReportFeed, Terminal as TerminalData } from "@/types/terminal";
import { Header } from "@/components/shell/Header";
import { Sidebar } from "@/components/shell/Sidebar";
import { SideHeader } from "@/components/shell/SideHeader";
import { StatusRail } from "@/components/shell/StatusRail";
import { Scanner } from "@/components/panels/Scanner";
import { Settings } from "@/components/panels/Settings";
import { StockPlan } from "@/components/panels/StockPlan";
import { Dashboard } from "@/components/Dashboard";
import { MacroBoard } from "@/components/MacroBoard";
import { FuturesBoard } from "@/components/futures/FuturesBoard";
import { FUT_NAME, FUT_VIEW_KEYS, type FutView } from "@/lib/futures";
import { AlertStrip } from "@/components/shell/AlertStrip";
import { SectorsBoard } from "@/components/SectorsBoard";
import { QuoteTiles } from "@/components/market/QuoteTiles";
import { DASH_GROUPS, SCAN_GROUPS, SIDE_FUT_GROUPS, SIDE_GROUPS } from "@/lib/quoteTiles";
import { ScanAlerts } from "@/components/shell/ScanAlerts";
import { PinUndo } from "@/components/shell/PinUndo";
import { AskPanel } from "@/components/ask/AskPanel";
import { TickerDrawer } from "@/components/ticker/TickerDrawer";
import { closeTicker } from "@/lib/ticker";
import { TickerSearch } from "@/components/ticker/TickerSearch";
import { HermesTab } from "@/components/hermes/HermesTab";
import { useHermes } from "@/lib/hermes/useHermes";
import { useMarket } from "@/lib/useMarket";
import { DEFAULT_THEME, type ThemeChoice } from "@/lib/theme";
import { DEFAULT_UI, type UiMode } from "@/lib/ui";
import { UiProvider } from "@/components/state/UiMode";
import { OfflineProvider } from "@/components/state/Offline";
import { cn } from "@/lib/cn";
import { useReport } from "@/lib/useReport";
import { useStockPlan, type PlanController } from "@/lib/useStockPlan";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import {
  SCAN_VIEWS,
  SCAN_VIEW_KEYS,
  TAB_KEYS,
  askTab,
  deskOf,
  isDesk,
  pageTitle,
  tabLabel,
  type Desk,
  type ScanView,
  type Tab,
} from "@/lib/tabs";
import { useNow } from "@/lib/useNow";
import { shareUnchanged } from "@/lib/share";

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
const MStatusRail = memo(StatusRail);


export function Terminal({
  initial,
  initialReport,
  initialTab = "terminal",
  initialTabPinned,
  initialTheme = DEFAULT_THEME,
  initialUi = DEFAULT_UI,
  initialScanView,
  initialFutView,
}: {
  initial: TerminalData;
  initialReport: ReportFeed | null;
  initialTab?: Tab;
  /** The URL named a tab — see `urlPinned` below. */
  initialTabPinned?: boolean;
  initialTheme?: ThemeChoice;
  initialUi?: UiMode;
  /** The view the URL named inside its tab (an old `?tab=plan` link is the Scanner's Game plan); unset, the remembered one. */
  initialScanView?: ScanView;
  /** The same for Futures: an old `?tab=report` link is its Brief. */
  initialFutView?: FutView;
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
  // The Hermes tab's chats and its stream, owned here so an answer being
  // written survives a tab switch (useHermes).
  const hermes = useHermes();
  // The stocks desk's market context, polled here rather than by the board
  // that reads it (Macro: prints, the Fed path, peers, cross-asset), so leaving
  // the page and coming back does not start it over.
  const market = useMarket();

  /*
   * NO CHASSIS LIGHT (owner, 2026-11-13: "get rid of the ... frame light and lets
   * remove that from the app as well"). A comet ran the window's edge, or the whole
   * edge breathed, chosen in Settings and kept in storage as `frame.fx`; the frame is
   * plain now, with no setting, no hook and no ring element under it.
   */
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
   * THE DESK IS ONLY WHAT A QUESTION TO HERMES IS LABELLED WITH (lib/tabs.ts): the
   * side of the terminal the reader was last on, remembered. It was the Analysis
   * tab's switch until that tab went (2026-11-11); now a page that belongs to one
   * side says so as it is opened, and Macro, Hermes and Settings leave it be.
   */
  const [desk, setDesk] = usePersisted<Desk>("desk", "futures", isDesk);
  useEffect(() => {
    const d = deskOf(tab);
    if (d && d !== desk) setDesk(d);
    // The page's say when the page changes, not when the remembered desk loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  /*
   * The tab is written to the URL with replaceState rather than a navigation.
   * Both tabs are already mounted with their data in hand, so routing would
   * re-run the server component and re-fetch the collector to show something
   * the client is holding — all to change one query parameter.
   */
  const tabNow = useRef(tab);
  tabNow.current = tab;
  const setTab = useCallback((t: Tab) => {
    // THE SLIDE-OUT BELONGS TO THE PAGE IT WAS OPENED ON (owner, 2026-11-10): a
    // chart left out over the Scanner stayed out over the Dashboard. A tab click
    // is a change of subject, so the drawer goes with the page — from the bar
    // alone now that the number keys are gone; the Scanner's own view strip is not a
    // change of page and leaves it be.
    if (t !== tabNow.current) closeTicker();
    setTabState(t);
    setStoredTab(t);
    urlPinned.current = false;
    if (typeof window !== "undefined") {
      const u = new URL(window.location.href);
      if (t === "terminal") u.searchParams.delete("tab");
      else u.searchParams.set("tab", t);
      u.searchParams.delete("desk");
      window.history.replaceState(null, "", u);
    }
  }, [setStoredTab]);

  /*
   * THE SCANNER'S VIEW IS HELD HERE, NOT IN THE SCANNER, because the Dashboard's links
   * open a view by name and the question to Hermes is labelled with it. The Scanner's
   * own strip reads and writes the same value.
   */
  const [scanView, setScanView] = usePersisted<ScanView>("scan.view", "setups", oneOf(...SCAN_VIEW_KEYS));
  // The Futures section's view: the overview, a book, or the brief.
  const [futView, setFutView] = usePersisted<FutView>("fut.view", "overview", oneOf(...FUT_VIEW_KEYS));
  useEffect(() => {
    // The URL's say, once, after storage has had its turn (usePersisted): a link
    // to the plan or the report opens that view, whatever was open there last.
    if (initialScanView) setScanView(initialScanView);
    if (initialFutView) setFutView(initialFutView);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const openScan = useCallback(
    (v: ScanView) => {
      setScanView(v);
      setTab("scanner");
    },
    [setScanView, setTab],
  );
  // The Sidebar interface lists the Futures views beside the pages: one click opens one.
  const openFut = useCallback(
    (v: FutView) => {
      setFutView(v);
      setTab("futures");
    },
    [setFutView, setTab],
  );

  /*
   * NO KEYBOARD CONTROLS (owner, 2026-11-11: "can we remove the key board controls and
   * from the settings too"). The number keys reached the tabs and A opened Hermes; a
   * single key pressed outside a field changed the page. The tabs are the bar's, and
   * Hermes is the status rail's button. What is left is what any page does: Esc closes
   * what is open, and Ctrl+K is the search box's own, written on it.
   */

  // The browser tab says where you are: "HERMES · Scanner".
  useEffect(() => {
    document.title = pageTitle(tab);
  }, [tab]);

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
  const link = data.offline || !data.ok ? "offline" : lost ? "lost" : "live";
  /*
   * THE SIDEBAR INTERFACE HAS A SHELL OF ITS OWN (lib/ui.ts): the pages down the left
   * and, beside them, a header that names the page and carries the prices and the
   * search. Everything under a header is the same in every interface, so it is built
   * once (`below`) and set under whichever header this interface has.
   */
  const side = ui === "side";
  const quoteRow = (groups: readonly (readonly string[])[], form: { spread?: boolean; pills?: boolean } = {}) => (
    <QuoteTiles quotes={data.quotes ?? NONE} groups={groups} implied={data.volterm?.books} vixMonth={data.volterm?.vix_month} {...form} />
  );

  const below = (
    <>
        {/* Macro's own, where the wire is (owner, 2026-11-10: "remove the news rail
            above from everywhere except macro tab"). */}
        {tab === "terminal" && <AlertStrip items={data.wire ?? NONE} />}
        {/* Raises the scanner's alerts on every tab — see the file. */}
        <ScanAlerts />
        {/* Says so when a star takes a name off the pinned list, with an Undo. */}
        <PinUndo />
        {/* The assistant, mounted once; the status rail's button opens it. It is
            told the page as the collector names it: the Brief view as "report",
            the Game plan view as "plan". */}
        <AskPanel tab={askTab(tab, scanView, futView)} />
        <TickerSearch />

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

        {/* The page and the slide-out over it, between the header and the status rail. */}
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {tab === "dashboard" ? (
            <Dashboard
              calendar={data.calendar ?? NONE}
              onOpen={setTab}
              onScan={openScan}
              // In the Sidebar interface the four are in the header beside the page's
              // name, so the read's card does not carry them a second time.
              prices={side ? undefined : quoteRow(DASH_GROUPS, { spread: true })}
            />
          ) : tab === "settings" ? (
            <Settings theme={theme} onTheme={setTheme} ui={ui} onUi={setUi} />
          ) : tab === "hermes" ? (
            <HermesTab hermes={hermes} desk={desk} />
          ) : tab === "scanner" ? (
            <ScannerTab calendar={data.calendar ?? NONE} view={scanView} onView={setScanView} data={data} plan={plan} />
          ) : tab === "futures" ? (
            <FuturesBoard data={data} view={futView} onView={setFutView} report={report} />
          ) : tab === "sectors" ? (
            <SectorsBoard prices={quoteRow(SCAN_GROUPS)} />
          ) : (
            <MacroBoard data={data} market={market} />
          )}
          <TickerDrawer />
        </div>

        <MStatusRail status={st} ages={raw} feeds={data.wire_feeds} pollSec={POLL_SEC} lastPoll={lastPoll} />
    </>
  );

  return (
    <UiProvider value={ui}>
    <OfflineProvider value={Boolean(data.offline)}>
    <div className="h-screen overflow-hidden p-2 sm:p-3 qt:p-0 qt:sm:p-0">
      <div
        className={cn(
          "app-frame flex h-full w-full flex-col overflow-hidden",
          // Every figure that changes glitches before it glows. Subtle is the
          // whole useful range at this type size — see the note in globals.css
          // — so it is a constant rather than another switch in Settings.
          "fx-glitch-subtle",
        )}
      >
        {side ? (
          <div className="qt-side-shell flex min-h-0 flex-1">
            <Sidebar tab={tab} scanView={scanView} futView={futView} onTab={setTab} onScan={openScan} onFut={openFut} />
            <div className="qt-side-main flex min-h-0 min-w-0 flex-1 flex-col">
              <SideHeader
                title={shellTitle(tab, scanView, futView)}
                // Each desk's own prices beside its pages' names; the search finds
                // stocks, so the Futures pages do not carry it (lib/quoteTiles).
                quotes={quoteRow(tab === "futures" ? SIDE_FUT_GROUPS : SIDE_GROUPS, { pills: true })}
                search={tab !== "futures"}
                clock={data.clock ?? null}
                link={link}
                onRefresh={load}
              />
              {below}
            </div>
          </div>
        ) : (
          <>
            <Header clock={data.clock ?? null} link={link} onRefresh={load} tab={tab} onTab={setTab} />
            {below}
          </>
        )}
      </div>
    </div>
    </OfflineProvider>
    </UiProvider>
  );
}

/**
 * The page's name, as the Sidebar interface's header says it: the page, or on a page
 * with views the one that is open.
 */
function shellTitle(tab: Tab, scan: ScanView, fut: FutView): string {
  if (tab === "scanner") return SCAN_VIEWS.find((v) => v.key === scan)?.label ?? tabLabel(tab);
  if (tab === "futures") return fut === "overview" ? "Futures" : fut === "brief" ? "Futures brief" : `${fut} · ${FUT_NAME[fut]}`;
  return tabLabel(tab);
}

/*
 * Stable empties for a block the payload does not carry yet, so a missing
 * block is the same prop every render rather than a fresh `[]` or `{}`.
 */
const NONE: never[] = [];

/**
 * The Scanner with its own thirty-second clock for the headline ages — the
 * only time it prints — so its tick re-renders the scanner, not the shell.
 */
function ScannerTab({
  calendar,
  view,
  onView,
  data,
  plan,
}: {
  calendar: CalendarRow[];
  view: ScanView;
  onView: (v: ScanView) => void;
  data: TerminalData;
  /** The written game plan's state, the Terminal's, so a plan being written survives a change of page. */
  plan: PlanController;
}) {
  const now = useNow(30_000);
  return (
    <Scanner
      now={now}
      calendar={calendar}
      view={view}
      onView={onView}
      plan={view === "plan" ? <StockPlan {...plan} /> : null}
      prices={<QuoteTiles quotes={data.quotes ?? []} groups={SCAN_GROUPS} implied={data.volterm?.books} vixMonth={data.volterm?.vix_month} />}
    />
  );
}
