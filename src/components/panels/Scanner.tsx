"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Regime, ScannerPayload, ScanRow, Side } from "@/types/scanner";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { useSide } from "@/components/state/UiMode";
import { ScanBreakouts } from "@/components/panels/ScanBreakouts";
import { ScanExtended } from "@/components/panels/ScanExtended";
import { ScanDay23 } from "@/components/panels/ScanDay23";
import { BiasStat, Choice, Chips, Glyph, Menu, STAT_BOX, Showing, StatCard, capWord, gapOf, isNum, isStr } from "@/components/panels/ScanWide";
import { ScanTable, sortValue, type ColSet, type SortKey } from "@/components/panels/ScanTable";
import { ChartControls, useChartPrefs } from "@/components/panels/ScanChart";
import { ScanMulti } from "@/components/panels/ScanMulti";
import { liveLine } from "@/lib/bias";
import { wholeScore } from "@/lib/biasScale";
import { inMin, pct } from "@/lib/format";
import { CHART_SLOTS, NO_HELD, TOP_N, isHeldSlots, topScores, type HeldSlots } from "@/lib/multiChart";
import { OUTSIDE_DAY_TITLE, outsideDay } from "@/lib/outsideDay";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { oneOf, persist, usePersisted } from "@/lib/usePersisted";
import { setAskFocus } from "@/lib/ask/open";
import { BENCHMARKS, openSearch, openTicker, useTicker } from "@/lib/ticker";
import { stripViews, type ScanView } from "@/lib/tabs";
import { useLegacyViews } from "@/lib/legacyViews";
import type { PhaseKey, TodayPayload, TodayPhase } from "@/types/today";
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
 * structure, relative strength, whether there is an entry, volume (before the bell, how
 * far the name is in play: gap, pre-market volume, catalyst), the market — each one
 * listed in the detail pane with the points it earned. It orders the list; it
 * is not a measured probability, and nothing on this page calls it one.
 *
 * WHAT THE LIST IS FOR IS STOCKS THAT TREND (owner, 2026-11-14), and the engine is
 * judged on +2R reached and R held, not +1R. Since that day a story earns its grade
 * whichever side the setup is on (news is fuel, the price picks the side; a headline
 * that reads against the side is a flag here, not minus points) and RS is 10 of the
 * score, not 20. Two things ride on a row as context and earn nothing: the previous
 * session's major story (a flag) and a model's read of how big today's story is (a
 * "Big" chip beside the story and a line in the slide-out's News card).
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
  // The three index funds (owner, 2026-11-14: "can we add a filter in the pill for
  // Index"). A set of names, as MAG7 is: SPY, QQQ and IWM are always on the list
  // (lib/ticker BENCHMARKS), ranked among forty stocks, and this is the three alone
  // with their levels and scores, which the Index view showed until it went.
  index: (r) => BENCHMARKS.has(r.sym),
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
  // An insider's open-market buy, or a sale not under a 10b5-1 plan, this month
  // (server sources/insiders.py): context, like news (owner, 2026-11-13).
  insiders: (r) => (r.insiders?.length ?? 0) > 0,
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
  { key: "pinned", label: "Favourites", title: "The names you starred" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "mag7", label: "MAG7", title: "The Magnificent Seven: Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta, Tesla" },
  { key: "index", label: "Index", title: "The index funds: SPY (S&P 500), QQQ (Nasdaq 100) and IWM (Russell 2000)" },
  { key: "news", label: "Has News", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened, or is trading pre-market, 2% or more from the previous close" },
  { key: "outside", label: "Outside Day", title: OUTSIDE_DAY_TITLE },
  { key: "inside", label: "Inside Day", title: "Today's range so far inside the previous day's" },
  { key: "day23", label: "Day 2/3", title: "Day 2 or later of a multi-day move" },
  {
    key: "insiders",
    label: "Insiders",
    title: "An insider bought on the open market ($100k+), or sold $1M+ outside a pre-planned 10b5-1 plan, in the last 30 days (SEC Form 4s, for the names on the Scanner and on the list)",
  },
];
const POLL_SEC = 20;
const LIVE_POLL_SEC = 5;

type SideFilter = "all" | "top10" | Side | "mag7" | "index" | "pinned" | "news" | "gaps" | "outside" | "inside" | "day23" | "insiders";
type Bench = "SPY" | "QQQ";

/**
 * THE MAGNIFICENT SEVEN, as a filter beside the side filter (owner,
 * 2026-10-14: "where we have all long short toggles, can we also add one for
 * MAG7"). Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta and Tesla — either
 * Alphabet line counts, so the filter still finds it if the list goes back to
 * GOOG. It picks names, not a side: each keeps its own long or short read.
 */
const MAG7: ReadonlySet<string> = new Set(["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA"]);

// The VIX against SPY as weather, never a side (server scanscore, the evening of
// 2026-11-19): "confirmed" and "risk-off" read as a call on which way.
const CONFIRM_LABEL: Record<NonNullable<Regime["confirm"]>, string> = {
  confirm: "SPY up, VIX down — no hedging under it",
  divergence: "SPY up, VIX up — a hedged rally",
  risk_off: "SPY down, VIX up — protection bid",
  divergence_down: "SPY down, VIX down — nobody hedging",
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
  prices = null,
  report = null,
}: {
  now?: number | null;
  calendar?: CalendarRow[];
  view: ScanView;
  onView: (v: ScanView) => void;
  /**
   * The Market Report view after Charts (2026-11-16): SPY, QQQ and IWM for New York,
   * built by the Terminal, which holds the report's state so a report being written
   * survives a change of page.
   */
  report?: React.ReactNode;
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
      persist("scan.view", "today");
      onView("today");
      openTicker(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [sideF, setSideF] = usePersisted<SideFilter>(
    "scan.side",
    "all",
    // "both" was the Both ranges chip, which is Outside day now, and "through" the
    // previous day's level alone: a browser that had either saved opens on All, once.
    oneOf("all", "top10", "long", "short", "mag7", "index", "pinned", "news", "gaps", "outside", "inside", "day23", "insiders"),
  );
  // Multicharts: six charts of the list's ten highest scores, a view of its own since
  // 2026-11-13 (lib/tabs.ts). Which names hold which chart, and the one toolbar they
  // all follow, are kept here, above the grid, so they are read from storage before
  // the grid first draws. (It was a switch on the Setups bar, `scan.multi`, for a day;
  // a browser that had it on opens the table, and the charts are one tab along.)
  // A new key on 2026-11-15, when the ten became the Scanner list's: what a browser held
  // was six of the engine's tracked names, filled in by the page and not by the reader.
  const [held, setHeld] = usePersisted<HeldSlots>("scan.multi.slots2", NO_HELD, isHeldSlots);
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
  /*
   * TODAY IS THIS TABLE, IN TODAY'S ORDER (owner, 2026-11-13: "i prefer the general style
   * of what it was before in terms of color etc"). The list is ranked for the hour it is
   * (server today.py) and each of its rows comes as the Setups table's own (today.scan_row):
   * the engine's row for a tracked name, one built from the wide read for the rest, the
   * score the phase's (in play before 10:00, the setup score after). So the chips, the
   * columns, the colours and the slide-out are the ones this table has always had.
   */
  const [today, setToday] = useState<TodayPayload | null>(null);
  // The list was asked for and did not come: the charts then fall back to the engine's
  // rows, and until it is known which, they wait (see `pool`).
  const [todayMiss, setTodayMiss] = useState(false);
  const todaySeq = useRef(0);
  const loadToday = useCallback(async () => {
    const mine = ++todaySeq.current;
    try {
      const r = await fetch("/api/scanner/today", { cache: "no-store" });
      const next = (await r.json()) as TodayPayload & { offline?: unknown };
      if (mine !== todaySeq.current) return;
      if (!next.offline && next.phase) {
        setToday(next);
        setTodayMiss(false);
      } else {
        setTodayMiss(true);
      }
    } catch {
      /* the engine's payload still carries the page; the next read tries again */
      if (mine === todaySeq.current) setTodayMiss(true);
    }
  }, []);
  const isToday = view === "today";
  const charts = view === "multi";
  // The Scanner's list is the table's rows and the charts' ten: both views read it.
  const wantToday = isToday || charts;
  const refresh = useCallback(() => {
    void load();
    if (wantToday) void loadToday();
  }, [load, loadToday, wantToday]);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(refresh);

  const live = data?.session === "rth";
  useEffect(() => {
    void load();
    const id = setInterval(load, (live ? LIVE_POLL_SEC : POLL_SEC) * 1000);
    return () => clearInterval(id);
  }, [load, live]);
  const todayPhase = today?.phase?.key ?? "overnight";
  useEffect(() => {
    if (!wantToday) return;
    void loadToday();
    const id = setInterval(loadToday, TODAY_POLL_SEC[todayPhase] * 1000);
    return () => clearInterval(id);
  }, [wantToday, loadToday, todayPhase]);

  /*
   * TODAY'S FILTERS, BESIDE COLUMNS (owner, 2026-11-13: "i cant see filters anymore? next
   * to columns and how to trade this"). The Filters menu was on Breakouts, Extended hours
   * and Day 2/3, which Today replaced; it is back here, the same menu, over Today's rows:
   * market cap, relative volume and sector, all off by default. Relative volume is read
   * from the open, as Breakouts read it: before the bell no name has one.
   */
  const [fCap, setFCap] = usePersisted<number>("today.cap", 0, isNum);
  const [fRvol, setFRvol] = usePersisted<number>("today.rvol", 0, isNum);
  const [fSector, setFSector] = usePersisted<string>("today.sector", "", isStr);
  const rvolOn = data?.session === "rth" || data?.session === "post";

  // The Scanner's list in its own order, as its Filters leave it.
  const todayRows = useMemo<ScanRow[]>(
    () =>
      (today?.rows ?? [])
        .map((t) => t.row)
        .filter(
          (r) =>
            (!fCap || (r.market_cap ?? 0) >= fCap) &&
            (!fRvol || !rvolOn || (r.rvol ?? 0) >= fRvol) &&
            (!fSector || r.sector === fSector),
        ),
    [today?.rows, fCap, fRvol, fSector, rvolOn],
  );
  // The rows the table and its chips read: Today's in its order, else the engine's.
  const listRows = useMemo<ScanRow[]>(() => (isToday ? todayRows : (data?.rows ?? [])), [isToday, todayRows, data?.rows]);
  const filterWord =
    [fCap ? capWord(fCap) : null, fRvol ? `RVol ${fRvol}×+` : null, fSector || null].filter(Boolean).join(" · ") || "all";

  const pinned = useMemo<ReadonlySet<string>>(() => new Set(data?.pinned ?? []), [data?.pinned]);
  const ctx = useMemo<PresetCtx>(
    () => ({ pinned, top: new Set(isToday ? listRows.slice(0, TOP_N).map((r) => r.sym) : topScores(data?.rows ?? [])) }),
    [pinned, isToday, listRows, data?.rows],
  );

  // The list as its chip and its sort leave it. The table narrows it further by what is
  // typed in the ticker box; the charts are drawn from its first ten as it stands here.
  const ranked = useMemo(() => {
    const kept = listRows.filter((r) => PRESET[sideF](r, ctx));
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
  }, [listRows, sideF, sortBy, bench, ctx]);

  // ONE SEARCH (owner, 2026-11-13: "we have two ticker / company search bars? which one
  // should we get rid off"). The bar's ticker box narrowed this list by what was typed; the
  // masthead's search (Ctrl K) finds any ticker and opens it, and the chips and Filters
  // narrow the list. The box went; the list is the chips' and the filters'.
  const rows = ranked;

  /*
   * THE CHARTS' TEN ARE THE SCANNER'S TOP TEN (owner, 2026-11-15: "the charts wsection is
   * bugging it's not actually showing from the top 10 picks, its showing from mag7"). They
   * were the ten highest scores among the ENGINE's rows, which was the whole list until
   * 2026-11-13. Since then the Scanner view is Today's list, ranked for the hour: the
   * evening's movers, what is in play into the open, then the session's setups. The
   * engine tracks only the benchmarks and the MAG 7 until the pool promotes names at
   * 06:00, so overnight and at a weekend the charts were the MAG 7 while the Scanner led
   * with something else. Now they are the list's first ten as its Filters leave it, the
   * same ten its Top 10 chip keeps, whatever chip the table was left on. A name the
   * engine does not track draws like any other: its chart is read on the request.
   *
   * null while the list is still being read, so six charts of the wrong names are not
   * drawn and then held (lib/multiChart: a chart keeps its name). If the list cannot be
   * read at all, the engine's ten as before.
   */
  const pool = useMemo<ScanRow[] | null>(() => {
    if (today) return todayRows.slice(0, TOP_N);
    if (!todayMiss) return null;
    const all = data?.rows ?? [];
    const by = new Map(all.map((r) => [r.sym, r]));
    return topScores(all).flatMap((s) => by.get(s) ?? []);
  }, [today, todayRows, todayMiss, data?.rows]);

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
      const n = listRows.filter((r) => PRESET[key](r, ctx)).length;
      // "Top 10 10" says the same thing twice; the count shows only when the list is short of ten.
      if (key !== "top10" || n < TOP_N) c[key] = n;
    }
    return c;
  }, [listRows, ctx]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* NO WATCHLIST BUTTON AND NO SESSION WORD (owner, 2026-11-13: "remove the
          pre-market next to watch list since we already show what session and then also
          remove watchlist"). The header says the session; a favourite is its row's star.
          The Sidebar interface draws no band, and had the button in its header: gone too. */}
      {!side && <Masthead data={data} view={view} onView={onView} prices={prices} />}

      {data?.offline || failed ? (
        <p className="qt-slab border-b border-ring bg-err/10 px-6 py-2 text-[12px] text-err">
          <strong className="font-semibold">Scanner unavailable.</strong>{" "}
          {data?.offline ? `${data.offline.reason} — expected at ${data.offline.api}.` : failed} Nothing
          below is cached or invented.
        </p>
      ) : null}

      {/* The page sits in one framed card under the band, as in the screenshots. */}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
      {view === "report" ? (
        report
      ) : view === "breakouts" ? (
        <ScanBreakouts onTrackChanged={load} />
      ) : view === "extended" ? (
        <ScanExtended onTrackChanged={load} onDay23={() => onView("day23")} />
      ) : view === "day23" ? (
        <ScanDay23 onTrackChanged={load} />
      ) : (
      <div className="flex min-h-0 flex-1 flex-col">
        {/* ---- the ranked list: the whole width, the name opens over it --- */}
        <section aria-label={charts ? "Multicharts" : "Ranked setups"} className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* The row sums up the table, so it is the Setups view's alone. Over the charts
              its height would be theirs (on a 1920 screen it is a sixth of what two rows of
              them have). */}
          {(view === "setups" || isToday) && data && !data.offline && (
            <SetupStats data={isToday ? { ...data, rows: listRows } : data} later={later} now={now} phase={isToday ? (today?.phase ?? null) : null} />
          )}
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
          {charts ? (
            <div className="qt-bar flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-ring px-4 py-2">
              {/* One toolbar for the six: a chart in the grid has no toolbar of its own. */}
              <ChartControls prefs={chartPrefs} hasBands={chartPrefs.tf !== "D"} shared />
              <p
                className="fig ml-auto shrink-0 text-right text-[10.5px] leading-[1.25] text-ink-3"
                title={`The first ${TOP_N} names on the Scanner's list${filterWord === "all" ? "" : `, as its Filters leave it (${filterWord})`}. A chart keeps its name until you change it from its Change menu, or the name leaves the ten`}
              >
                <span className="text-ink-2">{Math.min(CHART_SLOTS, pool?.length ?? 0)}</span> charts
                <br />
                the Scanner&apos;s top {TOP_N}
                {filterWord === "all" ? "" : ` · ${filterWord}`}
              </p>
            </div>
          ) : (
          <div className="qt-bar flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-4 py-2">
            <Chips items={PRESET_NAME} on={sideF} set={setSideF} counts={counts} />
            <div className="ml-auto flex items-center gap-2">
              {/*
                * NO "HOW TO TRADE THIS" (owner, 2026-11-13: "can we remove the 'how to
                * trade this' it's just random i dont even know what purpose it serves").
                * It opened the regime's stock lines on the VIX band and the tape; the VIX
                * card's own read and the Market overview say the same where they are read.
                */}
              {isToday && (
                <Menu label={<>Filters · <span className="fig">{filterWord}</span></>}>
                  <Choice label="Market cap" options={TODAY_CAPS} value={fCap} set={setFCap} />
                  <Choice label="Relative volume (from the open)" options={TODAY_RVOLS} value={fRvol} set={setFRvol} />
                  <Choice label="Sector" options={TODAY_SECTORS} value={fSector} set={setFSector} />
                  <button
                    type="button"
                    onClick={() => {
                      setFCap(0);
                      setFRvol(0);
                      setFSector("");
                    }}
                    {...segItem(false, { className: "self-start border border-ring-2" })}
                  >
                    Reset
                  </button>
                </Menu>
              )}
              <Menu label={<>Columns ·<span className="fig">{COL_WORD[cols]}</span></>} width={260}>
                <Choice label="Columns" options={COL_CHOICES} value={cols} set={setCols} />
                <Choice label="Relative strength against" options={BENCH_CHOICES} value={bench} set={setBench} />
                <p className="text-[11px] leading-[1.4] text-ink-3">Overview is what matters, Levels every column the Pine&apos;s scanner has, Options the chain. The score always uses SPY.</p>
              </Menu>
              <Showing shown={rows.length} total={isToday ? (today?.rows.length ?? null) : (data?.watchlist.length ?? null)} word="on the list" />
            </div>
          </div>
          )}

          {charts ? (
            data && !data.offline && data.rows.length > 0 && pool ? (
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
                {!data || (!data.offline && data.rows.length > 0 && !pool) ? (
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
            {!data || (isToday && !today && !data.offline) ? (
              <TableSkeleton />
            ) : rows.length === 0 ? (
              <p className="px-6 py-10 text-center text-[12px] text-ink-3">
                {data.offline
                  ? "Nothing to rank until the collector answers."
                  : isToday
                  ? (today?.note ?? (listRows.length ? "Nothing on this side right now." : TODAY_EMPTY[todayPhase]))
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
                onPinned={refresh}
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

/** Today's Filters menu: the choices Breakouts' had. */
const TODAY_CAPS = [0, 3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const TODAY_RVOLS = [0, 1, 1.5, 2, 5].map((value) => ({ value, label: value ? `${value}×+` : "Any" }));
const TODAY_SECTORS = ["", "XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU"].map((value) => ({
  value,
  label: value || "All",
}));

/** How often Today is read again: a phase that moves by the second, read often. */
const TODAY_POLL_SEC: Record<PhaseKey, number> = { session: 10, pre: 15, after: 30, overnight: 60 };
const TODAY_EMPTY: Record<PhaseKey, string> = {
  after: "Nothing has moved enough since the close to make the list yet.",
  overnight: "Nothing moved enough this evening to make the list.",
  pre: "Nothing is in play yet this morning. Names arrive as the pre-market trades.",
  session: "The engine has read no names yet.",
};

/** "in 48m", "in 5h 34m", "in 2d": when the next phase begins. */
function untilWord(min: number): string {
  if (min < 1) return "now";
  if (min < 90) return `in ${Math.round(min)}m`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h < 24 ? `in ${h}h${m ? ` ${m}m` : ""}` : `in ${Math.round(h / 24)}d`;
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
  view,
  onView,
  prices,
}: {
  data: ScannerPayload | null;
  view: ScanView;
  onView: (v: ScanView) => void;
  prices: React.ReactNode;
}) {
  const legacy = useLegacyViews();
  return (
    <div className="qt-mast flex min-h-[44px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 qt:px-4">
      <div className="contents">
        {/* `seg-tabs`: a page's views are words with a rule under the open one, not the
            lit pills the filter chips under them are (globals.css, "a page's views are
            tabs, not pills"). */}
        <span className="seg seg-tabs shrink-0" role="tablist" aria-label="Stocks views">
          {stripViews(legacy).map((v) => (
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
            className="hit flex h-[28px] w-[clamp(150px,11vw,220px)] items-center gap-2 rounded-[4px] border border-ring-2 px-2.5 text-[12px] whitespace-nowrap text-ink-3"
          >
            <Glyph name="search" size={13} />
            <span className="min-w-0 flex-1 truncate text-left">Search ticker or company…</span>
          </button>
        </span>
      </div>
    </div>
  );
}

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
/**
 * THE DAY'S PHASES, ONE CARD (owner, 2026-11-13: "a pop out card when you click on pre
 * market - ranked by in play etc, that shows each session with a small brief"). The
 * hours and what each phase ranks by are server/today.py's; the words are a short
 * reading of its docstring. In the order a trading day runs, from the pre-market.
 */
const PHASE_GUIDE: ReadonlyArray<{ key: TodayPhase["key"]; label: string; hours: string; ranks: string; brief: string }> = [
  {
    key: "pre",
    label: "Pre-market",
    hours: "04:00–09:30",
    ranks: "In play",
    brief: "What is in play going into the open: the gap in daily ATRs, pre-market volume against a normal day, a report or fresh news, a level already through, a Day 2 or 3. Each name shows both triggers; the gap's side is a lean, not a call.",
  },
  {
    key: "session",
    label: "Session",
    hours: "09:30–16:00",
    ranks: "Setup score",
    brief: "The best trades now, from the bell, by the engine's setup score: where the entry is, the levels broken, strength against SPY, the market, relative volume, the daily frame and the catalyst. Relative volume is thin until about 09:45, so read the first minutes' with care.",
  },
  {
    key: "after",
    label: "After hours",
    hours: "16:00–20:00",
    ranks: "In play",
    brief: "What is moving after the close and the day's big movers, by the move in daily ATRs, volume against normal, news, a report and tomorrow's Day 2. The prep for the next session starts here.",
  },
  {
    key: "overnight",
    label: "Overnight",
    hours: "20:00–04:00",
    ranks: "In play",
    brief: "The prep for the next session: the evening's movers and the reports due before the open. Weekends and market holidays read as overnight too.",
  },
];

function PhaseGuide({ phase }: { phase: TodayPhase }) {
  return (
    <div className="w-[min(520px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex items-baseline gap-2">
        <span className="qt-cap text-[10.5px] text-ink-3">The Scanner through the day</span>
        <span className="fig ml-auto text-[11px] text-ink-3">New York time</span>
      </div>
      <ul className="mt-2 flex flex-col">
        {PHASE_GUIDE.map((p) => {
          const now = p.key === phase.key;
          return (
            <li key={p.key} className={cn("border-b border-ring/50 py-2 last:border-b-0", now && "-mx-2 rounded-[6px] bg-desk-macro/[0.08] px-2")}>
              <div className="flex flex-wrap items-baseline gap-x-2.5">
                <span className={cn("text-[13px] font-semibold", now ? "text-desk-macro" : "text-ink")}>{p.label}</span>
                <span className="fig text-[11.5px] text-ink-3">{p.hours}</span>
                {now && <span className="qt-cap text-[9.5px] text-desk-macro">now · {phase.next_label} {untilWord(phase.ends_in_min)}</span>}
                <span className="qt-cap ml-auto text-[9.5px] text-ink-2">ranked by {p.ranks.toLowerCase()}</span>
              </div>
              <p className="mt-1 text-[12px] leading-[1.45] text-ink-2">{p.brief}</p>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[11px] leading-[1.4] text-ink-3">On a half day the session ends at 13:00 and the after-hours phase runs to 17:00.</p>
    </div>
  );
}

function SetupStats({
  data,
  later,
  now,
  phase = null,
}: {
  data: ScannerPayload;
  later: CalendarRow | null;
  now: number | null;
  /** Today's phase (the Today view): what the list is ranked for, as the row's first card. */
  phase?: TodayPhase | null;
}) {
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
  const c = regime.conviction;
  const bias = c ? c.bias : regime.bias;
  const biasTip = c
    ? `${liveLine(c)} · plans capped at ${c.max_conviction}\n` +
      c.votes.map((x) => `${x.live === false ? "·" : x.vote === "long" ? "▲" : x.vote === "short" ? "▼" : "–"} ${x.label}: ${x.value} — ${x.note}`).join("\n")
    : (regime.confirm ? CONFIRM_LABEL[regime.confirm] : "Which side the tape is paying");
  return (
    <div className="qt-stats shrink-0 border-b border-ring">
      <div className="qt-stats-row flex flex-wrap">
        {phase && (
          <StatCard
            glyph="clock"
            tint="setup"
            value={phase.label}
            hue="text-desk-macro"
            label={phase.key === "session" ? "Ranked by setup" : "Ranked by in play"}
            title={`${phase.title}${phase.key === "after" || phase.key === "overnight" ? `, for ${dayName(phase.day)}` : ""}. Click for every phase of the day.`}
            sub={`${phase.next_label} ${untilWord(phase.ends_in_min)}`}
            pop={{ label: "The Scanner through the day", panel: <PhaseGuide phase={phase} /> }}
          />
        )}
        {/*
          * THE TAPE IS DRAWN AS A FUTURES BOOK'S BIAS IS (owner, 2026-11-15: "instead of bias
          * saying 6 of 14 reads or whatever, why dont we jus have a scale instead which shows
          * how close to the extremes we are or how close to neutral", then of the first build
          * "why does the scale on stock and futures look different though?"). The card's
          * contents are ScanWide's BiasStat, the one the Futures bias card draws: the side
          * and its score, "Tape" and the grade, and the scale under them. The count is on
          * the hover, with every read.
          *
          * IT STANDS RIGHT OF THE PHASE CARD (owner, the same day: "can we all move the tape
          * card nexct to overnight card on the right"): the hour the list is ranked for,
          * then which way the market leans, then what the list itself holds. It was sixth,
          * after the top mover.
          *
          * NO VIX CARD (owner, the same day: "i dont think we need the vix card since we
          * already have it above"). It stood beside this one from that morning, when the
          * VIX stopped being this card's third line. The masthead carries the VIX with its
          * change on every view, and a click on it there opens the same bands.
          */}
        <div className={STAT_BOX} title={biasTip}>
          <BiasStat what="Tape" side={bias} score={c ? wholeScore(c) : null} grade={c?.grade} />
        </div>
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
