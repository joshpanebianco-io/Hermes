"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Regime, ScanRow, ScannerPayload, Side, Watchlist } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { ScanDetail, levelGlyph, setupLabel, sideHue } from "@/components/panels/ScanDetail";
import { age, compact, dir, inMin, num, pct } from "@/lib/format";
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
 */

const POLL_SEC = 20;

type SideFilter = "all" | Side;
type Bench = "SPY" | "QQQ";
type SortKey = "score" | "rs" | "rvol" | "chg";

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

export function Scanner({ now }: { now: number | null }) {
  const [data, setData] = useState<ScannerPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [sideF, setSideF] = usePersisted<SideFilter>("scan.side", "all", oneOf("all", "long", "short"));
  const [bench, setBench] = usePersisted<Bench>("scan.bench", "SPY", oneOf("SPY", "QQQ"));
  const [sort, setSort] = usePersisted<SortKey>("scan.sort", "score", oneOf("score", "rs", "rvol", "chg"));
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

  useEffect(() => {
    void load();
    const id = setInterval(load, POLL_SEC * 1000);
    return () => clearInterval(id);
  }, [load]);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const kept = sideF === "all" ? all : all.filter((r) => r.score.side === sideF);
    if (sort === "score") return kept; // the engine's own order
    const key = (r: ScanRow): number | null =>
      sort === "rs" ? r.rs[bench] : sort === "rvol" ? r.rvol : r.chg_pct;
    // Rows with no figure sink, whichever way the rest sorts.
    return [...kept].sort((a, b) => {
      const ka = key(a);
      const kb = key(b);
      if (ka == null) return kb == null ? 0 : 1;
      if (kb == null) return -1;
      return sort === "rs" && sideF === "short" ? ka - kb : kb - ka;
    });
  }, [data, sideF, sort, bench]);

  // The selection survives a re-poll by symbol; it falls back to the top row
  // when the name it pointed at is filtered out or dropped from the list.
  const selected = rows.find((r) => r.sym === sel) ?? rows[0] ?? null;

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

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1.75fr)_minmax(400px,1fr)] xl:divide-x xl:divide-ring">
        {/* ---- the ranked list -------------------------------------------- */}
        <section aria-label="Ranked setups" className="flex min-h-0 min-w-0 flex-col">
          <div className="flex flex-wrap items-center gap-3 px-6 pt-4 pb-3">
            <h2 className="text-[13.5px] font-semibold text-ink">Ranked setups</h2>
            <span className="text-[11.5px] text-ink-3">
              structure · relative strength · entry · volume · tape
            </span>
            <div className="ml-auto flex items-center gap-2">
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

          <div className="min-h-0 flex-1 overflow-auto px-3">
            {!data ? (
              <p className="px-3 py-10 text-center text-[12px] text-ink-4">Loading the scanner…</p>
            ) : rows.length === 0 ? (
              <p className="px-3 py-10 text-center text-[12px] text-ink-4">
                {data.offline
                  ? "Nothing to rank until the collector answers."
                  : data.rows.length === 0
                  ? "No names scanned yet — the collector fetches the watchlist a third at a time, so the first full pass takes about a minute and a half."
                  : "Nothing on this side right now."}
              </p>
            ) : (
              <table className="w-full min-w-[980px] border-collapse text-left">
                <thead className="sticky top-0 z-10 bg-bg">
                  <tr className="border-b border-ring">
                    <Th className="w-[28px] text-right">#</Th>
                    <Th>Ticker</Th>
                    <Th sort="score" cur={sort} onSort={setSort} className="w-[92px]">
                      Score
                    </Th>
                    <Th title="Where the trade is right now: the level to retest, or VWAP / the 8 EMA when price has run too far from it">
                      Setup
                    </Th>
                    <Th className="text-right" title="The entry reference, and how far price is from it in ten-minute ATRs">
                      Entry
                    </Th>
                    <Th className="text-right">Last</Th>
                    <Th sort="chg" cur={sort} onSort={setSort} className="text-right" title="Regular session vs the previous close — before the open, still the previous session's move (as the Pine prints it)">
                      Chg
                    </Th>
                    <Th className="text-right" title="Pre-market vs the previous close, or post-market vs today's close">
                      Ext
                    </Th>
                    <Th sort="rs" cur={sort} onSort={setSort} className="text-right" title={`Relative strength vs ${bench}: today's move in this name's daily ATRs, minus ${bench}'s in its own`}>
                      RS
                    </Th>
                    <Th sort="rvol" cur={sort} onSort={setSort} className="text-right" title="Regular-session volume to now against the same time of day on the prior sessions. Starts at the open: Yahoo's pre-market bars carry no volume.">
                      RVol
                    </Th>
                    <Th className="text-center" title="Previous-day high · low, pre-market high · low: a bar is how far price has travelled toward that level; a filled square means broken">
                      PDH · PDL · PMH · PML
                    </Th>
                    <Th>Catalysts</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <Row
                      key={r.sym}
                      r={r}
                      rank={i + 1}
                      bench={bench}
                      on={selected?.sym === r.sym}
                      onPick={() => setSel(r.sym)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* ---- the selected name ------------------------------------------ */}
        <section aria-label="Selected name" className="flex min-h-0 min-w-0 flex-col overflow-y-auto">
          {selected ? (
            <ScanDetail r={selected} bench={bench} now={now} />
          ) : (
            <p className="px-6 py-10 text-center text-[12px] text-ink-4">Pick a row to read it.</p>
          )}
        </section>
      </div>
    </div>
  );
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
            <span aria-hidden className="text-ink-4">•</span>
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
                  <span className={cn("w-[12px] text-center", t ? trendHue(t.trend) : "text-ink-4")}>
                    {t ? trendGlyph(t.trend) : "·"}
                  </span>
                  <Tick value={pct(mv)} className={cn("fig text-[11.5px]", dir(mv))} />
                  {t?.ext_pct != null && <span className="qt-cap text-[9.5px] text-ink-4">ext</span>}
                </div>
              );
            })}
          </div>
        </Cell>
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
              <p className="mt-1.5 text-[11px] text-ink-4">no scheduled US print to wait for</p>
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

function Cell({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 px-6 py-3" title={title}>
      <p className="qt-cap mb-2 text-[10.5px] text-ink-4">{label}</p>
      {children}
    </div>
  );
}

const trendGlyph = (t: -1 | 0 | 1) => (t === 1 ? "▲" : t === -1 ? "▼" : "–");
const trendHue = (t: -1 | 0 | 1) => (t === 1 ? "text-call-fig" : t === -1 ? "text-put-fig" : "text-flip-fig");

/* -------------------------------------------------------------------------- */
/* The table                                                                   */
/* -------------------------------------------------------------------------- */

function Th({
  children,
  className,
  title,
  sort,
  cur,
  onSort,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
  sort?: SortKey;
  cur?: SortKey;
  onSort?: (k: SortKey) => void;
}) {
  const on = sort != null && sort === cur;
  return (
    <th
      scope="col"
      title={title}
      className={cn("qt-cap px-2.5 py-2 text-[10.5px] font-semibold text-ink-4", className)}
    >
      {sort && onSort ? (
        <button
          type="button"
          onClick={() => onSort(sort)}
          className={cn("qt-cap text-[10.5px] hover:text-ink-2", on ? "text-ink" : "text-ink-4")}
        >
          {children}
          {on ? " ↓" : ""}
        </button>
      ) : (
        children
      )}
    </th>
  );
}

function Row({
  r,
  rank,
  bench,
  on,
  onPick,
}: {
  r: ScanRow;
  rank: number;
  bench: Bench;
  on: boolean;
  onPick: () => void;
}) {
  if (!r.ok) {
    return (
      <tr className="border-b border-ring/60">
        <td className="fig px-2.5 py-2 text-right text-[11px] text-ink-4">{rank}</td>
        <td className="px-2.5 py-2 text-[12.5px] font-semibold text-ink-3">{r.sym}</td>
        <td colSpan={10} className="px-2.5 py-2 text-[11.5px] text-ink-4">
          {r.error ?? "no data yet"}
        </td>
      </tr>
    );
  }
  const side = r.score.side;
  const rs = r.rs[bench];
  const entry = r.setup.entry;
  return (
    <tr
      onClick={onPick}
      aria-selected={on}
      className={cn(
        "hit cursor-pointer border-b border-ring/60",
        on && "bg-surface-2",
      )}
    >
      <td className="fig px-2.5 py-2 text-right text-[11px] text-ink-4">{rank}</td>
      <td className="px-2.5 py-2">
        <div className="flex items-baseline gap-1.5">
          <span className={cn("w-[10px] text-[11px]", side ? sideHue(side) : "text-ink-4")}>
            {side === "long" ? "▲" : side === "short" ? "▼" : "·"}
          </span>
          <span className="text-[13px] font-semibold text-ink" title={r.name ?? undefined}>
            {r.sym}
          </span>
          {r.sector && <span className="qt-cap text-[9.5px] text-ink-4">{r.sector}</span>}
        </div>
      </td>
      <td className="px-2.5 py-2">
        <ScoreBar v={r.score.total} />
      </td>
      <td className="px-2.5 py-2 text-[12px]">
        <span className={setupHue(r)}>{setupLabel(r)}</span>
      </td>
      <td className="px-2.5 py-2 text-right">
        {entry ? (
          <span className="fig text-[12px] text-ink-2" title={`${entry.kind} ${num(entry.price)}`}>
            <span className="qt-cap mr-1 text-[9.5px] text-ink-4">{entry.kind === "EMA8" ? "8 EMA" : entry.kind}</span>
            {num(entry.price)}
            <span className="ml-1.5 text-[10.5px] text-ink-4">{entry.dist_atr >= 0 ? "+" : ""}{entry.dist_atr.toFixed(1)}</span>
          </span>
        ) : (
          <span className="text-ink-4">—</span>
        )}
      </td>
      <td className="px-2.5 py-2 text-right">
        <Tick value={num(r.last)} className="fig text-[12.5px] text-ink" />
      </td>
      <td className="px-2.5 py-2 text-right">
        <Tick value={pct(r.chg_pct)} className={cn("fig text-[12px]", dir(r.chg_pct))} />
      </td>
      <td className="px-2.5 py-2 text-right">
        {r.ext_pct != null ? (
          <Tick value={pct(r.ext_pct)} className={cn("fig text-[12px]", dir(r.ext_pct))} />
        ) : (
          <span className="text-ink-4">—</span>
        )}
      </td>
      <td className="px-2.5 py-2 text-right">
        <Tick
          value={rs == null ? "—" : `${rs >= 0 ? "+" : ""}${rs.toFixed(2)}`}
          className={cn(
            "fig text-[12px]",
            rs == null ? "text-ink-4" : rs >= 0.05 ? "up" : rs <= -0.05 ? "down" : "text-ink-2",
          )}
        />
      </td>
      <td className="px-2.5 py-2 text-right">
        <span
          className={cn(
            "fig text-[12px]",
            r.rvol == null ? "text-ink-4" : r.rvol >= 1.5 ? "text-ink" : r.rvol >= 1 ? "text-ink-2" : "text-ink-3",
          )}
          title={r.volume != null ? `${compact(r.volume)} shares today incl. pre/post` : undefined}
        >
          {r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}
        </span>
      </td>
      <td className="px-2.5 py-2">
        <div className="flex items-center justify-center gap-1.5">
          <Prog v={r.progress.pdh} broken={r.broken.pdh} hi label="PDH" price={r.levels.pdh} ready />
          <Prog v={r.progress.pdl} broken={r.broken.pdl} label="PDL" price={r.levels.pdl} ready />
          <span aria-hidden className="mx-0.5 h-[10px] w-px bg-ring-2" />
          <Prog v={r.progress.pmh} broken={r.broken.pmh} hi label="PMH" price={r.levels.pmh} ready={r.levels.pm_done} />
          <Prog v={r.progress.pml} broken={r.broken.pml} label="PML" price={r.levels.pml} ready={r.levels.pm_done} />
        </div>
      </td>
      <td className="px-2.5 py-2">
        <div className="flex flex-wrap gap-x-2 gap-y-0.5">
          {r.flags.slice(0, 3).map((f) => (
            <span
              key={`${f.kind}-${f.text}`}
              className={cn(
                "qt-cap text-[9.5px]",
                f.tone === "warn" ? "text-flip-fig" : f.tone === "good" ? "text-call-fig" : "text-ink-3",
              )}
              title={f.text}
            >
              {flagShort(f.kind, f.text)}
            </span>
          ))}
          {r.news.length > 0 && !r.flags.some((f) => f.kind === "news") && (
            <span className="qt-cap text-[9.5px] text-ink-3" title={r.news[0].title}>
              News {r.news.length}
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

/** A flag's chip text: the kind's short name, plus the first word of detail where it says something. */
function flagShort(kind: ScanRow["flags"][number]["kind"], text: string): string {
  switch (kind) {
    case "earnings":
      return `Earn ${text.replace(/^reports?\s*/i, "").split(/[·—,]/)[0].trim()}`.slice(0, 18);
    case "filing":
      return text.split(/\s/)[0] || "Filing";
    case "event":
      return "Event";
    case "fuel":
      return "Range spent";
    case "extended":
      return "Extended";
    case "gap":
      return "Gap";
    case "halt":
      return "Halt";
    case "news":
      return text.split(/\s/).slice(0, 2).join(" ");
  }
}

function setupHue(r: ScanRow): string {
  const s = r.setup.state;
  if (s === "retest") return cn("font-semibold", r.setup.side ? sideHue(r.setup.side) : "text-ink");
  if (s === "pullback") return r.setup.side ? sideHue(r.setup.side) : "text-ink-2";
  if (s === "approaching") return "text-flip-fig";
  if (s === "extended") return "text-ink-2";
  if (s === "failed") return "text-ink-4 line-through decoration-ink-4/60";
  return "text-ink-3";
}

/** The score as a figure over a flat bar — neutral ink, because a score is not a side. */
function ScoreBar({ v }: { v: number }) {
  return (
    <div className="flex items-center gap-2" title={`${v} of 100 — a heuristic rank, not a probability`}>
      <span className={cn("fig w-[22px] text-right text-[12.5px]", v >= 65 ? "text-ink" : v >= 40 ? "text-ink-2" : "text-ink-3")}>
        {v}
      </span>
      <span className="relative h-[4px] w-[52px] bg-[var(--qt-track,var(--ring))]">
        <span
          className={cn("absolute inset-y-0 left-0", v >= 65 ? "bg-ink" : v >= 40 ? "bg-ink-2" : "bg-ink-4")}
          style={{ width: `${Math.max(0, Math.min(100, v))}%` }}
        />
      </span>
    </div>
  );
}

/**
 * One level's cell — the Pine's 10-segment bar, drawn. A track filled to how
 * far price has travelled toward the level; a filled square once it is
 * broken; dots while the pre-market range is still forming.
 */
function Prog({
  v,
  broken,
  hi,
  label,
  price,
  ready,
}: {
  v: number | null;
  broken: boolean;
  hi?: boolean;
  label: string;
  price: number | null;
  ready: boolean;
}) {
  const tip = `${label} ${num(price)}${
    !ready ? " · pre-market still forming" : broken ? " · broken" : v != null ? ` · ${Math.round(v * 100)}% of the way there` : ""
  }`;
  if (!ready) {
    return (
      <span title={tip} className="fig w-[30px] text-center text-[10px] leading-none text-ink-4">
        {levelGlyph("forming")}
      </span>
    );
  }
  if (broken) {
    return (
      <span title={tip} className="flex w-[30px] justify-center">
        <span className={cn("h-[8px] w-[8px] rounded-[1px]", hi ? "bg-call-fig" : "bg-put-fig")} />
      </span>
    );
  }
  if (v == null) {
    return <span title={tip} className="w-[30px]" />;
  }
  const near = v >= 0.9;
  return (
    <span title={tip} className="relative h-[4px] w-[30px] bg-[var(--qt-track,var(--ring))]">
      <span
        className={cn("absolute inset-y-0 left-0", near ? "bg-flip-fig" : hi ? "bg-call/70" : "bg-put/70")}
        style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }}
      />
    </span>
  );
}

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
        <p className="qt-cap text-[10.5px] text-ink-3">Watchlist</p>
        <p className="text-[11.5px] text-ink-3">
          Tickers separated by spaces or commas, up to 40. SPY and QQQ are always fetched as the benchmarks; list
          them to see them as rows. New names appear within a minute or two.
        </p>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        spellCheck={false}
        className="fig w-full resize-y rounded-[4px] border border-ring-2 bg-bg px-2.5 py-2 text-[12.5px] text-ink outline-none focus:border-ink-3"
      />
      <div className="flex items-center gap-2">
        <span className="fig text-[11px] text-ink-4">{symbols.length} names</span>
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
            {...segItem(true, { className: "border border-ring-2" })}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
