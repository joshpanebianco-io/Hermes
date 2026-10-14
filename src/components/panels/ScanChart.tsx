"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChartTf, ScanBars } from "@/types/scanner";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * One name's chart, drawn the way LE_Model.pine draws it: the
 * candles, the four levels (PDH / PDL solid, PMH / PML dashed, as the script's
 * defaults set them), the 8 EMA wave, VWAP, and the signals where they fired —
 * so the setup the row describes can be SEEN before switching to TradingView
 * (owner instruction, 2026-10-13: "fix everything you recommend" — the review's
 * mini chart).
 *
 * SVG, NOT A CHART LIBRARY. A hundred-odd candles and a handful of lines are
 * well inside what plain SVG draws without effort, and a canvas library would
 * be the first heavyweight dependency this front end has taken on, for one
 * panel.
 *
 * QUIET'S RULES HOLD HERE TOO: hue only on what carries a side — the candles,
 * the level lines, the signals — and the wave tinted by the row's level state
 * the way the Pine colours it, faintly. VWAP is ink, not amber: amber means
 * the gamma flip on this terminal, and VWAP is not that.
 *
 * Extended hours are shaded and their candles dimmed, because the strategy is
 * a regular-session one and the pre-market is where its levels come from, not
 * where it trades.
 *
 * TIMEFRAMES (owner instruction, 2026-10-14: "a toggle for the time frames on
 * the chart — 1m 3m 5m 10m D"). Ten minutes is the default and the one the
 * script's signals are read on; the others are views of the same tape, with
 * each signal marked on the bar that holds the ten-minute close confirming
 * it. The choice is remembered for every name.
 */

const H = 280;
const PAD = { top: 22, right: 78, bottom: 20, left: 4 };
/** Narrowest a candle step may get before the oldest bars are dropped instead. */
const MIN_STEP = 5;

const TFS: readonly ChartTf[] = ["1m", "3m", "5m", "10m", "D"];
const TF_NAME: Record<ChartTf, string> = {
  "1m": "one-minute",
  "3m": "three-minute",
  "5m": "five-minute",
  "10m": "ten-minute",
  D: "daily",
};
/** A daily chart changes once a session; the intraday ones as fast as their bars. */
const POLL_SEC: Record<ChartTf, number> = { "1m": 20, "3m": 30, "5m": 30, "10m": 30, D: 120 };
/** Minutes between time labels — kept 44px apart on screen regardless. */
const TICK_MIN: Record<Exclude<ChartTf, "D">, number> = { "1m": 15, "3m": 30, "5m": 60, "10m": 60 };

const ET_HM = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const hm = (t: number) => ET_HM.format(new Date(t * 1000));
const ET_DAY = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const ET_WDAY = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" });
const md = (t: number) => ET_DAY.format(new Date(t * 1000));
const wd = (t: number) => ET_WDAY.format(new Date(t * 1000));

export function ScanChart({
  sym,
  state,
  em = null,
}: {
  sym: string;
  state: -2 | -1 | 0 | 1 | 2;
  /** The front expiry's expected move, drawn as a dotted band. */
  em?: { lo: number; hi: number; label: string } | null;
}) {
  const [tf, setTf] = usePersisted<ChartTf>("scan.tf", "10m", oneOf(...TFS));
  const [data, setData] = useState<ScanBars | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [w, setW] = useState(0);
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/bars/${encodeURIComponent(sym)}?tf=${tf}`, { cache: "no-store" });
      const d = (await r.json()) as ScanBars & { offline?: { reason: string } };
      if (mine !== seq.current) return;
      setData(d);
      setErr(d.offline ? d.offline.reason : d.ok ? null : (d.error ?? "no bars"));
    } catch (e) {
      if (mine === seq.current) setErr(e instanceof Error ? e.message : "request failed");
    }
  }, [sym, tf]);

  // A new name or timeframe starts blank rather than showing the last one's
  // candles under its ticker.
  useEffect(() => {
    setData(null);
    setErr(null);
    setHover(null);
    void load();
    const id = setInterval(load, POLL_SEC[tf] * 1000);
    return () => clearInterval(id);
  }, [load, tf]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const emLo = em?.lo ?? null;
  const emHi = em?.hi ?? null;
  const emLabel = em?.label ?? "";
  const g = useMemo(
    () =>
      data?.ok && w > 0
        ? geometry(data, w, state, emLo != null && emHi != null ? { lo: emLo, hi: emHi, label: emLabel } : null, data.tf ?? "10m")
        : null,
    [data, w, state, emLo, emHi, emLabel],
  );

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!g) return;
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    const i = Math.round((x - g.x0) / g.step);
    setHover(i >= 0 && i < g.n ? i : null);
  };

  return (
    <div className="w-full">
      <div className="flex items-center gap-3 pb-1.5">
        <span className="qt-cap text-[10.5px] text-ink-3">Chart</span>
        {tf !== "10m" && tf !== "D" && (
          <span className="min-w-0 truncate text-[11px] text-ink-3" title="LE_Model's (L) and (E) are read on ten-minute bars; on this view each sits on the bar holding the ten-minute close that confirmed it">
            signals read on 10m
          </span>
        )}
        <span className="seg ml-auto shrink-0" role="group" aria-label="Chart timeframe">
          {TFS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTf(t)}
              aria-pressed={tf === t}
              title={`${TF_NAME[t]} bars`}
              {...segItem(tf === t, { className: "fig min-w-[30px] justify-center" })}
            >
              {t}
            </button>
          ))}
        </span>
      </div>
    <div ref={box} className="relative w-full" style={{ height: H }}>
      {!g ? (
        err ? (
          <p className="absolute inset-0 flex items-center justify-center text-[12px] text-ink-3">No chart — {err}</p>
        ) : (
          <HelmLoader label={`Loading the ${tf} chart`} size={40} className="absolute inset-0" />
        )
      ) : (
        <svg
          width={w}
          height={H}
          className="block select-none"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`${sym} ${TF_NAME[g.tf]} chart with its levels`}
        >
          {/* extended hours, shaded */}
          {g.shades.map((s, i) => (
            <rect key={i} x={s.x} y={PAD.top} width={s.w} height={H - PAD.top - PAD.bottom} fill="var(--surface-2)" opacity={0.55} />
          ))}
          {/* the regular-session open */}
          {g.opens.map((x, i) => (
            <line key={i} x1={x} x2={x} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--ring-2)" strokeWidth={1} />
          ))}
          {/* the 8 EMA wave, tinted by the level state as the Pine tints it */}
          {g.wave && <path d={g.wave} fill={g.waveHue} opacity={0.16} />}
          {g.ema8 && <path d={g.ema8} fill="none" stroke={g.waveHue} strokeWidth={1} opacity={0.7} />}
          {g.ema10 && <path d={g.ema10} fill="none" stroke={g.waveHue} strokeWidth={1} opacity={0.45} />}
          {/* VWAP */}
          {g.vwap && <path d={g.vwap} fill="none" stroke="var(--ink-2)" strokeWidth={1} strokeDasharray="4 3" opacity={0.85} />}
          {/* the straddle's expected move */}
          {g.em.map((e) => (
            <line key={e.key} x1={g.x0} x2={w - PAD.right} y1={e.y} y2={e.y} stroke="var(--ink-3)" strokeWidth={1} strokeDasharray="2 3" opacity={0.9} />
          ))}
          {/* levels */}
          {g.levels.map((l) => (
            <line
              key={l.key}
              x1={g.x0}
              x2={w - PAD.right}
              y1={l.y}
              y2={l.y}
              stroke={l.hue}
              strokeWidth={1}
              strokeDasharray={l.dashed ? "5 4" : undefined}
              opacity={l.faint ? 0.5 : 0.8}
            />
          ))}
          {/* earlier sessions' levels, each over its own day */}
          {g.hist.map((h) => (
            <g key={h.key} opacity={0.55}>
              <title>{h.title}</title>
              <line x1={h.x1} x2={h.x2} y1={h.y} y2={h.y} stroke={h.hue} strokeWidth={1} strokeDasharray={h.dashed ? "5 4" : undefined} />
              <text x={h.lx} y={h.y - 3} textAnchor={h.anchor} className="fig" fontSize={9} fill={h.hue}>
                {h.label}
              </text>
            </g>
          ))}
          {/* candles */}
          {g.candles.map((c, i) => (
            <g key={i} opacity={c.ext ? 0.5 : 1}>
              <line x1={c.x} x2={c.x} y1={c.yh} y2={c.yl} stroke={c.hue} strokeWidth={1} />
              <rect x={c.x - g.body / 2} y={Math.min(c.yo, c.yc)} width={g.body} height={Math.max(1, Math.abs(c.yc - c.yo))} fill={c.hue} />
            </g>
          ))}
          {/* signals */}
          {g.marks.map((m, i) => (
            <g key={i}>
              <path d={m.d} fill={m.hollow ? "none" : m.hue} stroke={m.hue} strokeWidth={1} />
              <text x={m.x} y={m.ty} textAnchor="middle" className="fig" fontSize={9.5} fill={m.hue}>
                {m.label}
              </text>
            </g>
          ))}
          {/* last price */}
          <line x1={g.x0} x2={w - PAD.right} y1={g.lastY} y2={g.lastY} stroke="var(--ink-3)" strokeWidth={1} strokeDasharray="1 3" />
          {/* right-hand labels, pushed apart so they never print over each other */}
          {g.labels.map((l) => (
            <g key={l.key}>
              {l.spot && <rect x={w - PAD.right + 2} y={l.y - 7} width={PAD.right - 4} height={14} fill="var(--surface-3)" />}
              <text x={w - PAD.right + 6} y={l.y + 3.5} className="fig" fontSize={10} fill={l.hue}>
                {l.title && <title>{l.title}</title>}
                {l.text}
              </text>
            </g>
          ))}
          {/* hour ticks, ET */}
          {g.ticks.map((t) => (
            <text key={t.x} x={t.x} y={H - 5} textAnchor="middle" className="fig" fontSize={9.5} fill="var(--ink-3)">
              {t.text}
            </text>
          ))}
          {/* hover */}
          {hover !== null && g.candles[hover] && (
            <line x1={g.candles[hover].x} x2={g.candles[hover].x} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--ink-4)" strokeWidth={1} />
          )}
        </svg>
      )}
      {g && (
        <p className={cn("fig pointer-events-none absolute top-0 left-1 text-[10.5px] text-ink-3")}>
          {hover !== null && g.bars[hover] ? readout(g, hover) : `${g.tf} · ${g.tf === "D" ? "regular session" : "ET"} · ${g.n} bars`}
        </p>
      )}
    </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

interface Geo {
  tf: ChartTf;
  n: number;
  x0: number;
  step: number;
  body: number;
  bars: ScanBars["bars"];
  vwapAt: Array<number | null>;
  ema8At: Array<number | null>;
  candles: Array<{ x: number; yo: number; yc: number; yh: number; yl: number; hue: string; ext: boolean }>;
  shades: Array<{ x: number; w: number }>;
  opens: number[];
  wave: string | null;
  ema8: string | null;
  ema10: string | null;
  waveHue: string;
  vwap: string | null;
  levels: Array<{ key: string; y: number; hue: string; dashed: boolean; faint?: boolean }>;
  hist: Array<{
    key: string;
    x1: number;
    x2: number;
    y: number;
    hue: string;
    dashed: boolean;
    label: string;
    lx: number;
    anchor: "start" | "end";
    title: string;
  }>;
  em: Array<{ key: string; y: number }>;
  labels: Array<{ key: string; y: number; text: string; hue: string; spot?: boolean; title?: string }>;
  marks: Array<{ d: string; x: number; ty: number; label: string; hue: string; hollow: boolean }>;
  ticks: Array<{ x: number; text: string }>;
  lastY: number;
}

function readout(g: Geo, i: number): string {
  const b = g.bars[i];
  const when = g.tf === "D" ? `${wd(b.t)} ${md(b.t)}` : hm(b.t);
  const parts = [when, `O ${num(b.o)}`, `H ${num(b.h)}`, `L ${num(b.l)}`, `C ${num(b.c)}`];
  const v = g.vwapAt[i];
  const e = g.ema8At[i];
  if (v != null) parts.push(`VWAP ${num(v)}`);
  if (e != null) parts.push(`8EMA ${num(e)}`);
  return parts.join("  ");
}

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function geometry(
  d: ScanBars,
  w: number,
  state: number,
  emBand: { lo: number; hi: number; label: string } | null,
  tf: ChartTf,
): Geo | null {
  const all = d.bars;
  if (all.length === 0) return null;
  const plotW = w - PAD.left - PAD.right;
  const maxBars = Math.max(10, Math.floor(plotW / MIN_STEP));

  // Start at today's pre-market (and six bars of the evening before it, for
  // context), or simply the most recent bars that fit — whichever is shorter.
  // The daily chart simply shows the most recent sessions that fit.
  const lastT = all[all.length - 1].t;
  const pre = [...d.sessions].reverse().find((s) => s.kind === "pre" && s.from <= lastT);
  let start = pre ? all.findIndex((b) => b.t >= pre.from) : -1;
  start = tf === "D" ? 0 : start < 0 ? Math.max(0, all.length - 60) : Math.max(0, start - 6);
  start = Math.max(start, all.length - maxBars);
  const bars = all.slice(start);
  const n = bars.length;
  const sl = <T,>(a: T[]) => a.slice(start, start + n);
  const ema8 = sl(d.ema8);
  const ema10 = sl(d.ema10);
  const vwap = sl(d.vwap);

  const step = plotW / Math.max(n, 1);
  const x0 = PAD.left + step / 2;
  const xAt = (i: number) => x0 + i * step;

  // The scale fits the bars and the lines over them; a level far off the
  // range is not allowed to crush the candles into a sliver — it gets an
  // edge label instead of a line.
  let lo = Math.min(...bars.map((b) => b.l));
  let hi = Math.max(...bars.map((b) => b.h));
  for (const v of [...ema8, ...ema10, ...vwap]) {
    if (v != null) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  const span0 = Math.max(hi - lo, hi * 0.002);
  const L = d.levels;
  /*
   * PMH / PML WHILE THEY FORM (owner, 2026-10-14: "ensure that the chart in
   * the scanner includes the pre market highs and lows"). They were hidden
   * until 09:30, when the pre-market is done — so the hours the levels are
   * made in showed none. Now they draw as they stand, fainter and marked
   * "·f" (forming), and become the day's lines at the bell.
   */
  const forming = !L.pm_done;
  const lvl: Array<{ key: string; v: number | null; hue: string; dashed: boolean; forming?: boolean }> = [
    { key: "PDH", v: L.pdh, hue: "var(--call-fig)", dashed: false },
    { key: "PMH", v: L.pmh, hue: "var(--call-fig)", dashed: true, forming },
    { key: "PML", v: L.pml, hue: "var(--put-fig)", dashed: true, forming },
    { key: "PDL", v: L.pdl, hue: "var(--put-fig)", dashed: false },
  ];
  // Earlier sessions' levels, each over its own regular hours — the Pine's
  // "keep previous days' levels" — where that session is on screen. Overnight
  // the chart shows yesterday; these are the levels yesterday traded against.
  const hist0 = (d.history ?? [])
    .map((h) => {
      const i0 = bars.findIndex((b) => b.t >= h.from);
      let i1 = -1;
      for (let i = n - 1; i >= 0; i--) {
        if (bars[i].t < h.to) {
          i1 = i;
          break;
        }
      }
      return { ...h, i0, i1 };
    })
    .filter((h) => h.i0 >= 0 && h.i1 >= h.i0);
  for (const v of [...lvl.map((l) => l.v), ...hist0.map((h) => h.v)]) {
    if (v != null && v > lo - span0 * 0.6 && v < hi + span0 * 0.6) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  const pad = (hi - lo) * 0.06 || hi * 0.001;
  lo -= pad;
  hi += pad;
  const top = PAD.top;
  const bot = H - PAD.bottom;
  const y = (v: number) => top + ((hi - v) / (hi - lo)) * (bot - top);
  const clampY = (v: number) => Math.max(top + 6, Math.min(bot - 6, y(v)));

  // A daily bar is the regular session by construction — nothing to shade.
  const inExt = (t: number) => {
    if (tf === "D") return false;
    const s = d.sessions.find((x) => t >= x.from && t < x.to);
    return !s || s.kind !== "rth";
  };

  const candles = bars.map((b, i) => ({
    x: xAt(i),
    yo: y(b.o),
    yc: y(b.c),
    yh: y(b.h),
    yl: y(b.l),
    hue: b.c >= b.o ? "var(--call-fig)" : "var(--put-fig)",
    ext: inExt(b.t),
  }));

  // Shaded runs of extended-hours bars, and a hairline at each 09:30.
  const shades: Geo["shades"] = [];
  const opens: number[] = [];
  let runStart: number | null = null;
  candles.forEach((c, i) => {
    if (c.ext && runStart === null) runStart = i;
    if (!c.ext && runStart !== null) {
      shades.push({ x: xAt(runStart) - step / 2, w: (i - runStart) * step });
      opens.push(xAt(i) - step / 2);
      runStart = null;
    }
  });
  if (runStart !== null) shades.push({ x: xAt(runStart) - step / 2, w: (n - runStart) * step });

  const line = (vals: Array<number | null>) => {
    let p = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      p += `${pen ? "L" : "M"}${xAt(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return p || null;
  };
  let wave: string | null = null;
  const idx = ema8.map((v, i) => (v != null && ema10[i] != null ? i : -1)).filter((i) => i >= 0);
  if (idx.length > 1) {
    const upper = idx.map((i) => `${xAt(i).toFixed(1)},${y(ema8[i] as number).toFixed(1)}`);
    const lower = [...idx].reverse().map((i) => `${xAt(i).toFixed(1)},${y(ema10[i] as number).toFixed(1)}`);
    wave = `M${upper.join("L")}L${lower.join("L")}Z`;
  }
  const waveHue = state > 0 ? "var(--call-fig)" : state < 0 ? "var(--put-fig)" : "var(--ink-3)";

  const levels: Geo["levels"] = [];
  const labels: Geo["labels"] = [];
  for (const l of lvl) {
    if (l.v == null) continue;
    const onScale = l.v >= lo && l.v <= hi;
    if (onScale) levels.push({ key: l.key, y: y(l.v), hue: l.hue, dashed: l.dashed, faint: l.forming });
    labels.push({
      key: l.key,
      y: clampY(l.v),
      text: `${l.key} ${num(l.v)}${l.forming ? " ·f" : ""}${onScale ? "" : l.v > hi ? " ↑" : " ↓"}`,
      hue: l.hue,
      title: l.forming ? `${l.key} so far — the pre-market is still forming it; final at 09:30 ET` : undefined,
    });
  }
  // The earlier sessions' segments: PDH / PDL named at their left end, PMH /
  // PML at their right, so a pair that sits close does not print its names
  // over each other.
  const hist: Geo["hist"] = [];
  for (const h of hist0) {
    if (h.v < lo || h.v > hi) continue;
    const pm = h.key === "PMH" || h.key === "PML";
    const x1 = xAt(h.i0) - step / 2;
    const x2 = xAt(h.i1) + step / 2;
    hist.push({
      key: `${h.day}-${h.key}`,
      x1,
      x2,
      y: y(h.v),
      hue: h.key === "PDH" || h.key === "PMH" ? "var(--call-fig)" : "var(--put-fig)",
      dashed: pm,
      label: h.key,
      lx: pm ? x2 - 2 : x1 + 2,
      anchor: pm ? "end" : "start",
      title: `${h.key} ${num(h.v)} — the ${h.day} session's level`,
    });
  }
  // The expected-move band: drawn where it falls on the scale, labelled once
  // (at its upper edge) so it reads as one band rather than two more levels.
  const em: Geo["em"] = [];
  if (emBand) {
    for (const [key, v] of [["emhi", emBand.hi], ["emlo", emBand.lo]] as const) {
      if (v >= lo && v <= hi) em.push({ key, y: y(v) });
    }
    labels.push({ key: "em", y: clampY(emBand.hi), text: emBand.label, hue: "var(--ink-3)" });
  }
  const lastV = bars[n - 1].c;
  const vLast = vwap[n - 1];
  if (vLast != null) labels.push({ key: "VWAP", y: clampY(vLast), text: `VWAP ${num(vLast)}`, hue: "var(--ink-2)" });
  labels.push({ key: "last", y: clampY(lastV), text: num(lastV), hue: "var(--ink)", spot: true });

  // Push labels apart, keeping the order price gives them.
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].y - labels[i - 1].y < 12) labels[i].y = labels[i - 1].y + 12;
  }
  const over = labels.length ? labels[labels.length - 1].y - (bot - 4) : 0;
  if (over > 0) for (const l of labels) l.y -= over;

  const tIndex = new Map(bars.map((b, i) => [b.t, i]));
  const marks: Geo["marks"] = [];
  for (const s of d.signals) {
    const i = tIndex.get(s.t);
    if (i === undefined) continue;
    const b = bars[i];
    const x = xAt(i);
    const long = s.side === "long";
    const hue = long ? "var(--call-fig)" : "var(--put-fig)";
    const yy = long ? y(b.l) + 5 : y(b.h) - 5;
    const dir = long ? 1 : -1;
    const tri = `M${x},${yy}L${x - 4},${yy + 6 * dir}L${x + 4},${yy + 6 * dir}Z`;
    const label = s.kind === "BO" ? "◆" : s.kind === "E_SETUP" ? "E" : s.kind;
    marks.push({ d: tri, x, ty: long ? yy + 16 : yy - 8, label, hue, hollow: s.kind === "E_SETUP" });
  }

  // An ET hour label wherever a bar opens on the hour, kept at least 44px
  // apart. Spacing is measured on screen, not counted in hours: the bars are
  // contiguous but time is not — 19:50 sits beside 04:00 across the night —
  // so two hour marks can land a candle apart.
  //
  // The interval follows the timeframe (every quarter-hour on 1m, half-hour on
  // 3m, the hour above); the daily chart labels the first session of each week.
  const ticks: Geo["ticks"] = [];
  let lastX = -Infinity;
  bars.forEach((b, i) => {
    const x = xAt(i);
    let text: string | null = null;
    if (tf === "D") {
      const prev = bars[i - 1];
      // A new week: this session's weekday comes before the last one's, or
      // more than three days have passed (a holiday Monday).
      if (!prev || b.t - prev.t > 3 * 86400 || DOW.indexOf(wd(b.t)) < DOW.indexOf(wd(prev.t))) text = md(b.t);
    } else {
      const t = hm(b.t);
      if (Number(t.slice(3)) % TICK_MIN[tf] === 0 && (TICK_MIN[tf] < 60 || t.endsWith(":00"))) text = t;
    }
    // Not so near the left edge that half the label is cut off.
    if (text && x >= 18 && x - lastX >= 44) {
      ticks.push({ x, text });
      lastX = x;
    }
  });

  return {
    tf,
    n,
    x0,
    step,
    body: Math.max(1, Math.min(9, step * 0.6)),
    bars,
    vwapAt: vwap,
    ema8At: ema8,
    candles,
    shades,
    opens,
    wave,
    ema8: line(ema8),
    ema10: line(ema10),
    waveHue,
    vwap: line(vwap),
    levels,
    hist,
    em,
    labels,
    marks,
    ticks,
    lastY: y(lastV),
  };
}
