"use client";

import { useState } from "react";
import { isBool, usePersisted } from "@/lib/usePersisted";
import type { Catalyst, NewsRead, PreContext, ScanRow, Side } from "@/types/scanner";
import { CARD, DIRECTION_WORD, Glyph, capShort, gapOf, readWord } from "@/components/panels/ScanWide";
import { ago, compact, dir, num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * One name, read top to bottom in the order you would act on it: what the
 * setup is and where the entry sits, why it ranks where it does, the levels
 * around price, and then what could move it that the chart does not show —
 * earnings, filings, headlines.
 *
 * THE LADDER IS IN PRICE ORDER, with every level measured from the last print
 * in ten-minute ATRs, because "0.3 ATR above the PMH" is the sentence the
 * retest trade is made of and "$0.41 above" is not — the same forty cents is a
 * retest on one name and noise on another.
 */

export const sideHue = (s: Side) => (s === "long" ? "text-call-fig" : "text-put-fig");

export const levelGlyph = (k: "forming") => (k === "forming" ? "···" : "");

const LEVEL_FIELD = { PDH: "pdh", PDL: "pdl", PMH: "pmh", PML: "pml" } as const;

/** The front expiry's straddle as a band for the chart — what the options market prices for the move. */
export function emBand(r: ScanRow): { lo: number; hi: number; label: string } | null {
  const e = r.options?.ok ? r.options.em.find((x) => x.key === "front") : undefined;
  return e ? { lo: e.lo, hi: e.hi, label: `EM ±${e.pct.toFixed(1)}%` } : null;
}

/**
 * The setup column's words: the state, and the level or reference it is about.
 * `short` is the narrow form, for a column with a headline beside it.
 */
export function setupLabel(r: Pick<ScanRow, "setup" | "broken">, short = false): string {
  const { state, level, entry, side } = r.setup;
  switch (state) {
    case "retest":
      return `Retest ${level ?? entry?.kind ?? ""}`.trim();
    case "pullback": {
      // THROUGH THE LEVEL AND SHORT OF EXTENDED: THE TRADE IS THE RETEST. It read "Pulling
      // back to PDH" until 2026-11-11, which says which way price is travelling, and
      // nothing here measures that: a name running away from the level read the same.
      const where = `${side === "short" ? "Below" : "Above"} ${level ?? entry?.kind ?? "level"}`;
      return short ? `${where} · retest` : `${where} · entry is the retest`;
    }
    case "extended":
      return entry && (entry.kind === "VWAP" || entry.kind === "EMA8")
        ? `Extended → ${entry.kind === "EMA8" ? "8 EMA" : "VWAP"}`
        : `Extended past ${level ?? "level"}`;
    case "approaching":
      return `Near ${level ?? "a level"}`;
    case "failed":
      return `Failed ${level ?? ""}`.trim();
    case "forming":
      // Pre-market: the levels are not locked yet, so the row says what the
      // open has to do — hold beyond a level it has already broken, or break
      // one it has not. Read off `broken`, never inferred from the side.
      if (!level) return "Inside · plan";
      if (r.broken[LEVEL_FIELD[level]]) return `${side === "short" ? "Below" : "Above"} ${level} · plan`;
      return `Break of ${level} · plan`;
    case "chop":
      return "Inside — chop";
  }
}

export function ScanDetail({
  r,
  bench,
  now,
  stage = null,
}: {
  r: ScanRow;
  bench: "SPY" | "QQQ";
  now: number | null;
  /** Accepted for the callers; the Options card it served is gone. */
  tracked?: boolean;
  /** Which day of a multi-day move, for the score card's corner. */
  stage?: number | null;
}) {
  if (!r.ok) {
    return (
      <div className="px-6 py-6">
        <p className="text-[18px] font-semibold text-ink">{r.sym}</p>
        <p className="mt-2 text-[12px] text-ink-3">{r.error ?? "No data for this name yet."}</p>
      </div>
    );
  }
  const side = r.setup.side ?? r.score.side;
  return (
    <div className="qt-detail flex flex-col gap-2 p-2.5">
      <Figures r={r} bench={bench} />
      <KeyLevels r={r} />
      <Score r={r} side={side} stage={stage} />
      <NewsCard r={r} now={now} />
      {/* NO SETUP-IN-FULL, LADDER OR OPTIONS CARDS (owner, 2026-11-13: "get rid of the
          set up in full card, every level with its distance, and options"). The key levels,
          the score and the news above say what the setup is; the folds repeated them. */}
      <Fold id="catalysts" title="Earnings, filings and flags">
        <Catalysts r={r} />
      </Fold>
    </div>
  );
}

/** A card that opens on a click, remembered, so the rail stays short by default. */
function Fold({ id, title, right, children }: { id: string; title: string; right?: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = usePersisted<boolean>(`drawer.fold.${id}`, false, isBool);
  return (
    <section className={CARD}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="hit flex w-full items-baseline gap-2 text-left">
        <h3 className="qt-cap text-[10.5px] font-semibold text-ink-3">{title}</h3>
        <span className="ml-auto flex items-baseline gap-2 text-[11px] text-ink-3">
          {right}
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && <div className="mt-2.5">{children}</div>}
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Figures({ r, bench }: { r: ScanRow & { float_shares?: number | null; market_cap?: number | null }; bench: "SPY" | "QQQ" }) {
  const rs = r.rs[bench];
  const rs1h = r.rs_1h[bench];
  const vol = r.volume ?? r.premkt?.volume ?? null;
  const adv = vol != null && r.adv ? (vol / r.adv) * 100 : null;
  const pmOnly = r.volume == null && r.premkt?.volume != null;
  const ema = r.levels.ema8;
  const float = r.float_shares ?? r.short?.float_shares ?? null;
  const gap = gapOf(r);
  const atrPct = r.atr_d != null && r.last ? (r.atr_d / r.last) * 100 : null;
  const capWord = r.market_cap == null ? "" : r.market_cap >= 2e11 ? "Mega cap" : r.market_cap >= 1e10 ? "Large cap" : r.market_cap >= 2e9 ? "Mid cap" : "Small cap";
  return (
    <div className={CARD}>
      <p className="qt-cap mb-3 flex items-baseline justify-between text-[10.5px] text-ink-3">
        <span className="flex items-center gap-1.5"><Glyph name="pulse" size={11} />Session snapshot</span>
        {r.sector && (
          <span className="normal-case" title="The name's sector SPDR against SPY today, in percentage points">
            {r.sector}{" "}
            <span className={cn("fig", dir(r.sector_rs))}>
              {r.sector_rs != null ? `${r.sector_rs >= 0 ? "+" : ""}${r.sector_rs.toFixed(2)}` : "—"}
            </span>{" "}
            vs SPY
          </span>
        )}
      </p>
      <div className="grid grid-cols-3 gap-x-3 gap-y-3">
        <Fig label="RVol" sub="vs usual" title="Regular-session volume to now against the same time of day on the prior sessions">
          <span className={cn("fig text-[14px]", (r.rvol ?? 0) >= 2 ? "text-flip-fig" : "text-ink")}>{r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}</span>
        </Fig>
        <Fig label={pmOnly ? "PM volume" : "Volume"} sub={adv != null ? `${Math.round(adv)}% ADV` : ""}>
          <span className="fig text-[14px] text-ink">{vol != null ? compact(vol) : "—"}</span>
        </Fig>
        <Fig label="8 EMA · 10m" sub={ema != null && r.last ? `px ${r.last >= ema ? "+" : ""}${(((r.last - ema) / ema) * 100).toFixed(1)}%` : ""}>
          <span className={cn("fig text-[14px]", ema != null && r.last != null ? (r.last >= ema ? "up" : "down") : "text-ink")}>{ema != null ? `$${num(ema)}` : "—"}</span>
        </Fig>
        <Fig label="Float" sub="shares">
          <span className="fig text-[14px] text-ink">{float != null ? compact(float) : "—"}</span>
        </Fig>
        <Fig label="Mkt cap" sub={capWord}>
          <span className="fig text-[14px] text-ink">{capShort(r.market_cap)}</span>
        </Fig>
        <Fig label="ATR (14d)" sub={r.range_used != null ? `${Math.round(r.range_used * 100)}% used` : atrPct != null ? `${atrPct.toFixed(1)}% of px` : ""} title="The daily ATR, and how much of it today's regular session has used. Past about 120% the day's fuel is mostly spent.">
          <span className={cn("fig text-[14px]", (r.range_used ?? 0) >= 1.2 ? "text-flip-fig" : "text-ink")}>{r.atr_d != null ? `$${num(r.atr_d)}` : "—"}</span>
        </Fig>
        <Fig label="Day range" sub="" title="Today's regular-session low to high">
          <span className="fig text-[12px] text-ink">{r.levels.day_lo != null && r.levels.day_hi != null ? `${num(r.levels.day_lo)}–${num(r.levels.day_hi)}` : "—"}</span>
        </Fig>
        <Fig label="Gap" sub="" title="The open against the previous close. Before the open, where the extended session stands against that close.">
          <span className={cn("fig text-[14px]", gap == null ? "text-ink-3" : dir(gap))}>{gap == null ? "—" : `${gap >= 0 ? "+" : ""}${gap.toFixed(2)}%`}</span>
        </Fig>
        <Fig label={`RS ${bench}`} sub={rs1h == null ? "" : `1h ${rs1h >= 0 ? "+" : ""}${rs1h.toFixed(2)}`} title={`Today · last hour (six ten-minute bars), each in ATRs, minus ${bench}'s`}>
          <span className={cn("fig text-[14px]", rs == null ? "text-ink-3" : dir(rs))}>{rs == null ? "—" : `${rs >= 0 ? "+" : ""}${rs.toFixed(2)}`}</span>
        </Fig>
      </div>
    </div>
  );
}

function Fig({ label, sub, title, children }: { label: string; sub?: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0" title={title}>
      <p className="qt-cap mb-1 truncate text-[9.5px] text-ink-3">{label}</p>
      <div className="flex items-baseline whitespace-nowrap">{children}</div>
      {sub ? <p className="fig mt-0.5 truncate text-[10.5px] text-ink-3">{sub}</p> : null}
    </div>
  );
}

/** The five levels the strategy trades, each with which side of it price is on. */
function KeyLevels({ r }: { r: ScanRow }) {
  const L = r.levels;
  const last = r.last;
  // Where the official level sits past the chart's bars, say so (see `offBars`).
  const official = (what: string, level: number | null, bars: number | null | undefined) =>
    offBars(level, bars)
      ? `The official day's ${what}. The 5-minute bars reach ${num(bars)}: they miss the opening prints, so the candles stop short of this line.`
      : undefined;
  const pmSrc = pmSource(r);
  const rows: Array<{ key: string; label: React.ReactNode; v: number | null; forming?: boolean; note?: string; mark?: string }> = [
    { key: "pdh", label: "PDH", v: L.pdh, note: official("high", L.pdh, L.pdh_bars), mark: "official" },
    { key: "pmh", label: "PMH", v: L.pmh, forming: !L.pm_done, note: pmPastBars("high", L.pmh, L.pmh_bars, pmSrc), mark: "wider" },
    { key: "ema", label: <>8 EMA <span className="text-ink-3">10m</span></>, v: L.ema8 },
    { key: "pml", label: "PML", v: L.pml, forming: !L.pm_done, note: pmPastBars("low", L.pml, L.pml_bars, pmSrc), mark: "wider" },
    { key: "pdl", label: "PDL", v: L.pdl, note: official("low", L.pdl, L.pdl_bars), mark: "official" },
  ];
  const span = L.pdh != null && L.pdl != null ? L.pdh - L.pdl : 0;
  const pos = span > 0 && last != null && L.pdl != null ? Math.max(0, Math.min(1, (last - L.pdl) / span)) : null;
  return (
    <section className={CARD}>
      <p className="qt-cap mb-2.5 flex items-baseline justify-between text-[10.5px] text-ink-3">
        <span className="flex items-center gap-1.5"><Glyph name="tape" size={11} />Key levels</span>
        <span className="normal-case">Live state</span>
      </p>
      <ul className="flex flex-col">
        {rows.map((x) => {
          const above = x.v != null && last != null && last >= x.v;
          return (
            <li key={x.key} title={x.note} className="grid grid-cols-[92px_minmax(0,1fr)_auto] items-baseline gap-2 py-[3px]">
              <span className="text-[11.5px] text-ink-2">
                {x.label}
                {x.note && <span className="qt-cap ml-1.5 text-[9px] text-ink-3">{x.mark ?? "official"}</span>}
              </span>
              <span className="fig text-[13px] text-ink">{x.v != null ? `$${num(x.v)}` : "—"}</span>
              <span className={cn("qt-cap text-[9.5px]", x.v == null ? "text-ink-3" : x.forming ? "text-ink-3" : above ? "text-call-fig" : "text-put-fig")}>
                {x.v == null ? "" : x.forming ? "Forming" : above ? "Above" : "Below"}
              </span>
            </li>
          );
        })}
      </ul>
      {pos != null && (
        <>
          <div className="relative mt-3 h-[3px] rounded-full bg-[var(--qt-track,var(--ring))]">
            <span className="absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-desk-macro" style={{ left: `${pos * 100}%` }} />
          </div>
          <p className="fig mt-1.5 flex justify-between text-[11px] text-ink-3">
            <span>PDL ${num(L.pdl)}</span>
            <span>PDH ${num(L.pdh)}</span>
          </p>
        </>
      )}
    </section>
  );
}


/* -------------------------------------------------------------------------- */

/**
 * THE SCORE AS THE SCREENSHOTS HAVE IT: the number, a bar, and a tick or a cross for
 * each thing that earned it or cost it. The points stay at the end of each line, and
 * the setup's own words sit under them, because the number on its own says nothing.
 */
function Score({ r, side, stage }: { r: ScanRow; side: Side | null; stage: number | null }) {
  const v = r.score.total;
  const hue = v >= 65 ? "text-call-fig" : v >= 50 ? "text-flip-fig" : "text-ink-2";
  const bar = v >= 65 ? "bg-call-fig" : v >= 50 ? "bg-flip-fig" : "bg-ink-3";
  /*
   * ONE SCORE, THE LIST'S (owner, 2026-11-18: "i just need it intuitive"). Before the bell
   * the Scanner ranks how in play a name is, and this card shows that same number and
   * what earned it, one line a reason; from the bell, the setup score and its parts.
   */
  const inplay = r.score.kind === "inplay";
  const ip = inplay ? r.score.parts.find((p) => p.key === "inplay") : undefined;
  const reasons = ip?.note ? ip.note.split(" · ").filter(Boolean) : [];
  return (
    <section className={CARD}>
      <p className="qt-cap mb-2 flex items-baseline justify-between text-[10.5px] text-ink-3">
        <span className="flex items-center gap-1.5"><Glyph name="star" size={11} />Score</span>
        {inplay ? (
          <span
            className="normal-case"
            title="Before the bell the list ranks how in play a name is: the move in daily ATRs, volume against normal, a report or a major story, Day 2 or 3. From 09:30 it ranks by the setup score."
          >
            {stage != null && stage >= 2 ? `Day ${stage} of run · ` : ""}in play · until 09:30
          </span>
        ) : (
          <span className="normal-case" title="Each part is a fixed rule; together they order the list. Not a measured probability.">
            {stage != null && stage >= 2 ? `Day ${stage} of run · ` : ""}setup · heuristic rank
          </span>
        )}
      </p>
      <div className="flex items-baseline justify-between gap-3">
        <p className={cn("fig text-[24px] leading-none", hue)}>
          {v} <span className="text-[12px] text-ink-3">/100</span>
        </p>
        <p className={cn("text-right text-[12.5px] font-semibold", r.setup.state === "retest" && side ? sideHue(side) : "text-ink-2")}>
          {side === "long" ? "Long · " : side === "short" ? "Short · " : ""}
          {setupLabel(r)}
        </p>
      </div>
      <div className="relative mt-2 h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", bar)} style={{ width: `${Math.max(0, Math.min(100, v))}%` }} />
      </div>
      {inplay ? (
        <>
          <ul className="mt-2.5 flex flex-col gap-1">
            {(reasons.length ? reasons : ["not in play yet"]).map((why) => {
              const good = (ip?.pts ?? 0) > 0;
              return (
                <li key={why} className="flex items-baseline gap-1.5 text-[11.5px] leading-[1.35]">
                  <span aria-hidden className={cn("shrink-0 text-[11px]", good ? "text-call-fig" : "text-put-fig")}>{good ? "✓" : "✗"}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-2">{why.charAt(0).toUpperCase() + why.slice(1)}</span>
                </li>
              );
            })}
          </ul>
          {r.pre_ctx && <PreFigures c={r.pre_ctx} />}
        </>
      ) : (
        <ul className="mt-2.5 flex flex-col gap-1">
          {r.score.parts.map((p) => {
            const good = p.max > 0 && p.pts / p.max >= 0.5;
            return (
              <li key={p.key} className="flex items-baseline gap-1.5 text-[11.5px] leading-[1.35]" title={p.note}>
                <span aria-hidden className={cn("shrink-0 text-[11px]", good ? "text-call-fig" : "text-put-fig")}>{good ? "✓" : "✗"}</span>
                <span className="min-w-0 flex-1 truncate text-ink-2">
                  {p.label}
                  {p.note ? <span className="text-ink-3"> — {p.note}</span> : null}
                </span>
                <span className={cn("fig shrink-0 text-[11px]", p.pts < 0 ? "text-flip-fig" : "text-ink-3")}>{p.max > 0 ? `${Math.round(p.pts)}/${p.max}` : Math.round(p.pts)}</span>
              </li>
            );
          })}
        </ul>
      )}
      {/* Why the list holds a name lower than its score (scanscore.rvol_gate, 2026-11-13). */}
      {r.score.gated && <p className="mt-2 text-[11.5px] leading-[1.4] text-flip-fig">{r.score.gated}</p>}
      {r.setup.note && <p className="mt-2.5 border-t border-ring/60 pt-2 text-[12px] leading-[1.45] text-ink-2">{r.setup.note}</p>}
      {/* THE RECORD LINE (owner, 2026-10-23: "as high probability as
          possible"): what logged signals of this kind, side and band did —
          the only probability the rank can honestly show, with its sample. */}
      {r.record && (
        <p className="mt-3 border-t border-ring/60 pt-2 text-[11.5px] leading-[1.5] text-ink-3">
          <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Signals like this</span>
          <span className="text-ink-2">
            ({r.record.kind}) {r.record.side}s scored {r.record.band}
          </span>
          {" · "}
          <span className="fig text-ink">{r.record.win_1r != null ? `${Math.round(r.record.win_1r * 100)}%` : "—"}</span> reached +1R ·
          held to the close with the stop kept, <span className={cn("fig", (r.record.held_r ?? 0) >= 0 ? "text-ink" : "text-put-fig")}>
            {r.record.held_r != null ? `${r.record.held_r >= 0 ? "+" : ""}${r.record.held_r.toFixed(1)} R` : "—"}
          </span>{" "}
          · <span className="fig">{r.record.n}</span> signals over{" "}
          <span className="fig">{r.record.sessions ?? "—"}</span> sessions
          {r.record.small && <span className="block text-ink-3">Small sample: a hint, not a rate, until there are 30.</span>}
        </p>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * THE OFFICIAL DAY'S LEVEL, WHEN THE CHART'S BARS STOP SHORT OF IT. PDH and PDL are
 * the daily bar's; the 5-minute bars the candles are drawn from leave out the opening
 * prints, so on some days the line sits past every candle (AVGO, 6 Nov 2026: 311.52
 * against bars that reach 306.20). The row says so rather than leave the reader
 * wondering which is wrong.
 */
function offBars(official: number | null, bars: number | null | undefined): bars is number {
  return official != null && bars != null && Math.abs(official - bars) > Math.max(0.05, official * 0.0005);
}

/**
 * THE PRE-MARKET LEVEL, WHEN THE CANDLES STOP SHORT OF IT. PMH and PML take whichever
 * of the 5-minute bars and a second read reaches further (server scan.technicals). On
 * 11 Nov 2026 Yahoo had no bar before 05:20 ET for any Nasdaq-listed name, so the
 * line sat well past every candle (NVDA's low 172.66 against bars that began at
 * 177.02). The row says which read the level is from, and that the bars are short,
 * so a line with no candle near it is not taken for a mistake.
 */
function pmSource(r: ScanRow): string {
  return r.premkt?.source === "screener" ? "TradingView's screener (fifteen minutes behind)" : "Nasdaq's pre-market read";
}

function pmPastBars(what: "high" | "low", level: number | null, bars: number | null | undefined, src: string): string | undefined {
  // An older collector sends no bars figure: nothing to compare, nothing to say.
  if (level == null || bars === undefined) return undefined;
  if (bars === null) return `The pre-market ${what} from ${src}. Yahoo has no pre-market bars for this name yet today, so no candle reaches this line.`;
  return offBars(level, bars)
    ? `The pre-market ${what} from ${src}. Yahoo's 5-minute bars reach ${num(bars)}: they are missing part of today's pre-market, so the candles stop short of this line.`
    : undefined;
}

/* -------------------------------------------------------------------------- */

const KIND_LABEL: Record<ScanRow["news"][number]["kind"], string> = {
  rating: "Rating",
  earnings: "Earnings",
  filing: "Filing",
  news: "News",
};

/**
 * BEFORE THE BELL, FOUR FIGURES SHOWN AND NOT SCORED (owner, 2026-11-18: "the purpose of the
 * scoring is to show potential strong stocks where the break and retest will hold and continue
 * trending (both bearish or bullish) with momentum"). Each is a reason a move might keep going:
 * the stock's own push beyond the market's, volume unusual for it, a story behind it, and a gap
 * that holds into the open. The pre-market record holds them against what the names then did
 * (server premarket_record.py), and one earns points only where it separates on both sides.
 */
function PreFigures({ c }: { c: PreContext }) {
  const arrow = (x: number) => (x > 0 ? "▲ " : x < 0 ? "▼ " : "");
  const own =
    c.own != null
      ? `${arrow(c.own)}${Math.abs(c.own).toFixed(2)} ATR after SPY${c.spy != null ? ` (${arrow(c.spy)}${Math.abs(c.spy).toFixed(2)})` : ""}`
      : null;
  const vol = c.rvol != null ? `${c.rvol.toFixed(1)}× its usual pre-market${c.rvol_est ? " (estimate)" : ""}` : null;
  const k = c.catalyst;
  const size = k.size === "big" ? "Big" : k.size === "ordinary" ? "Ordinary" : k.size === "unclear" ? "Unclear" : null;
  const cat =
    size || k.direction
      ? `${[size, k.direction ? DIRECTION_WORD[k.direction] : null].filter(Boolean).join(" · ")}${k.line ? `: ${k.line}` : ""}`
      : k.report
        ? k.report.charAt(0).toUpperCase() + k.report.slice(1)
        : k.tag && k.major
          ? `${k.tag} story, not read yet`
          : "No fresh story";
  const rows: [string, string | null][] = [
    ["Own move", own],
    ["Volume", vol],
    ["Catalyst", cat],
    ["Hold", c.hold_word],
  ];
  return (
    <div className="mt-2.5 border-t border-ring/60 pt-2">
      <p
        className="qt-cap mb-1 text-[9.5px] text-ink-3"
        title="Shown and recorded, not scored: each is held against whether the names' retests then held and trended, and earns points only if it separates on both longs and shorts."
      >
        Not scored yet
      </p>
      <ul className="flex flex-col gap-0.5">
        {rows.map(([label, v]) => (
          <li key={label} className="flex items-baseline gap-2 text-[11.5px] leading-[1.35]">
            <span className="w-[62px] shrink-0 text-ink-3">{label}</span>
            <span className="min-w-0 flex-1 truncate text-ink-2" title={v ?? undefined}>
              {v ?? "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The news card: the most important story first if it is not in the list, then by day. */
function NewsCard({ r, now }: { r: ScanRow; now: number | null }) {
  const inList = r.catalyst != null && r.news.some((n) => n.title === r.catalyst?.title);
  return (
    <section className={CARD}>
      <p className="qt-cap mb-2 flex items-baseline justify-between text-[10.5px] text-ink-3">
        <span className="flex items-center gap-1.5"><Glyph name="clock" size={11} />News</span>
        <span className="fig normal-case">{r.news.length} in 3d</span>
      </p>
      {r.news_read && readWord(r.news_read) && <ModelRead read={r.news_read} />}
      {r.catalyst && !inList && <TopStory c={r.catalyst} />}
      {r.news.length === 0 ? <p className="text-[12px] text-ink-3">No headlines found for this name.</p> : <Headlines news={r.news} now={now} top={r.catalyst} />}
    </section>
  );
}

/**
 * WHAT THE MODEL MADE OF THE STORY THE SCORE COUNTED (owner, 2026-11-14: "does it take
 * into consideration the content of the news not just the heading?"). The score grades a
 * headline by rule, which says what a story is and not how big; the model reads the
 * headline, the feed's summary and the report's figures once and says big or ordinary
 * in a line (server newsread.py). Context only: it earns no points until the record can
 * show that big stories run further. No colour: how big is not which way.
 */
function ModelRead({ read }: { read: NewsRead }) {
  const size = read.size === "big" ? "Big" : read.size === "ordinary" ? "Ordinary" : "Unclear";
  /*
   * AND WHICH WAY (owner, 2026-11-18: "do what you recommend to make our scanner more
   * accurate"). The model reads the story's own text where TradingView carries it, and
   * says which way it pushes the name; that replaces the headline's words in the "reads
   * against" flag. Coloured as the sides are; still no points.
   */
  const way = read.direction;
  const wayHue =
    way === "bullish" ? "border-call-fig/60 text-call-fig" : way === "bearish" ? "border-put-fig/60 text-put-fig" : way === "mixed" ? "border-flip-fig/60 text-flip-fig" : "border-ring text-ink-3";
  return (
    <div
      className="mb-3 rounded-[3px] border border-ring-2 p-2.5"
      title={`A model's read of ${read.text ? "the story's text" : "the headline"}${read.headline ? `: "${read.headline}"` : ""}. Its direction decides the "reads against" flag; it earns no points.`}
    >
      <span className="qt-cap text-[9.5px] text-ink-2">Model&apos;s read</span>
      <span className={cn("qt-cap ml-2 rounded-[2px] border px-1 text-[9.5px] leading-[14px]", read.size === "big" ? "border-ring-2 text-ink" : "border-ring text-ink-3")}>{size}</span>
      {way && (
        <span className={cn("qt-cap ml-1.5 rounded-[2px] border px-1 text-[9.5px] leading-[14px]", wayHue)}>
          {way === "bullish" ? "▲ " : way === "bearish" ? "▼ " : ""}
          {DIRECTION_WORD[way]}
        </span>
      )}
      <span className="ml-2 text-[10.5px] text-ink-3">{read.text ? "from the story" : "headline only"}</span>
      {read.line && <span className="mt-1 block text-[12.5px] leading-[1.4] text-ink">{read.line}</span>}
    </div>
  );
}

function Catalysts({ r }: { r: ScanRow }) {
  const e = r.earnings;
  return (
    <div>
      <div className="flex flex-col gap-1.5">
        <p className="text-[12px] text-ink-2">
          <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Earnings</span>
          {e ? (
            <>
              <span className="text-ink">{earnDay(e.date, e.days)}</span>{" "}
              <span className="text-ink-3">
                {e.when === "pre" ? "before the open" : e.when === "after" ? "after the close" : "time unconfirmed"}
              </span>
              {e.eps_actual ? (
                <span className="fig ml-2">
                  EPS {e.eps_actual} vs {e.eps_forecast ?? "—"}e
                  {e.surprise_pct != null && (
                    <span className={cn("ml-1", dir(e.surprise_pct))}>
                      ({e.surprise_pct >= 0 ? "+" : ""}
                      {e.surprise_pct.toFixed(1)}%)
                    </span>
                  )}
                </span>
              ) : e.eps_forecast ? (
                <span className="fig ml-2 text-ink-3">est {e.eps_forecast}</span>
              ) : null}
            </>
          ) : (
            <span className="text-ink-3">none in the window the calendar covers</span>
          )}
        </p>
        {/* Short interest (sources/shortint): the squeeze a short can meet
            that has nothing to do with the level. Amber past 15% of the float. */}
        {r.short?.pct_float != null && (
          <p className="text-[12px] text-ink-2">
            <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Short interest</span>
            <span className={cn("fig", r.short.pct_float >= 15 ? "text-flip-fig" : "text-ink")}>
              {r.short.pct_float.toFixed(1)}%
            </span>{" "}
            of the float
            {r.short.days_to_cover != null && (
              <>
                {" "}· <span className="fig">{r.short.days_to_cover.toFixed(1)}</span> days to cover
              </>
            )}
            {r.short.as_of && <span className="text-ink-3"> · as of {r.short.as_of}</span>}
          </p>
        )}
        {r.peers && r.peers.length > 0 && (
          <p className="text-[12px] text-ink-2">
            <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Sector peers</span>
            {r.peers.map((p, i) => (
              <span key={`${p.sym}-${p.date}`}>
                {i > 0 && " · "}
                <span className="font-semibold text-ink">{p.sym}</span>{" "}
                <span className="text-ink-3">
                  {earnDay(p.date, p.days).split(" · ")[0]}
                  {p.when === "pre" ? " BMO" : p.when === "after" ? " AMC" : ""}
                </span>
              </span>
            ))}
            <span className="text-ink-3"> — a peer&apos;s report can move the whole sector</span>
          </p>
        )}
        {r.flags.length > 0 && (
          <ul className="flex flex-col gap-1">
            {r.flags.map((f, i) => (
              <li key={`${f.kind}-${i}`} className="flex items-baseline gap-2 text-[12px]">
                <span
                  aria-hidden
                  className={cn(
                    "mt-[5px] h-[6px] w-[6px] shrink-0 rounded-[1px]",
                    f.tone === "warn" ? "bg-flip-fig" : f.tone === "good" ? "bg-call-fig" : "bg-ink-4",
                  )}
                />
                <span className="text-ink-2">{f.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {r.filings.length > 0 && (
        <div className="mt-3.5">
          <p className="qt-cap mb-1.5 text-[10.5px] text-ink-3">SEC filings · last 3 days</p>
          <ul className="flex flex-col">
            {r.filings.map((f) => (
              <li key={`${f.form}-${f.filed}-${f.url}`}>
                <a
                  href={f.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="hit grid grid-cols-[56px_92px_minmax(0,1fr)] items-baseline gap-2 py-[3px] text-[12px]"
                >
                  <span className="fig font-semibold text-ink">{f.form}</span>
                  <span className="fig text-ink-3">{filedAt(f.filed)}</span>
                  <span className="truncate text-ink-2">{f.desc}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

    </div>
  );
}

/** The most important story of the last day, above the list it was picked from. */
function TopStory({ c }: { c: Catalyst }) {
  return (
    <a href={c.url} target="_blank" rel="noreferrer noopener" className="hit mb-3 block rounded-[3px] border border-ring-2 p-2.5" title={c.provider}>
      <span className="qt-cap text-[9.5px] text-ink-2">{c.tag}</span>
      <span className="fig ml-2 text-[10.5px] text-ink-3">{c.age_min < 60 ? `${Math.round(c.age_min)}m` : `${Math.round(c.age_min / 60)}h`} ago</span>
      <span className="mt-1 block text-[13px] leading-[1.4] text-ink">{c.title}</span>
    </a>
  );
}

const HEADLINES_SHOWN = 6;
const ET_HM = new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false });
const ET_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const ET_DAY_NAME = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" });

/** Headlines newest first, under their New York day, the rest behind a button. */
function Headlines({ news, now, top }: { news: ScanRow["news"]; now: number | null; top?: Catalyst | null }) {
  const [all, setAll] = useState(false);
  const shown = all ? news : news.slice(0, HEADLINES_SHOWN);
  const today = now === null ? null : ET_DATE.format(new Date(now));
  let last: string | null = null;
  return (
    <>
      <ul className="flex flex-col">
        {shown.map((n, i) => {
          const when = n.utc ? new Date(n.utc) : null;
          const day = when ? ET_DATE.format(when) : null;
          const head = day !== null && day !== last;
          last = day ?? last;
          return (
            <li key={`${n.url}-${i}`}>
              {head && when && (
                <p className="qt-cap mt-2 border-t border-ring/60 pt-2 text-[10px] text-ink-3">
                  {day === today ? "Today" : ET_DAY_NAME.format(when)}
                </p>
              )}
              <a href={n.url} target="_blank" rel="noreferrer noopener" className="hit flex flex-col gap-0.5 py-1.5" title={n.publisher}>
                <span className="flex items-baseline gap-2 text-[11px] text-ink-3">
                  {when && <span className="fig text-[12px] text-ink">{ET_HM.format(when)}</span>}
                  <span className="fig">{ago(n.utc, now)}</span>
                  {top?.title === n.title ? (
                    <span className="qt-cap rounded-[3px] border border-desk-markets/50 bg-desk-markets/10 px-1 text-[9px] leading-[13px] text-desk-markets">{top.tag}</span>
                  ) : (
                    n.kind !== "news" && <span className={cn("qt-cap text-[9.5px]", n.kind === "rating" ? "text-flip-fig" : "text-ink-3")}>{KIND_LABEL[n.kind]}</span>
                  )}
                </span>
                <span className="text-[12.5px] leading-[1.4] text-ink">{n.title}</span>
              </a>
            </li>
          );
        })}
      </ul>
      {/* Both ways (owner, 2026-11-13: "show more ... but then no option to collapse it
          back"): the same button folds the list back to the first few. */}
      {news.length > HEADLINES_SHOWN && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          aria-expanded={all}
          className="hit mt-1.5 w-full rounded-[3px] border border-ring-2 py-1 text-[11.5px] text-ink-3 hover:text-ink"
        >
          {all ? "Show less" : `Show ${news.length - HEADLINES_SHOWN} more`}
        </button>
      )}
    </>
  );
}

/** EDGAR's acceptance time → "Oct 12 16:05", in New York time like everything else here. */
function filedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" });
  const t = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" });
  return `${day} ${t}`;
}

/** "Today", "Tomorrow", "Thu Oct 16 · in 3d", "Mon Oct 12 · 1d ago". */
function earnDay(iso: string, days: number): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  const d = new Date(`${iso}T12:00:00Z`);
  const name = Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  return days > 0 ? `${name} · in ${days}d` : `${name} · ${-days}d ago`;
}
