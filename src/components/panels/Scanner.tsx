"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Regime, ScannerPayload, ScanRow, Side } from "@/types/scanner";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { ShellAction } from "@/components/shell/SideHeader";
import { useSide } from "@/components/state/UiMode";
import { ScanLog } from "@/components/panels/ScanLog";
import { ScanBreakouts } from "@/components/panels/ScanBreakouts";
import { ScanExtended } from "@/components/panels/ScanExtended";
import { ScanDay23 } from "@/components/panels/ScanDay23";
import { Choice, Chips, Glyph, Menu, Showing, StatCard, TickerFilter, gapOf } from "@/components/panels/ScanWide";
import { ScanTable, sortValue, type ColSet, type SortKey } from "@/components/panels/ScanTable";
import { ChartControls, useChartPrefs } from "@/components/panels/ScanChart";
import { ScanMulti } from "@/components/panels/ScanMulti";
import { WatchlistEditor } from "@/components/panels/ScanWatchlist";
import { liveLine, scoreText } from "@/lib/bias";
import { age, inMin, num, pct } from "@/lib/format";
import { CHART_SLOTS, NO_HELD, TOP_N, isHeldSlots, topScores, type HeldSlots } from "@/lib/multiChart";
import { OUTSIDE_DAY_TITLE, outsideDay } from "@/lib/outsideDay";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { oneOf, persist, usePersisted } from "@/lib/usePersisted";
import { setAskFocus } from "@/lib/ask/open";
import { openSearch, openTicker, useTicker } from "@/lib/ticker";
import { SCAN_VIEWS, type ScanView } from "@/lib/tabs";
import { BAND_LABEL, bandChip, curveOverride } from "@/lib/vix";
import { VixPopover } from "@/components/vol/VixBands";
import { etDay, useNextPrint } from "@/lib/nextPrint";
import type { CalendarRow } from "@/types/terminal";
import { usePinsChanged } from "@/lib/usePinsChanged";

/**
 * The Scanner — the Pine script's scanner table, ranked, with the tape and the
 * news beside it (owner instruction, 2026-10-13: "a section where it ranks
 * specific stocks that are higher probability to trade, similar to the
 * pinescript, and also attach any relevant headlines and earnings and
 * reports").
 *
 * THE STRATEGY IT SERVES. New York break-and-retest: a name breaks its
 * pre-market or previous-day high (low), and the trade is the retest of that
 * level — or of VWAP / the 8 EMA wave when price has run too far from the
 * level for it to come back. So every row answers three questions in order:
 * which levels has it broken (the Pine's PDH / PDL / PMH / PML columns), is it
 * stronger or weaker than the market once each move is scaled by its own ATR
 * (RS), and where is the entry right now (the setup column).
 *
 * THE RANK IS A HEURISTIC, AND SAYS SO. The score is a sum of named parts —
 * structure, relative strength, entry location, volume (before the bell, how
 * far the name is in play: gap, pre-market volume, catalyst), the market — each one
 * listed in the detail pane with the points it earned. It orders the list; it
 * is not a measured probability, and nothing on this page calls it one.
 *
 * VIX IS THE WEATHER, NOT A SIGNAL. It sits in the strip above the table and
 * reaches each score only through the tape's bias (SPY / QQQ against their own
 * levels, and which way VIX is moving with them) — it tells you how hard to
 * press and which side the market is paying, never which name to click.
 *
 * FETCHED ONLY WHILE THIS TAB IS OPEN. The payload is thirty names' levels,
 * signals, headlines and filings, and has no business riding the terminal's
 * twenty-second poll on every other tab.
 *
 * FIVE SECONDS IN THE REGULAR SESSION (owner, 2026-10-14: "as close to real
 * time as possible"). The collector now holds each name's last trade five
 * seconds old, and a twenty-second poll would sit on it for up to four times
 * that. The read is local and ~100 KB, so the faster poll costs the page
 * nothing worth saving; outside the session nothing moves that fast.
 */

const NO_ROWS: CalendarRow[] = [];

/** What a preset may ask about beyond the row itself: the owner's list, and the ten highest scores. */
interface PresetCtx {
  pinned: ReadonlySet<string>;
  top: ReadonlySet<string>;
}

/** Each preset on the Setups table, as a test of one row. */
const PRESET: Record<SideFilter, (r: ScanRow, ctx: PresetCtx) => boolean> = {
  all: () => true,
  top10: (r, c) => c.top.has(r.sym),
  long: (r) => r.score.side === "long",
  short: (r) => r.score.side === "short",
  mag7: (r) => MAG7.has(r.sym),
  pinned: (r, c) => c.pinned.has(r.sym),
  news: (r) => r.catalyst != null,
  gaps: (r) => Math.abs(gapOf(r) ?? 0) >= 2,
  // Through BOTH ranges the same way (lib/outsideDay): the owner's rule. It tested the
  // previous day's range alone until 2026-11-13. That test was kept for an hour as a
  // chip of its own ("Through PDH/PDL") and taken off this table the same day (owner:
  // "are the pill filter bars redundant ... can we clean up redundancy"): every outside
  // day is in it, on a down day it was the Short chip again (22 names, 20 of them
  // short), and the PD range column says it on each row. Breakouts keeps it, where the
  // Dashboard's two counts open it.
  outside: (r) => outsideDay(r.last, r.levels) !== null,
  inside: (r) => {
    const { day_hi: hi, day_lo: lo, pdh, pdl } = r.levels;
    return hi != null && lo != null && pdh != null && pdl != null && hi <= pdh && lo >= pdl;
  },
  day23: (r) => (r.stage ?? 0) >= 2,
};

/*
 * TOP 10 SITS BETWEEN ALL AND PINNED (owner, 2026-11-12: "a top 10 filter in between all
 * and pinned"): the ten highest scores on the list right now, long and short together.
 * It is a set of names, as MAG7 is, so sorting by another column reorders those ten and
 * does not pick ten others.
 */
const PRESET_NAME: ReadonlyArray<{ key: SideFilter; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "top10", label: `Top ${TOP_N}`, title: `The ${TOP_N} highest scores on the list right now, long and short together` },
  { key: "pinned", label: "Pinned", title: "The names you starred" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "mag7", label: "MAG7", title: "The Magnificent Seven: Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta, Tesla" },
  { key: "news", label: "Has news", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened, or is trading pre-market, 2% or more from the previous close" },
  { key: "outside", label: "Outside day", title: OUTSIDE_DAY_TITLE },
  { key: "inside", label: "Inside day", title: "Today's range so far inside the previous day's" },
  { key: "day23", label: "Day 2/3", title: "Day 2 or later of a multi-day move" },
];
const POLL_SEC = 20;
const LIVE_POLL_SEC = 5;

type SideFilter = "all" | "top10" | Side | "mag7" | "pinned" | "news" | "gaps" | "outside" | "inside" | "day23";
type Bench = "SPY" | "QQQ";

/**
 * THE MAGNIFICENT SEVEN, as a filter beside the side filter (owner,
 * 2026-10-14: "where we have all long short toggles, can we also add one for
 * MAG7"). Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta and Tesla — either
 * Alphabet line counts, so the filter still finds it if the list goes back to
 * GOOG. It picks names, not a side: each keeps its own long or short read.
 */
const MAG7: ReadonlySet<string> = new Set(["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA"]);

const CONFIRM_LABEL: Record<NonNullable<Regime["confirm"]>, string> = {
  confirm: "SPY up, VIX down — confirmed",
  divergence: "SPY up, VIX up — divergence",
  risk_off: "SPY down, VIX up — risk-off",
  chop: "Both flat — chop",
};

/**
 * The page's own clock, at the pace its ages need. A headline's "14m" and a
 * signal's "fresh" both move in minutes, so this ticks every thirty seconds
 * rather than taking the shell's second hand — the scanner re-renders when
 * its data or its minutes change, not sixty times a minute.
 */
function useMinuteClock(): number | null {
  const [t, setT] = useState<number | null>(null);
  useEffect(() => {
    setT(Date.now());
    const id = setInterval(() => setT(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  return t;
}

/*
 * THE VIEWS SIT IN A STRIP INSIDE THIS TAB (owner, 2026-11-09), so a view is not a
 * tab. Setups is the deep list;
 * Breakouts, Extended hours, Day 2/3 and Sectors are the wide scan read four ways; the
 * Signal log is what happened. The list is lib/tabs.ts's and the choice the Terminal's.
 */
export function Scanner({
  now: shellNow,
  calendar = NO_ROWS,
  view,
  onView,
  plan = null,
  prices = null,
}: {
  now?: number | null;
  calendar?: CalendarRow[];
  view: ScanView;
  onView: (v: ScanView) => void;
  /**
   * The Game plan view: the written pre-open plan, which was the stocks half of the
   * Analysis tab until 2026-11-11. Built by the Terminal, which holds its state so a
   * plan being written goes on being written while another page is open.
   */
  plan?: React.ReactNode;
  /**
   * SPY, QQQ, IWM and VIX in the masthead, on every view (owner, 2026-11-10: the
   * header's prices moved to "there appropriate places"): what a stock is read
   * against stays in sight while the names are. Built by the Terminal, which holds
   * the quotes.
   */
  prices?: React.ReactNode;
}) {
  const ownNow = useMinuteClock();
  const now = shellNow ?? ownNow;
  const [data, setData] = useState<ScannerPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const ticker = useTicker();
  // The Sidebar interface lists this page's views itself and carries its prices and
  // search in the shell's header: the band is not drawn there (state/UiMode).
  const side = useSide();
  // Shown when no print falls inside the six hours the engine prices in (see RegimeStrip).
  const later = useNextPrint(calendar, now);

  // `?sym=` (an alert's click-through) opens straight onto that name.
  useEffect(() => {
    const s = new URLSearchParams(window.location.search).get("sym");
    if (s) {
      setSel(s.toUpperCase());
      // Written straight through: the Terminal reads the remembered view after this
      // runs, and must find this one rather than put the last view back.
      persist("scan.view", "setups");
      onView("setups");
      openTicker(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [sideF, setSideF] = usePersisted<SideFilter>(
    "scan.side",
    "all",
    // "both" was the Both ranges chip, which is Outside day now, and "through" the
    // previous day's level alone: a browser that had either saved opens on All, once.
    oneOf("all", "top10", "long", "short", "mag7", "pinned", "news", "gaps", "outside", "inside", "day23"),
  );
  // Multicharts: six charts of the list's ten highest scores, a view of its own since
  // 2026-11-13 (lib/tabs.ts). Which names hold which chart, and the one toolbar they
  // all follow, are kept here, above the grid, so they are read from storage before
  // the grid first draws. (It was a switch on the Setups bar, `scan.multi`, for a day;
  // a browser that had it on opens the table, and the charts are one tab along.)
  const [held, setHeld] = usePersisted<HeldSlots>("scan.multi.slots", NO_HELD, isHeldSlots);
  const chartPrefs = useChartPrefs("multi");
  const [bench, setBench] = usePersisted<Bench>("scan.bench", "SPY", oneOf("SPY", "QQQ"));
  const [sort, setSort] = usePersisted<SortKey>(
    "scan.sort",
    "score",
    oneOf("score", "rs", "rvol", "chg", "gap", "ext", "vol", "trend", "ivrv", "em"),
  );
  // A new key, so every browser starts on the clean view once.
  const [cols, setCols] = usePersisted<ColSet>("scan.cols2", "overview", oneOf("overview", "ranked", "options"));
  // Implied against realised is a heading on the Options columns alone since 2026-11-11.
  // A table left sorted by it on the other two would sit in an order no heading shows or
  // can undo, so there it reads in the engine's own order. The saved choice is kept, and
  // is the sort again on Options.
  const sortBy: SortKey = sort === "ivrv" && cols !== "options" ? "score" : sort;
  const [find, setFind] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/scanner", { cache: "no-store" });
      const next = (await r.json()) as ScannerPayload;
      if (mine === seq.current) {
        setData(next);
        setFailed(null);
      }
    } catch (e) {
      if (mine === seq.current) setFailed(e instanceof Error ? e.message : "request failed");
    }
  }, []);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);

  const live = data?.session === "rth";
  useEffect(() => {
    void load();
    const id = setInterval(load, (live ? LIVE_POLL_SEC : POLL_SEC) * 1000);
    return () => clearInterval(id);
  }, [load, live]);

  const pinned = useMemo<ReadonlySet<string>>(() => new Set(data?.pinned ?? []), [data?.pinned]);
  const ctx = useMemo<PresetCtx>(() => ({ pinned, top: new Set(topScores(data?.rows ?? [])) }), [pinned, data?.rows]);

  // The list as its chip and its sort leave it. The table narrows it further by what is
  // typed in the ticker box; the charts are drawn from its first ten as it stands here.
  const ranked = useMemo(() => {
    const kept = (data?.rows ?? []).filter((r) => PRESET[sideF](r, ctx));
    if (sortBy === "score") return kept; // the engine's own order
    // Rows with no figure sink, whichever way the rest sorts. On the short
    // side the strongest is the most NEGATIVE, so the signed columns flip.
    const flip = sideF === "short" && (sortBy === "rs" || sortBy === "chg" || sortBy === "gap" || sortBy === "ext" || sortBy === "trend");
    return [...kept].sort((a, b) => {
      const ka = sortValue(a, sortBy, bench);
      const kb = sortValue(b, sortBy, bench);
      if (ka == null) return kb == null ? 0 : 1;
      if (kb == null) return -1;
      return flip ? ka - kb : kb - ka;
    });
  }, [data, sideF, sortBy, bench, ctx]);

  const rows = useMemo(() => {
    const typed = find.trim().toUpperCase();
    return typed ? ranked.filter((r) => r.sym.includes(typed)) : ranked;
  }, [ranked, find]);

  const charts = view === "multi";
  // The charts' ten: the ten highest scores on the whole list, best first, whatever
  // chip the Setups table was left on.
  const pool = useMemo(() => {
    const all = data?.rows ?? [];
    const by = new Map(all.map((r) => [r.sym, r]));
    return topScores(all).flatMap((s) => by.get(s) ?? []);
  }, [data?.rows]);

  // The selection survives a re-poll by symbol; it falls back to the top row
  // when the name it pointed at is filtered out or dropped from the list.
  const selected = rows.find((r) => r.sym === sel) ?? rows[0] ?? null;
  /*
   * AND THE FALLBACK IS PINNED. Left as "whatever is on top", the pane changed
   * name under the reader whenever the ranking did — every five seconds in
   * the session since the live layer (audit, 2026-10-14). The name it falls
   * back to becomes the selection, so only a click or an arrow moves it.
   */
  const shownSym = selected?.sym ?? null;
  useEffect(() => {
    if (shownSym !== null && shownSym !== sel) setSel(shownSym);
  }, [shownSym, sel]);

  // Hermes reads the name under the cursor: "explain this setup" means it.
  const focusSym = ticker ?? selected?.sym ?? null;
  useEffect(() => {
    setAskFocus(focusSym);
  }, [focusSym]);
  useEffect(() => () => setAskFocus(null), []);

  // A row is a stop in the tab order and Enter picks it. The arrows walking the list
  // went with the other keyboard controls (owner, 2026-11-11).
  const pick = (s: string) => {
    setSel(s);
    openTicker(s);
  };

  const counts = useMemo(() => {
    const c: Partial<Record<SideFilter, number>> = {};
    for (const { key } of PRESET_NAME) {
      const n = (data?.rows ?? []).filter((r) => PRESET[key](r, ctx)).length;
      // "Top 10 10" says the same thing twice; the count shows only when the list is short of ten.
      if (key !== "top10" || n < TOP_N) c[key] = n;
    }
    return c;
  }, [data, ctx]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {side ? (
        // The Sidebar interface: the views are in the sidebar and the prices and the
        // search in its header, so the band is not drawn. What is left of it is the
        // Watchlist button, which goes in the header's slot, with the scan's state
        // (what the band's dot said) on its hover.
        <ShellAction>
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            title={
              data && !data.offline
                ? [
                    "Edit the pinned list",
                    data.trading_day ? `Levels for ${dayName(data.trading_day)}` : null,
                    `${data.rows.filter((r) => r.ok).length} of ${data.watchlist.length} names read, ${age(data.age_min)} ago`,
                    data.status?.error ?? null,
                  ]
                    .filter(Boolean)
                    .join("\n")
                : "Edit the pinned list"
            }
            {...segItem(editing, { className: "border border-ring-2" })}
          >
            Watchlist
          </button>
        </ShellAction>
      ) : (
        <Masthead
          data={data}
          onWatchlist={() => setEditing((v) => !v)}
          editing={editing}
          view={view}
          onView={onView}
          prices={prices}
        />
      )}
      {editing && (
        <WatchlistEditor
          onSaved={() => {
            setEditing(false);
            void load();
          }}
          onCancel={() => setEditing(false)}
        />
      )}

      {data?.offline || failed ? (
        <p className="qt-slab border-b border-ring bg-err/10 px-6 py-2 text-[12px] text-err">
          <strong className="font-semibold">Scanner unavailable.</strong>{" "}
          {data?.offline ? `${data.offline.reason} — expected at ${data.offline.api}.` : failed} Nothing
          below is cached or invented.
        </p>
      ) : null}

      {/* The page sits in one framed card under the band, as in the screenshots. */}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
      {view === "breakouts" ? (
        <ScanBreakouts onTrackChanged={load} />
      ) : view === "extended" ? (
        <ScanExtended onTrackChanged={load} onDay23={() => onView("day23")} />
      ) : view === "day23" ? (
        <ScanDay23 onTrackChanged={load} />
      ) : view === "plan" ? (
        plan
      ) : (
      <div className="flex min-h-0 flex-1 flex-col">
        {/* ---- the ranked list: the whole width, the name opens over it --- */}
        <section aria-label={charts ? "Multicharts" : view === "log" ? "Signal log" : "Ranked setups"} className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* The row sums up the table, so it is the Setups view's alone. Over the charts
              its height would be theirs (on a 1920 screen it is a sixth of what two rows of
              them have). */}
          {view === "setups" && data && !data.offline && <SetupStats data={data} later={later} now={now} />}
          {/*
            * ONE BAR UNDER THE BAND, AND WHAT IT HOLDS IS THE VIEW'S. Setups: the chips and
            * the table's tools. The Signal log: a line of words. Multicharts: the charts'
            * one toolbar, the timeframes and the Indicators menu all six follow, at the
            * left where a view's choices sit, with what the six are at the right where a
            * view's status sits.
            *
            * MULTICHARTS LEFT THIS BAR ON 2026-11-13 (owner: "the multicharts should be up
            * the top next to gameplan and on sidebar it should be under neath gameplan").
            * For a day it was a button after the chips (2026-11-12: "a option next to the
            * filter bar called multicharts"), then one of the bar's choices, the chips or
            * the charts and never both lit. As a view it needs neither rule: the chips are
            * not on its page.
            *
            * Exactly one of the three is rendered, never one rendered and hidden: under
            * Luminous the band over the page joins the FIRST card under it, and a hidden
            * bar was that card, so the log's own bar kept its rounded top beneath a
            * squared band.
            */}
          {view === "log" ? (
            <p className="qt-bar shrink-0 border-b border-ring px-4 py-2.5 text-[11.5px] text-ink-3">Every signal, and what it did afterwards</p>
          ) : charts ? (
            <div className="qt-bar flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-ring px-4 py-2">
              {/* One toolbar for the six: a chart in the grid has no toolbar of its own. */}
              <ChartControls prefs={chartPrefs} hasBands={chartPrefs.tf !== "D"} shared />
              <p className="fig ml-auto shrink-0 text-right text-[10.5px] leading-[1.25] text-ink-3" title="A chart keeps its name until you change it from its Change menu, or the name leaves the ten">
                <span className="text-ink-2">{Math.min(CHART_SLOTS, pool.length)}</span> charts
                <br />
                the {TOP_N} highest scores
              </p>
            </div>
          ) : (
          <div className="qt-bar flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-4 py-2">
            <Chips items={PRESET_NAME} on={sideF} set={setSideF} counts={counts} />
            <div className="ml-auto flex items-center gap-2">
              <TickerFilter value={find} onChange={setFind} />
              {/*
                * HOW TO TRADE THIS TAPE IS A BUTTON AMONG THE BAR'S BUTTONS (owner,
                * 2026-11-11: "i dont like the 'How to trade this' text just being
                * randomly there, it sticks out"). It was a line of text at the end of
                * the stat tiles that opened the desk's notes as loose lines under
                * them: neither the words nor what they opened sat in anything. The
                * notes are the regime's own (the VIX band, its month, SPY's implied
                * move, the tape), unchanged.
                */}
              {data && !data.offline && data.regime.notes.length > 0 && (
                <Menu label="How to trade this" width={460}>
                  <ul className="space-y-2 text-[12px] leading-[1.45] text-ink-2">
                    {data.regime.notes.map((n) => (
                      <li key={n} className="flex gap-2">
                        <span aria-hidden className="mt-[7px] h-[4px] w-[4px] shrink-0 rounded-[1px] bg-ink-4" />
                        {n}
                      </li>
                    ))}
                  </ul>
                </Menu>
              )}
              <Menu label={<>Columns ·<span className="fig">{COL_WORD[cols]}</span></>} width={260}>
                <Choice label="Columns" options={COL_CHOICES} value={cols} set={setCols} />
                <Choice label="Relative strength against" options={BENCH_CHOICES} value={bench} set={setBench} />
                <p className="text-[11px] leading-[1.4] text-ink-3">Overview is what matters, Levels every column the Pine&apos;s scanner has, Options the chain. The score always uses SPY.</p>
              </Menu>
              <Showing shown={rows.length} total={data?.watchlist.length ?? null} word="on the list" />
            </div>
          </div>
          )}

          {charts ? (
            data && !data.offline && data.rows.length > 0 ? (
              <ScanMulti
                pool={pool}
                // Another day is another list: its six start from its top.
                listKey={data.trading_day}
                what={`the top ${TOP_N}`}
                held={held}
                onHeld={setHeld}
                prefs={chartPrefs}
                session={data.session}
                open={ticker}
              />
            ) : (
              // The charts' page never falls back to the table: it waits, or says why not.
              <div className="qt-sheet min-h-0 flex-1 overflow-auto">
                {!data ? (
                  <TableSkeleton />
                ) : (
                  <p className="px-6 py-10 text-center text-[12px] text-ink-3">
                    {data.offline
                      ? "Nothing to chart until the collector answers."
                      : "No names scanned yet — the collector fetches the watchlist a third at a time, so the first full pass takes about a minute and a half."}
                  </p>
                )}
              </div>
            )
          ) : (
          <div className="qt-sheet min-h-0 flex-1 overflow-auto">
            {view === "log" ? (
              <ScanLog onPick={(s) => {
                setSel(s);
                onView("setups");
                openTicker(s);
              }} />
            ) : !data ? (
              <TableSkeleton />
            ) : rows.length === 0 ? (
              <p className="px-6 py-10 text-center text-[12px] text-ink-3">
                {data.offline
                  ? "Nothing to rank until the collector answers."
                  : data.rows.length === 0
                  ? "No names scanned yet — the collector fetches the watchlist a third at a time, so the first full pass takes about a minute and a half."
                  : "Nothing on this side right now."}
              </p>
            ) : (
              <ScanTable
                rows={rows}
                cols={cols}
                bench={bench}
                session={data.session}
                sort={sortBy}
                onSort={setSort}
                now={now}
                selected={ticker ?? selected?.sym ?? null}
                onPick={pick}
                pinned={pinned}
                onPinned={load}
              />
            )}
          </div>
          )}
        </section>
      </div>
      )}
      </div>
    </div>
  );
}

const COL_WORD: Record<ColSet, string> = { overview: "Overview", ranked: "Levels", options: "Options" };
const COL_CHOICES: ReadonlyArray<{ value: ColSet; label: string }> = [
  { value: "overview", label: "Overview" },
  { value: "ranked", label: "Levels" },
  { value: "options", label: "Options" },
];
const BENCH_CHOICES: ReadonlyArray<{ value: Bench; label: string }> = [
  { value: "SPY", label: "SPY" },
  { value: "QQQ", label: "QQQ" },
];

/**
 * The first load: the helm in the middle of the card the table is about to fill, where
 * every other page's wait puts it (ui/HelmLoader PageLoader). The sheet is the card here.
 */
function TableSkeleton() {
  return <HelmLoader label="Loading the scanner" size={56} className="h-full min-h-[240px]" />;
}

/* -------------------------------------------------------------------------- */
/* Masthead                                                                    */
/* -------------------------------------------------------------------------- */

function Masthead({
  data,
  onWatchlist,
  editing,
  view,
  onView,
  prices,
}: {
  data: ScannerPayload | null;
  onWatchlist: () => void;
  editing: boolean;
  view: ScanView;
  onView: (v: ScanView) => void;
  prices: React.ReactNode;
}) {
  const ok = data?.rows.filter((r) => r.ok).length ?? 0;
  const total = data?.watchlist.length ?? 0;
  const fromPool = data?.pool?.promoted.length ?? 0;
  return (
    <div className="qt-mast flex min-h-[44px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 qt:px-4">
      <div className="contents">
        {/* `seg-tabs`: a page's views are words with a rule under the open one, not the
            lit pills the filter chips under them are (globals.css, "a page's views are
            tabs, not pills"). */}
        <span className="seg seg-tabs shrink-0" role="tablist" aria-label="Stocks views">
          {SCAN_VIEWS.map((v) => (
            <button key={v.key} type="button" role="tab" aria-selected={view === v.key} title={v.title} onClick={() => onView(v.key)} {...segItem(view === v.key)}>
              {v.label}
            </button>
          ))}
        </span>
      </div>
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
        {data && !data.offline && (
          <span
            className="fig text-[11px] whitespace-nowrap text-ink-3"
            title={[
              data.trading_day ? `Levels for ${dayName(data.trading_day)}` : null,
              `${ok} of ${total} names read${fromPool > 0 ? `, ${fromPool} from the pool` : ""}, ${age(data.age_min)} ago`,
              data.status?.error ?? data.status?.notes.join(" · ") ?? null,
            ]
              .filter(Boolean)
              .join("\n")}
          >
            <span
              aria-hidden
              className={cn(
                "mr-1.5 inline-block h-[6px] w-[6px] rounded-full align-middle",
                data.status?.ok ? "bg-call" : "bg-err",
              )}
            />
            {SESSION_WORD[data.session]}
          </span>
        )}
        <button type="button" onClick={onWatchlist} {...segItem(editing, { className: "border border-ring-2" })}>
          Watchlist
        </button>
      </div>
    </div>
  );
}

/** The session in a word or two, beside the status dot. */
const SESSION_WORD: Record<ScannerPayload["session"], string> = {
  pre: "Pre-market",
  rth: "Regular session",
  post: "After hours",
  closed: "Market closed",
};

/**
 * THE PAGE'S HEAD, AS THE SCREENSHOTS HAVE IT: how many on each side, the most
 * relative volume, the biggest mover. The tape and the next print sit in the same
 * row, so the weather line under it could go: the VIX figure still opens its bands
 * and the desk's lines on how to trade this band are one button away, in the bar
 * over the table with the page's other buttons.
 *
 * NO SESSION-TYPE TILE (owner, 2026-11-11: "why do we show an nq session lean in the
 * scanner when it's for sotcks/ optios"). For a day the row carried NQ's trend-or-range
 * lean beside the tape. It is a read of the future's night in the future's own ATR,
 * with a record kept on futures sessions and none against these stocks' signals, so on
 * this page it was another desk's figure. It lives on the Futures tab.
 */
function SetupStats({ data, later, now }: { data: ScannerPayload; later: CalendarRow | null; now: number | null }) {
  const rows = data.rows.filter((r) => r.ok);
  const longs = rows.filter((r) => r.score.side === "long");
  const shorts = rows.filter((r) => r.score.side === "short");
  const topRvol = rows.reduce<ScanRow | null>((m, r) => ((r.rvol ?? 0) > (m?.rvol ?? 0) ? r : m), null);
  const topPm = rows.reduce<ScanRow | null>((m, r) => ((r.premkt?.pct_adv ?? 0) > (m?.premkt?.pct_adv ?? 0) ? r : m), null);
  const pre = data.session === "pre";
  const moveOf = (r: ScanRow) => (pre ? (r.ext_pct ?? r.chg_pct) : r.chg_pct) ?? 0;
  const topMove = rows.reduce<ScanRow | null>((m, r) => (m === null || Math.abs(moveOf(r)) > Math.abs(moveOf(m)) ? r : m), null);
  const where = (r: ScanRow) => {
    const { pdh, pdl } = r.levels;
    return r.last != null && pdh != null && r.last > pdh ? "Above PDH" : r.last != null && pdl != null && r.last < pdl ? "Below PDL" : "Inside the day";
  };
  const regime = data.regime;
  // No release with the calendar not loading is a gap, and the card says so.
  const calendarDown = regime.calendar_ok === false && !regime.event && !later;
  const v = regime.vix;
  const c = regime.conviction;
  const bias = c ? c.bias : regime.bias;
  const biasHue = bias === "long" ? "text-call-fig" : bias === "short" ? "text-put-fig" : "text-ink-2";
  const biasTip = c
    ? `${liveLine(c)} · plans capped at ${c.max_conviction}\n` +
      c.votes.map((x) => `${x.live === false ? "·" : x.vote === "long" ? "▲" : x.vote === "short" ? "▼" : "–"} ${x.label}: ${x.value} — ${x.note}`).join("\n")
    : (regime.confirm ? CONFIRM_LABEL[regime.confirm] : "Which side the tape is paying");
  const tape = (["SPY", "QQQ", "IWM"] as const)
    .map((k) => {
      const t = regime.tape[k];
      return `${k} ${t ? trendGlyph(t.trend) : "·"}`;
    })
    .join("  ");
  return (
    <div className="qt-stats shrink-0 border-b border-ring">
      <div className="qt-stats-row flex flex-wrap">
        <StatCard glyph="up" tint="up" value={longs.length} hue="text-call-fig" label="Bullish signals" sub={`${longs.filter((r) => r.broken.pdh).length} breaking PDH`} />
        <StatCard glyph="down" tint="down" value={shorts.length} hue="text-put-fig" label="Bearish signals" sub={`${shorts.filter((r) => r.broken.pdl).length} breaking PDL`} />
        {topRvol?.rvol != null || topPm?.premkt?.pct_adv == null ? (
          <StatCard
            glyph="pulse"
            tint="news"
            value={topRvol?.rvol != null ? `${topRvol.rvol.toFixed(1)}×` : "—"}
            hue="text-desk-markets"
            label="Top RVol"
            sub={topRvol ? `${topRvol.sym}${topRvol.name ? ` · ${topRvol.name}` : ""}` : undefined}
          />
        ) : (
          // Before the bell there is no relative volume: the most pre-market volume
          // against an average day, which is what the pre-open rank reads.
          <StatCard
            glyph="pulse"
            tint="news"
            value={`${topPm.premkt.pct_adv.toFixed(1)}%`}
            hue="text-desk-markets"
            label="Top pre-mkt vol"
            title="The most pre-market volume as a share of an average day. Relative volume by time of day starts at the open."
            sub={`${topPm.sym} · of an average day`}
          />
        )}
        <StatCard
          glyph="star"
          tint="move"
          value={topMove ? pct(moveOf(topMove)) : "—"}
          hue="text-desk-policy"
          label="Top mover"
          sub={topMove ? `${topMove.sym} · ${where(topMove)}` : undefined}
        />
        <StatCard
          glyph="tape"
          value={
            <>
              {bias === "long" ? "▲ Long" : bias === "short" ? "▼ Short" : "No lean"}
              {c &&
                (c.thin ? (
                  // Under half the weight can vote: the count, not a score that reads as certainty.
                  <span className="ml-1.5 text-[12px] text-ink-3">
                    {c.live ?? 0} of {c.total} reads
                  </span>
                ) : (
                  <span className="ml-1.5">{c.score != null ? scoreText(c.score) : `${c.agree}/${c.total}`}</span>
                ))}
            </>
          }
          hue={biasHue}
          label={c ? `Tape · ${c.grade}` : "Tape"}
          title={biasTip}
          sub={
            <VixPopover facts={{ ...v, band: regime.band, sub: regime.sub ?? null, month: v.month ?? null }} className="-mx-1 px-1">
              <span className="fig text-[11px]" title={`The weather, not a signal. Click for the bands.\n${v.shape !== "unknown" ? `The curve is in ${v.shape}. ` : ""}${tape}: SPY, QQQ and IWM against their own PDH / PMH and PDL / PML.`}>
                VIX {num(v.last, 2)}
                {regime.band ? ` ${bandChip(regime.band, regime.sub ?? null, curveOverride(regime.vix?.last, regime.band)) ?? BAND_LABEL[regime.band]}` : ""}
                {regime.spy_em_pct != null ? ` · SPY ±${regime.spy_em_pct.toFixed(2)}%` : ""}
              </span>
            </VixPopover>
          }
        />
        <StatCard
          glyph="clock"
          value={
            regime.event ? (
              regime.event.in_min < 0 ? "just printed" : `in ${inMin(regime.event.in_min)}`
            ) : later && later.ts !== null && now !== null ? (
              `in ${inMin((later.ts - now / 1000) / 60)}`
            ) : (
              "—"
            )
          }
          hue={regime.event && regime.event.in_min <= 30 ? "text-flip-fig" : "text-ink"}
          label="Next print"
          title={
            calendarDown
              ? "The economic calendar is not loading, so the next release is unknown — not the same as none scheduled. Check the day's prints before taking a level."
              : "The next US release scored 4+ on the calendar. Inside six hours the engine prices it in; inside thirty minutes it costs every score ten points."
          }
          sub={
            regime.event ? (
              regime.event.title
            ) : later && now !== null ? (
              `${etDay(later.ts ?? 0, now)}${later.event}`
            ) : calendarDown ? (
              <span className="text-warn">Calendar feed down</span>
            ) : (
              "None scheduled"
            )
          }
        />
      </div>
    </div>
  );
}

/** "2026-10-13" → "Tue Oct 13". */
function dayName(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

const trendGlyph = (t: -1 | 0 | 1) => (t === 1 ? "▲" : t === -1 ? "▼" : "–");
