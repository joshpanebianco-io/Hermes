"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Regime, ScannerPayload, ScanRow, Side } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { ScanLog } from "@/components/panels/ScanLog";
import { ScanBreakouts } from "@/components/panels/ScanBreakouts";
import { ScanExtended } from "@/components/panels/ScanExtended";
import { ScanDay23 } from "@/components/panels/ScanDay23";
import { ScanSectors } from "@/components/panels/ScanSectors";
import { gapOf, useWalk } from "@/components/panels/ScanWide";
import { ScanTable, sortValue, type ColSet, type SortKey } from "@/components/panels/ScanTable";
import { WatchlistEditor } from "@/components/panels/ScanWatchlist";
import { useOptionsPrefs } from "@/lib/optionsPrefs";
import { liveLine, scoreText } from "@/lib/bias";
import { age, dir, inMin, num, pct } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { isBool, oneOf, usePersisted } from "@/lib/usePersisted";
import { setAskFocus } from "@/lib/ask/open";
import { openSearch, openTicker, useTicker } from "@/lib/ticker";
import { BAND_LABEL, bandChip, curveOverride } from "@/lib/vix";
import { VixPopover } from "@/components/vol/VixBands";
import { etDay, useNextPrint } from "@/lib/nextPrint";
import type { CalendarRow } from "@/types/terminal";

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

/** Each preset on the Setups table, as a test of one row. */
const PRESET: Record<SideFilter, (r: ScanRow, pinned: ReadonlySet<string>) => boolean> = {
  all: () => true,
  long: (r) => r.score.side === "long",
  short: (r) => r.score.side === "short",
  mag7: (r) => MAG7.has(r.sym),
  pinned: (r, p) => p.has(r.sym),
  both: (r) => r.trend !== 0,
  news: (r) => r.catalyst != null,
  gaps: (r) => Math.abs(gapOf(r) ?? 0) >= 2,
  inside: (r) => {
    const { day_hi: hi, day_lo: lo, pdh, pdl } = r.levels;
    return hi != null && lo != null && pdh != null && pdl != null && hi <= pdh && lo >= pdl;
  },
  day23: (r) => (r.stage ?? 0) >= 2,
};

const PRESET_NAME: ReadonlyArray<{ key: SideFilter; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "mag7", label: "MAG7", title: "The Magnificent Seven: Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta, Tesla" },
  { key: "pinned", label: "Pinned", title: "The names you starred" },
  { key: "both", label: "Both ranges", title: "Through the pre-market range and the previous day's range, the same way" },
  { key: "news", label: "Has news", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened, or is trading pre-market, 2% or more from the previous close" },
  { key: "inside", label: "Inside day", title: "Today's range so far inside the previous day's" },
  { key: "day23", label: "Day 2/3", title: "Day 2 or later of a multi-day move" },
];
const POLL_SEC = 20;
const LIVE_POLL_SEC = 5;

type SideFilter = "all" | Side | "mag7" | "pinned" | "both" | "news" | "gaps" | "inside" | "day23";
type Bench = "SPY" | "QQQ";

/**
 * THE MAGNIFICENT SEVEN, as a filter beside the side filter (owner,
 * 2026-10-14: "where we have all long short toggles, can we also add one for
 * MAG7"). Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta and Tesla — either
 * Alphabet line counts, so the filter still finds it if the list goes back to
 * GOOG. It picks names, not a side: each keeps its own long or short read.
 */
const MAG7: ReadonlySet<string> = new Set(["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA"]);

const SESSION_LABEL: Record<ScannerPayload["session"], string> = {
  pre: "Pre-market — PMH / PML still forming",
  rth: "Regular session",
  post: "Post-market",
  closed: "Market closed — levels for the next session",
};

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
 * tab. Setups is the deep list; Breakouts, Extended hours, Day 2/3 and Sectors are the
 * wide scan read four ways; the Signal log is what happened.
 */
type View = "setups" | "breakouts" | "extended" | "day23" | "sectors" | "log";

const VIEWS: ReadonlyArray<{ key: View; label: string; title: string }> = [
  { key: "setups", label: "Setups", title: "The list, ranked: levels, signals, the score and the options" },
  { key: "breakouts", label: "Breakouts", title: "Every US stock against its levels" },
  { key: "extended", label: "Extended hours", title: "The pre-market and after-hours gappers" },
  { key: "day23", label: "Day 2/3", title: "The big movers, and whether they are still moving" },
  { key: "sectors", label: "Sectors", title: "The sector and theme heat map, the industries, and the stocks in each" },
  { key: "log", label: "Signal log", title: "Every signal, and what it did afterwards" },
];

export function Scanner({ now: shellNow, calendar = NO_ROWS }: { now?: number | null; calendar?: CalendarRow[] } = {}) {
  const ownNow = useMinuteClock();
  const now = shellNow ?? ownNow;
  const [data, setData] = useState<ScannerPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [view, setView] = usePersisted<View>("scan.view", "setups", oneOf("setups", "breakouts", "extended", "day23", "sectors", "log"));
  const ticker = useTicker();
  // Shown when no print falls inside the six hours the engine prices in (see RegimeStrip).
  const later = useNextPrint(calendar, now);

  // `?sym=` (an alert's click-through) opens straight onto that name.
  useEffect(() => {
    const s = new URLSearchParams(window.location.search).get("sym");
    if (s) {
      setSel(s.toUpperCase());
      setView("setups");
      openTicker(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [sideF, setSideF] = usePersisted<SideFilter>(
    "scan.side",
    "all",
    oneOf("all", "long", "short", "mag7", "pinned", "both", "news", "gaps", "inside", "day23"),
  );
  const [bench, setBench] = usePersisted<Bench>("scan.bench", "SPY", oneOf("SPY", "QQQ"));
  const [sort, setSort] = usePersisted<SortKey>(
    "scan.sort",
    "score",
    oneOf("score", "rs", "rvol", "chg", "gap", "ext", "vol", "trend", "ivrv", "em"),
  );
  // A new key, so every browser starts on the clean view once.
  const [cols, setCols] = usePersisted<ColSet>("scan.cols2", "overview", oneOf("overview", "ranked", "options"));
  const { budget } = useOptionsPrefs();
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

  const live = data?.session === "rth";
  useEffect(() => {
    void load();
    const id = setInterval(load, (live ? LIVE_POLL_SEC : POLL_SEC) * 1000);
    return () => clearInterval(id);
  }, [load, live]);

  const pinned = useMemo<ReadonlySet<string>>(() => new Set(data?.pinned ?? []), [data?.pinned]);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const kept = all.filter((r) => PRESET[sideF](r, pinned));
    if (sort === "score") return kept; // the engine's own order
    // Rows with no figure sink, whichever way the rest sorts. On the short
    // side the strongest is the most NEGATIVE, so the signed columns flip.
    const flip = sideF === "short" && (sort === "rs" || sort === "chg" || sort === "gap" || sort === "ext" || sort === "trend");
    return [...kept].sort((a, b) => {
      const ka = sortValue(a, sort, bench);
      const kb = sortValue(b, sort, bench);
      if (ka == null) return kb == null ? 0 : 1;
      if (kb == null) return -1;
      return flip ? ka - kb : kb - ka;
    });
  }, [data, sideF, sort, bench, pinned]);

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

  /*
   * THE KEYBOARD WALKS THE LIST. A row is a stop in the tab order, Enter picks
   * it, and ↑ / ↓ move the selection and the focus together — reading thirty
   * names is faster as a walk down a column than as thirty clicks.
   */
  const tbody = useRef<HTMLTableSectionElement | null>(null);
  const step = (from: string, delta: number) => {
    const i = rows.findIndex((r) => r.sym === from);
    const next = rows[Math.max(0, Math.min(rows.length - 1, i + delta))];
    if (!next) return;
    setSel(next.sym);
    if (ticker) openTicker(next.sym);
    tbody.current?.querySelector<HTMLElement>(`tr[data-sym="${next.sym}"]`)?.focus();
  };
  const pick = (s: string) => {
    setSel(s);
    openTicker(s);
  };

  // With the slide-out open, the arrows walk wherever the focus is.
  const walkable = useMemo(() => (view === "setups" ? rows.map((r) => r.sym) : []), [view, rows]);
  useWalk(walkable);

  const counts = useMemo(() => {
    const c = {} as Record<SideFilter, number>;
    for (const { key } of PRESET_NAME) c[key] = (data?.rows ?? []).filter((r) => PRESET[key](r, pinned)).length;
    return c;
  }, [data, pinned]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Masthead
        data={data}
        onWatchlist={() => setEditing((v) => !v)}
        editing={editing}
        view={view}
        onView={setView}
      />
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
        <p className="border-b border-ring bg-err/10 px-6 py-2 text-[12px] text-err">
          <strong className="font-semibold">Scanner unavailable.</strong>{" "}
          {data?.offline ? `${data.offline.reason} — expected at ${data.offline.api}.` : failed} Nothing
          below is cached or invented.
        </p>
      ) : null}

      {data && !data.offline && (view === "setups" || view === "log") && <RegimeStrip regime={data.regime} later={later} now={now} />}

      {view === "breakouts" ? (
        <ScanBreakouts onTrackChanged={load} />
      ) : view === "extended" ? (
        <ScanExtended onTrackChanged={load} />
      ) : view === "day23" ? (
        <ScanDay23 onTrackChanged={load} />
      ) : view === "sectors" ? (
        <ScanSectors onTrackChanged={load} />
      ) : (
      <div className="flex min-h-0 flex-1 flex-col">
        {/* ---- the ranked list: the whole width, the name opens over it --- */}
        <section aria-label="Ranked setups" className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-3 px-6 pt-3 pb-3">
            {view === "setups" && (
              <span className="seg" title="Which columns: the short list of what matters, every column the Pine's scanner has, or the options">
                <button type="button" onClick={() => setCols("overview")} {...segItem(cols === "overview")}>
                  Overview
                </button>
                <button type="button" onClick={() => setCols("ranked")} {...segItem(cols === "ranked")}>
                  Levels
                </button>
                <button type="button" onClick={() => setCols("options")} {...segItem(cols === "options")}>
                  Options
                </button>
              </span>
            )}
            {view === "log" && <span className="text-[11.5px] text-ink-3">every signal, and what it did afterwards</span>}
            <div className={cn("ml-auto flex items-center gap-2", view === "log" && "hidden")}>
              <span className="seg">
                {PRESET_NAME.map((p) => (
                  <button key={p.key} type="button" onClick={() => setSideF(p.key)} title={p.title} {...segItem(sideF === p.key)}>
                    {p.label}
                    <span className="seg-n">{counts[p.key]}</span>
                  </button>
                ))}
              </span>
              <span
                className="seg"
                title="Which benchmark the RS column reads against. The score always uses SPY."
              >
                {(["SPY", "QQQ"] as const).map((b) => (
                  <button key={b} type="button" onClick={() => setBench(b)} {...segItem(bench === b)}>
                    RS {b}
                  </button>
                ))}
              </span>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {view === "log" ? (
              <ScanLog onPick={(s) => {
                setSel(s);
                setView("setups");
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
                sort={sort}
                onSort={setSort}
                now={now}
                selected={ticker ?? selected?.sym ?? null}
                onPick={pick}
                onStep={step}
                tbody={tbody}
                budget={budget}
                pinned={pinned}
                onPinned={load}
              />
            )}
          </div>
        </section>
      </div>
      )}
    </div>
  );
}

/** The first load: the helm, in the space the table is about to take. */
function TableSkeleton() {
  return <HelmLoader label="Loading the scanner" size={48} minHeight={420} />;
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
}: {
  data: ScannerPayload | null;
  onWatchlist: () => void;
  editing: boolean;
  view: View;
  onView: (v: View) => void;
}) {
  const ok = data?.rows.filter((r) => r.ok).length ?? 0;
  const total = data?.watchlist.length ?? 0;
  const fromPool = data?.pool?.promoted.length ?? 0;
  return (
    <div className="flex min-h-[50px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-ring px-6 py-2">
      <h2 className="text-[13.5px] font-semibold whitespace-nowrap text-ink">Scanner</h2>
      <span className="seg shrink-0">
        {VIEWS.map((v) => (
          <button key={v.key} type="button" title={v.title} onClick={() => onView(v.key)} {...segItem(view === v.key)}>
            {v.label}
          </button>
        ))}
      </span>
      <p className="flex min-w-0 flex-1 items-baseline gap-x-2.5 truncate text-[11.5px] text-ink-3">
        <span className="max-[2199px]:hidden">break and retest of PDH / PDL and PMH / PML, or VWAP / the 8 EMA when extended</span>
        {data && !data.offline && (
          <>
            <span aria-hidden className="text-ink-3">•</span>
            <span className="whitespace-nowrap text-ink-2">{SESSION_LABEL[data.session]}</span>
            {data.trading_day && (
              <span className="fig whitespace-nowrap text-ink-3">levels for {dayName(data.trading_day)}</span>
            )}
          </>
        )}
      </p>
      <div className="flex shrink-0 items-center gap-3">
        {data && !data.offline && (
          <span
            className="fig text-[11px] text-ink-3"
            title={data.status?.error ?? data.status?.notes.join(" · ") ?? undefined}
          >
            <span
              aria-hidden
              className={cn(
                "mr-1.5 inline-block h-[6px] w-[6px] rounded-[1px] align-middle",
                data.status?.ok ? "bg-call" : "bg-err",
              )}
            />
            {ok}/{total} names{fromPool > 0 ? ` · ${fromPool} from the pool` : ""} · {age(data.age_min)}
          </span>
        )}
        <button type="button" onClick={openSearch} title="Find any ticker or company (Ctrl+K)" {...segItem(false, { className: "border border-ring-2" })}>
          Search <span className="fig ml-1 text-[10px] text-ink-3">Ctrl K</span>
        </button>
        <button type="button" onClick={onWatchlist} {...segItem(editing, { className: "border border-ring-2" })}>
          Watchlist
        </button>
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

/* -------------------------------------------------------------------------- */
/* The weather: VIX, the tape, the bias, the next print                        */
/* -------------------------------------------------------------------------- */

/**
 * THE WEATHER ON ONE LINE (owner, 2026-11-09: "i like how it is a bit more
 * streamlined"). This was five tall cells and a block of notes, a fifth of a 1080
 * screen above the table it serves. Every figure is still here, the detail behind
 * its hover or a click, and the desk's lines on how to trade this band one button
 * away, remembered.
 */
function RegimeStrip({ regime, later, now }: { regime: Regime; later: CalendarRow | null; now: number | null }) {
  const [notes, setNotes] = usePersisted<boolean>("scan.notes", false, isBool);
  const v = regime.vix;
  const shapeHue = v.shape === "backwardation" ? "text-put-fig" : v.shape === "contango" ? "text-call-fig" : "text-flip-fig";
  const bandHue =
    regime.band === "stressed" ? "text-put-fig" : regime.band === "elevated" ? "text-flip-fig" : regime.band === "grind" ? "text-ink-3" : "text-ink-2";
  const c = regime.conviction;
  const bias = c ? c.bias : regime.bias;
  const biasHue = bias === "long" ? "text-call-fig" : bias === "short" ? "text-put-fig" : "text-ink-3";
  const biasTip = c
    ? `${liveLine(c)} · plans capped at ${c.max_conviction}\n` +
      c.votes.map((x) => `${x.live === false ? "·" : x.vote === "long" ? "▲" : x.vote === "short" ? "▼" : "–"} ${x.label}: ${x.value} — ${x.note}`).join("\n")
    : (regime.confirm ? CONFIRM_LABEL[regime.confirm] : "Which side the tape is paying");
  const nextTip = "The next US release scored 4+ on the calendar. Inside six hours the engine prices it in; inside thirty minutes it costs every score ten points.";
  return (
    <div className="shrink-0 border-b border-ring">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-1.5 px-6 py-2">
        <VixPopover facts={{ ...v, band: regime.band, sub: regime.sub ?? null, month: v.month ?? null }} className="-mx-1.5 px-1.5 py-0.5">
          <span className="flex items-baseline gap-2" title={`VIX/VIX3M ${v.ratio != null ? v.ratio.toFixed(2) : "—"} ${v.shape}${v.vvix != null ? ` · VVIX ${num(v.vvix, 1)}` : ""}\nImplied 30-day S&P 500 volatility: the weather, not a signal. Click for the bands.`}>
            <span className="qt-cap text-[10px] text-ink-3">VIX</span>
            <Tick value={num(v.last, 2)} className="fig text-[15px] leading-none text-ink" />
            <Tick value={pct(v.pct)} className={cn("fig text-[11.5px]", dir(v.pct))} />
            {regime.band && <span className={cn("qt-cap text-[10px]", bandHue)}>{bandChip(regime.band, regime.sub ?? null, curveOverride(regime.vix?.last, regime.band)) ?? BAND_LABEL[regime.band]}</span>}
            <span className={cn("text-[11px]", shapeHue)}>{v.shape !== "unknown" ? v.shape : ""}</span>
          </span>
        </VixPopover>
        <Stat label="Implied SPY" title="VIX ÷ √252: the one-day, one-standard-deviation move the options market prices for SPY">
          <span className="fig text-[13px] text-ink">{regime.spy_em_pct != null ? `±${regime.spy_em_pct.toFixed(2)}%` : "—"}</span>
        </Stat>
        <Stat label="Tape" title="SPY, QQQ and IWM against their own PDH / PMH and PDL / PML; the move outside the session once it is shut">
          <span className="flex items-baseline gap-3">
            {(["SPY", "QQQ", "IWM"] as const).map((k) => {
              const t = regime.tape[k];
              const mv = t ? (t.ext_pct ?? t.chg_pct) : null;
              return (
                <span key={k} className="flex items-baseline gap-1 text-[11.5px]">
                  <span className="fig text-ink-3">{k}</span>
                  <span className={cn("text-[10px]", t ? trendHue(t.trend) : "text-ink-3")}>{t ? trendGlyph(t.trend) : "·"}</span>
                  <Tick value={pct(mv)} className={cn("fig", dir(mv))} />
                </span>
              );
            })}
          </span>
        </Stat>
        <Stat label="Tape conviction" title={biasTip}>
          <span className={cn("text-[13px] font-semibold", biasHue)}>{bias === "long" ? "▲ Long" : bias === "short" ? "▼ Short" : "No lean"}</span>
          {c && <span className={cn("fig ml-1.5 text-[13px] font-semibold", biasHue)}>{c.score != null ? scoreText(c.score) : `${c.agree} of ${c.total}`}</span>}
          {c && <span className={cn("qt-cap ml-1.5 text-[10px]", c.grade === "strong" ? biasHue : "text-ink-3")}>{c.grade}</span>}
        </Stat>
        <Stat label="Next" title={nextTip}>
          {regime.event ? (
            <span className="text-[12px] text-ink-2">
              <span className={cn("fig", regime.event.in_min <= 30 ? "text-flip-fig" : "text-ink")}>{regime.event.in_min < 0 ? "just printed" : `in ${inMin(regime.event.in_min)}`}</span> {regime.event.title}
            </span>
          ) : later && later.ts !== null && now !== null ? (
            <span className="text-[12px] text-ink-2">
              <span className="fig text-ink-2">in {inMin((later.ts - now / 1000) / 60)}</span> {etDay(later.ts, now)}
              {later.event}
            </span>
          ) : (
            <span className="text-[12px] text-ink-3">None scheduled</span>
          )}
        </Stat>
        {regime.notes.length > 0 && (
          <button type="button" onClick={() => setNotes((x) => !x)} aria-expanded={notes} className="hit ml-auto text-[11px] text-ink-3 hover:text-ink-2">
            How to trade this {notes ? "▴" : "▾"}
          </button>
        )}
      </div>
      {notes && regime.notes.length > 0 && (
        <ul className="flex flex-wrap gap-x-6 gap-y-1 border-t border-ring px-6 py-2.5 text-[12px] leading-[1.45] text-ink-2">
          {regime.notes.map((n) => (
            <li key={n} className="flex gap-2">
              <span aria-hidden className="mt-[7px] h-[4px] w-[4px] shrink-0 rounded-[1px] bg-ink-4" />
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-2" title={title}>
      <span className="qt-cap shrink-0 text-[10px] text-ink-3">{label}</span>
      <span className="min-w-0 truncate">{children}</span>
    </div>
  );
}

const trendGlyph = (t: -1 | 0 | 1) => (t === 1 ? "▲" : t === -1 ? "▼" : "–");
const trendHue = (t: -1 | 0 | 1) => (t === 1 ? "text-call-fig" : t === -1 ? "text-put-fig" : "text-flip-fig");
