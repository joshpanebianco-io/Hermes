"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Conviction, Regime, ScannerPayload, Side, Watchlist } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { ScanDetail } from "@/components/panels/ScanDetail";
import { ScanLog } from "@/components/panels/ScanLog";
import { ScanTable, sortValue, type ColSet, type SortKey } from "@/components/panels/ScanTable";
import { useOptionsPrefs } from "@/lib/optionsPrefs";
import { age, dir, inMin, num, pct } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * The Scanner — LE_Model.pine's scanner table, ranked, with the tape and the
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
 * structure, relative strength, entry location, volume, the market — each one
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

const POLL_SEC = 20;
const LIVE_POLL_SEC = 5;

type SideFilter = "all" | Side;
type Bench = "SPY" | "QQQ";

const SESSION_LABEL: Record<ScannerPayload["session"], string> = {
  pre: "Pre-market — PMH / PML still forming",
  rth: "Regular session",
  post: "Post-market",
  closed: "Market closed — levels for the next session",
};

const BAND_LABEL: Record<NonNullable<Regime["band"]>, string> = {
  grind: "Grind",
  normal: "Normal",
  elevated: "Elevated",
  stressed: "Stressed",
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

type View = "setups" | "log";

export function Scanner({ now: shellNow }: { now?: number | null } = {}) {
  const ownNow = useMinuteClock();
  const now = shellNow ?? ownNow;
  const [data, setData] = useState<ScannerPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [view, setView] = usePersisted<View>("scan.view", "setups", oneOf("setups", "log"));

  // `?sym=` (an alert's click-through) opens straight onto that name.
  useEffect(() => {
    const s = new URLSearchParams(window.location.search).get("sym");
    if (s) {
      setSel(s.toUpperCase());
      setView("setups");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [sideF, setSideF] = usePersisted<SideFilter>("scan.side", "all", oneOf("all", "long", "short"));
  const [bench, setBench] = usePersisted<Bench>("scan.bench", "SPY", oneOf("SPY", "QQQ"));
  const [sort, setSort] = usePersisted<SortKey>(
    "scan.sort",
    "score",
    oneOf("score", "rs", "rvol", "chg", "ext", "vol", "trend", "ivrv", "em"),
  );
  const [cols, setCols] = usePersisted<ColSet>("scan.cols", "ranked", oneOf("ranked", "options"));
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

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const kept = sideF === "all" ? all : all.filter((r) => r.score.side === sideF);
    if (sort === "score") return kept; // the engine's own order
    // Rows with no figure sink, whichever way the rest sorts. On the short
    // side the strongest is the most NEGATIVE, so the signed columns flip.
    const flip = sideF === "short" && (sort === "rs" || sort === "chg" || sort === "ext" || sort === "trend");
    return [...kept].sort((a, b) => {
      const ka = sortValue(a, sort, bench);
      const kb = sortValue(b, sort, bench);
      if (ka == null) return kb == null ? 0 : 1;
      if (kb == null) return -1;
      return flip ? ka - kb : kb - ka;
    });
  }, [data, sideF, sort, bench]);

  // The selection survives a re-poll by symbol; it falls back to the top row
  // when the name it pointed at is filtered out or dropped from the list.
  const selected = rows.find((r) => r.sym === sel) ?? rows[0] ?? null;

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
    tbody.current?.querySelector<HTMLElement>(`tr[data-sym="${next.sym}"]`)?.focus();
  };

  const counts = useMemo(() => {
    const c = { all: 0, long: 0, short: 0 };
    for (const r of data?.rows ?? []) {
      c.all += 1;
      if (r.score.side) c[r.score.side] += 1;
    }
    return c;
  }, [data]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Masthead
        data={data}
        onWatchlist={() => setEditing((v) => !v)}
        editing={editing}
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

      {data && !data.offline && <RegimeStrip regime={data.regime} />}

      {/*
        * THE DETAIL PANE IS A FIXED COLUMN and the table takes everything else:
        * the table now carries every column the Pine's scanner does, so it is
        * the one that needs the width. 460 below 1600, 600 above (owner,
        * 2026-10-13: "slightly more width" for the chart, setup and options;
        * 2026-10-14: "a bit more width" again, for options and why it ranks);
        * past what fits, the table scrolls sideways under its pinned ticker.
        */}
      <div className="grid min-h-0 flex-1 grid-cols-1 xl:divide-x xl:divide-ring min-[1280px]:max-[1599px]:grid-cols-[minmax(0,1fr)_460px] min-[1600px]:grid-cols-[minmax(0,1fr)_600px]">
        {/* ---- the ranked list -------------------------------------------- */}
        <section aria-label="Ranked setups" className="flex min-h-0 min-w-0 flex-col">
          <div className="flex flex-wrap items-center gap-3 px-6 pt-4 pb-3">
            <span className="seg">
              <button type="button" onClick={() => setView("setups")} {...segItem(view === "setups")}>
                Ranked setups
              </button>
              <button type="button" onClick={() => setView("log")} {...segItem(view === "log")}>
                Signal log
              </button>
            </span>
            {view === "setups" && (
              <span className="seg" title="Which columns: the Pine's scanner and the setup, or the options">
                <button type="button" onClick={() => setCols("ranked")} {...segItem(cols === "ranked")}>
                  Levels
                </button>
                <button type="button" onClick={() => setCols("options")} {...segItem(cols === "options")}>
                  Options
                </button>
              </span>
            )}
            <span className="text-[11.5px] text-ink-3 max-[1599px]:hidden">
              {view === "log"
                ? "every signal, and what it did afterwards"
                : cols === "options"
                  ? "implied vs realised · the straddle's move · liquidity · the contract"
                  : "the Pine's scanner, ranked by structure · strength · entry · tape"}
            </span>
            <div className={cn("ml-auto flex items-center gap-2", view === "log" && "hidden")}>
              <span className="seg">
                {(["all", "long", "short"] as const).map((k) => (
                  <button key={k} type="button" onClick={() => setSideF(k)} {...segItem(sideF === k)}>
                    {k === "all" ? "All" : k === "long" ? "Long" : "Short"}
                    <span className="seg-n">{counts[k]}</span>
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
                selected={selected?.sym ?? null}
                onPick={setSel}
                onStep={step}
                tbody={tbody}
                budget={budget}
              />
            )}
          </div>
        </section>

        {/* ---- the selected name ------------------------------------------ */}
        <section aria-label="Selected name" className="flex min-h-0 min-w-0 flex-col overflow-y-auto">
          {selected ? (
            <ScanDetail r={selected} bench={bench} now={now} />
          ) : (
            <p className="px-6 py-10 text-center text-[12px] text-ink-3">Pick a row to read it.</p>
          )}
        </section>
      </div>
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
}: {
  data: ScannerPayload | null;
  onWatchlist: () => void;
  editing: boolean;
}) {
  const ok = data?.rows.filter((r) => r.ok).length ?? 0;
  const total = data?.watchlist.length ?? 0;
  return (
    <div className="flex min-h-[50px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-ring px-6 py-2">
      <h2 className="text-[13.5px] font-semibold whitespace-nowrap text-ink">Scanner</h2>
      <p className="flex min-w-0 flex-1 items-baseline gap-x-2.5 truncate text-[11.5px] text-ink-3">
        <span className="qt-cap text-ink-3">LE model</span>
        <span>break and retest of PDH / PDL and PMH / PML, or VWAP / the 8 EMA when extended</span>
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
            {ok}/{total} names · {age(data.age_min)}
          </span>
        )}
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

function RegimeStrip({ regime }: { regime: Regime }) {
  const v = regime.vix;
  const shapeHue =
    v.shape === "backwardation" ? "text-put-fig" : v.shape === "contango" ? "text-call-fig" : "text-flip-fig";
  const bandHue =
    regime.band === "stressed"
      ? "text-put-fig"
      : regime.band === "elevated"
        ? "text-flip-fig"
        : regime.band === "grind"
          ? "text-ink-3"
          : "text-ink";
  return (
    <div className="shrink-0 border-b border-ring">
      <div className="grid grid-cols-2 divide-ring md:grid-cols-5 md:divide-x">
        <Cell label="VIX" title="Implied 30-day S&P 500 volatility. The weather, not a signal: it sets how far things travel and how hard to press.">
          <div className="flex items-baseline gap-2">
            <Tick value={num(v.last, 2)} className="fig text-[19px] leading-none text-ink" />
            <Tick value={pct(v.pct)} className={cn("fig text-[11.5px]", dir(v.pct))} />
            {regime.band && <span className={cn("qt-cap text-[10.5px]", bandHue)}>{BAND_LABEL[regime.band]}</span>}
          </div>
          <p className="mt-1.5 text-[11px] text-ink-3">
            VIX/VIX3M <span className="fig text-ink-2">{v.ratio != null ? v.ratio.toFixed(2) : "—"}</span>{" "}
            <span className={shapeHue}>{v.shape}</span>
            {v.vvix != null && (
              <>
                {" "}· VVIX <span className="fig text-ink-2">{num(v.vvix, 1)}</span>
              </>
            )}
          </p>
        </Cell>
        <Cell label="Implied SPY day" title="VIX ÷ √252 — the one-day, one-standard-deviation move the options market prices for SPY">
          <span className="fig text-[19px] leading-none text-ink">
            {regime.spy_em_pct != null ? `±${regime.spy_em_pct.toFixed(2)}%` : "—"}
          </span>
          <p className="mt-1.5 text-[11px] text-ink-3">one-sigma, from VIX</p>
        </Cell>
        <Cell label="Tape" title="SPY, QQQ and IWM against their own PDH / PMH and PDL / PML — the Pine's trend column for the market itself">
          <div className="flex flex-col gap-1">
            {(["SPY", "QQQ", "IWM"] as const).map((k) => {
              const t = regime.tape[k];
              // The LIVE move: before the open the session change is still
              // yesterday's, so the pre-market move is the one the tape is making.
              const mv = t ? (t.ext_pct ?? t.chg_pct) : null;
              return (
                <div key={k} className="flex items-baseline gap-2 text-[12px]">
                  <span className="fig w-[30px] text-ink-2">{k}</span>
                  <span className={cn("w-[12px] text-center", t ? trendHue(t.trend) : "text-ink-3")}>
                    {t ? trendGlyph(t.trend) : "·"}
                  </span>
                  <Tick value={pct(mv)} className={cn("fig text-[11.5px]", dir(mv))} />
                  {t?.ext_pct != null && <span className="qt-cap text-[9.5px] text-ink-3">ext</span>}
                </div>
              );
            })}
          </div>
        </Cell>
        {regime.conviction ? (
          <ConvictionCell c={regime.conviction} />
        ) : (
          <Cell label="Bias" title="Which side the tape is paying: SPY and QQQ against their levels, confirmed or contradicted by which way VIX is moving">
            <span
              className={cn(
                "text-[17px] leading-none font-semibold",
                regime.bias === "long" ? "text-call-fig" : regime.bias === "short" ? "text-put-fig" : "text-ink-3",
              )}
            >
              {regime.bias === "long" ? "▲ Long" : regime.bias === "short" ? "▼ Short" : "Neutral"}
            </span>
            <p className="mt-1.5 text-[11px] text-ink-3">
              {regime.confirm ? CONFIRM_LABEL[regime.confirm] : "no read from VIX yet"}
            </p>
          </Cell>
        )}
        <Cell label="Next high-impact" title="The next US release scored 4+ on the calendar, inside six hours. Inside thirty minutes it costs every score ten points.">
          {regime.event ? (
            <>
              <span
                className={cn(
                  "fig text-[17px] leading-none",
                  regime.event.in_min <= 30 ? "text-flip-fig" : "text-ink",
                )}
              >
                {regime.event.in_min < 0 ? "just printed" : `in ${inMin(regime.event.in_min)}`}
              </span>
              <p className="mt-1.5 truncate text-[11px] text-ink-3" title={regime.event.title}>
                <span className="fig text-ink-2">{regime.event.et}</span> {regime.event.title}
              </p>
            </>
          ) : (
            <>
              <span className="text-[14px] leading-none text-ink-3">Nothing inside 6h</span>
              <p className="mt-1.5 text-[11px] text-ink-3">no scheduled US print to wait for</p>
            </>
          )}
        </Cell>
      </div>
      {regime.notes.length > 0 && (
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

/**
 * The tape's conviction: how many independent signals agree with the bias —
 * SPY and QQQ against their levels, VIX and its curve, sectors, the equal
 * weight, credit, yields, the dollar, index volume, participation. A count the
 * engine makes, so "short" on a 6-of-11 tape and "short" on a 3-of-11 tape
 * stop looking the same. Every vote, with its figure and its reason, is on
 * the hover.
 */
function ConvictionCell({ c }: { c: Conviction }) {
  const hue = c.bias === "long" ? "text-call-fig" : c.bias === "short" ? "text-put-fig" : "text-ink-3";
  const tip = c.votes
    .map((v) => `${v.vote === "long" ? "▲" : v.vote === "short" ? "▼" : "–"} ${v.label}: ${v.value} — ${v.note}`)
    .join("\n");
  const seg = (n: number, cls: string) =>
    n > 0 ? <span className={cn("h-full", cls)} style={{ width: `${(n / Math.max(1, c.total)) * 100}%` }} /> : null;
  const agreeHue = c.bias === "long" ? "bg-call-fig" : "bg-put-fig";
  const againstHue = c.bias === "long" ? "bg-put-fig" : "bg-call-fig";
  return (
    <Cell label="Tape conviction" title={tip}>
      <div className="flex items-baseline gap-2">
        <span className={cn("text-[17px] leading-none font-semibold", hue)}>
          {c.bias === "long" ? "▲ Long" : c.bias === "short" ? "▼ Short" : "Neutral"}
        </span>
        <span className="fig text-[12px] text-ink-2">
          {c.agree} of {c.total}
        </span>
        <span className={cn("qt-cap text-[10px]", c.grade === "strong" ? hue : c.grade === "weak" || c.grade === "none" ? "text-ink-3" : "text-ink-2")}>
          {c.grade}
        </span>
      </div>
      {c.bias && (
        <span className="mt-2 flex h-[4px] w-full max-w-[220px] gap-px bg-[var(--qt-track,var(--ring))]" aria-label={`${c.agree} agree, ${c.against} against, ${c.neutral} neutral`}>
          {seg(c.agree, agreeHue)}
          {seg(c.against, againstHue)}
        </span>
      )}
      <p className="mt-1.5 text-[11px] text-ink-3">
        {c.agree} agree · {c.against} against · {c.neutral} neutral · plans capped at {c.max_conviction}
      </p>
    </Cell>
  );
}

function Cell({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 px-6 py-3" title={title}>
      <p className="qt-cap mb-2 text-[10.5px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}

const trendGlyph = (t: -1 | 0 | 1) => (t === 1 ? "▲" : t === -1 ? "▼" : "–");
const trendHue = (t: -1 | 0 | 1) => (t === 1 ? "text-call-fig" : t === -1 ? "text-put-fig" : "text-flip-fig");

/* -------------------------------------------------------------------------- */
/* Watchlist                                                                   */
/* -------------------------------------------------------------------------- */

function WatchlistEditor({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [text, setText] = useState("");
  const [dflt, setDflt] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    void fetch("/api/scanner/watchlist", { cache: "no-store" })
      .then((r) => r.json() as Promise<Watchlist>)
      .then((w) => {
        if (!live) return;
        setText(w.symbols.join(" "));
        setDflt(w.default);
        if (w.error) setErr(w.error);
      })
      .catch((e: unknown) => live && setErr(e instanceof Error ? e.message : "could not read the list"));
    return () => {
      live = false;
    };
  }, []);

  const symbols = text
    .toUpperCase()
    .split(/[\s,;]+/)
    .map((s) => s.replace(/^\$/, "").trim())
    .filter(Boolean);

  const save = async (list: string[]) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/scanner/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: list }),
      });
      const w = (await r.json()) as Watchlist;
      if (!r.ok || w.error) {
        setErr(w.error ?? `HTTP ${r.status}`);
        return;
      }
      if (w.rejected && w.rejected.length > 0) {
        // Saved, but not all of it — keep the editor open so the dropped
        // names are seen rather than silently missing from the list.
        setText(w.symbols.join(" "));
        setErr(`Saved without ${w.rejected.join(", ")} — not a valid ticker.`);
        return;
      }
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-ring bg-surface-2/40 px-6 py-3">
      <div className="flex items-baseline gap-3">
        <label htmlFor="scan-watchlist" className="qt-cap text-[10.5px] text-ink-3">
          Watchlist
        </label>
        <p className="text-[11.5px] text-ink-3">
          Tickers separated by spaces or commas, up to 40. SPY and QQQ are always fetched as the benchmarks; list
          them to see them as rows. New names appear within a minute or two.
        </p>
      </div>
      <textarea
        id="scan-watchlist"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        spellCheck={false}
        className="fig w-full resize-y rounded-[4px] border border-ring-2 bg-bg px-2.5 py-2 text-[12.5px] text-ink outline-none focus:border-ink-3"
      />
      <div className="flex items-center gap-2">
        <span className="fig text-[11px] text-ink-3">{symbols.length} names</span>
        {err && <span className="text-[11.5px] text-err">{err}</span>}
        <div className="ml-auto flex items-center gap-2">
          {dflt.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setText(dflt.join(" "))}
              {...segItem(false, { className: "border border-ring-2" })}
              title={dflt.join(" ")}
            >
              Reset to the Pine list
            </button>
          )}
          <button type="button" onClick={onCancel} {...segItem(false, { className: "border border-ring-2" })}>
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || symbols.length === 0}
            onClick={() => void save(symbols)}
            {...segItem(true, { className: "border border-ring-2 disabled:cursor-not-allowed disabled:opacity-40" })}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
