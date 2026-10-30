"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { CalendarRow, ReportFeed, Terminal as TerminalData } from "@/types/terminal";
import { Header } from "@/components/shell/Header";
import { StatusRail } from "@/components/shell/StatusRail";
import { Scanner } from "@/components/panels/Scanner";
import { Settings } from "@/components/panels/Settings";
import { Analysis } from "@/components/panels/Analysis";
import { MacroBoard } from "@/components/MacroBoard";
import { StructureBoard } from "@/components/StructureBoard";
import { AlertStrip } from "@/components/shell/AlertStrip";
import { ScanAlerts } from "@/components/shell/ScanAlerts";
import { AskPanel } from "@/components/ask/AskPanel";
import { HermesTab } from "@/components/hermes/HermesTab";
import { useHermes } from "@/lib/hermes/useHermes";
import { useMarket } from "@/lib/useMarket";
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
import { DESK_TABS, TABS, TAB_KEYS, askTab, isDesk, pageTitle, type Desk, type Tab } from "@/lib/tabs";
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
  initialDesk,
}: {
  initial: TerminalData;
  initialReport: ReportFeed | null;
  initialTab?: Tab;
  /** The URL named a tab — see `urlPinned` below. */
  initialTabPinned?: boolean;
  initialTheme?: ThemeChoice;
  initialUi?: UiMode;
  /** The Analysis half the URL named (`?desk=`, or an old `?tab=report` / `plan` link); unset, the remembered one. */
  initialDesk?: Desk;
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
  // The stocks desk's market context, polled here rather than by the boards
  // that read it, so switching between Macro and Structure does not start it
  // over — and the boards' one loader (lib/ready.ts) does not show twice.
  const market = useMarket();

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
   * THE DESK IS THE ANALYSIS TAB'S QUESTION, nothing else's (owner,
   * 2026-10-30 — see lib/tabs.ts). It is the half of that tab you last read,
   * remembered; a link may name it (`?desk=`), and an old link to the report
   * or the plan names it by implication (lib/tabs.ts resolveTab) — either
   * wins over what is remembered, written through so the next load agrees.
   */
  const [desk, setDeskState] = usePersisted<Desk>("desk", initialDesk ?? "futures", isDesk);
  useEffect(() => {
    if (initialDesk) setDeskState(initialDesk);
    // The URL's say, once, after storage has had its turn (usePersisted).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /*
   * The tab is written to the URL with replaceState rather than a navigation.
   * Both tabs are already mounted with their data in hand, so routing would
   * re-run the server component and re-fetch the collector to show something
   * the client is holding — all to change one query parameter.
   */
  const setTab = useCallback((t: Tab) => {
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

  /**
   * The desk — the brief or the plan on Analysis, the futures or the stocks
   * half of Structure — one remembered choice for both tabs, and named in
   * the URL while a tab that wears the switch is open.
   */
  const setDesk = useCallback((d: Desk) => {
    setDeskState(d);
    if (typeof window !== "undefined") {
      const u = new URL(window.location.href);
      if (!DESK_TABS.has(tab)) u.searchParams.set("tab", "analysis");
      u.searchParams.set("desk", d);
      window.history.replaceState(null, "", u);
    }
  }, [setDeskState, tab]);

  /*
   * THE KEYBOARD. 1–6 reach the tabs in bar order, D flips the desk — in place
   * on Structure and Analysis, and from any other tab it goes to Analysis —
   * A opens Hermes. Never while typing — the
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
        if (!DESK_TABS.has(tab)) setTab("analysis");
        setDesk(desk === "futures" ? "stocks" : "futures");
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
        const t = TABS[n - 1];
        if (t) {
          e.preventDefault();
          setTab(t.key);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desk, tab, setTab, setDesk]);

  // The browser tab says where you are: "HERMES · Structure", "HERMES · Analysis · Futures".
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
          implied={data.volterm?.books}
          vixMonth={data.volterm?.vix_month}
          link={data.offline || !data.ok ? "offline" : lost ? "lost" : "live"}
          onRefresh={load}
          tab={tab}
          onTab={setTab}
        />

        <AlertStrip items={data.wire ?? NONE} />
        {/* Raises the scanner's alerts on every tab — see the file. */}
        <ScanAlerts />
        {/* The assistant, mounted once; the rail's key and A open it. It is
            told the tab as the collector names it — Analysis as its half. */}
        <AskPanel tab={askTab(tab, desk)} />

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
        ) : tab === "hermes" ? (
          <HermesTab hermes={hermes} desk={desk} />
        ) : tab === "analysis" ? (
          <Analysis desk={desk} onDesk={setDesk} report={report} plan={plan} />
        ) : tab === "scanner" ? (
          <ScannerTab calendar={data.calendar ?? NONE} />
        ) : tab === "structure" ? (
          <StructureBoard data={data} market={market} desk={desk} onDesk={setDesk} />
        ) : (
          <MacroBoard data={data} market={market} />
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

/**
 * The Scanner with its own thirty-second clock for the headline ages — the
 * only time it prints — so its tick re-renders the scanner, not the shell.
 */
function ScannerTab({ calendar }: { calendar: CalendarRow[] }) {
  const now = useNow(30_000);
  return <Scanner now={now} calendar={calendar} />;
}
