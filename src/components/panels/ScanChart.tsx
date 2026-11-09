"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  TickMarkType,
  createChart,
  createSeriesMarkers,
  type AutoscaleInfo,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type IPriceLine,
  type IPrimitivePaneRenderer,
  type IPrimitivePaneView,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type ISeriesPrimitive,
  type LineData,
  type Logical,
  type MouseEventParams,
  type SeriesAttachedParameter,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import type { ChartTf, ScanBars, TickPayload } from "@/types/scanner";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { mergeTick, nextEma } from "@/lib/chartLive";

/**
 * One name's chart, drawn the way the Pine script draws it: the candles, the four
 * levels (PDH / PDL solid, PMH / PML dashed), the 8 EMA wave, VWAP and the signals
 * where they fired.
 *
 * LIGHTWEIGHT CHARTS, NOT SVG (owner, 2026-11-09). This was plain SVG, chosen when
 * it was a mini chart in a 500px pane: "a canvas library would be the first
 * heavyweight dependency this front end has taken on, for one panel". It is the
 * centre of the slide-out now, 1,200px wide, and the reader wants to drag it back
 * through the week and zoom a retest; and a last candle that moves on every trade
 * cannot mean rebuilding a few hundred SVG nodes every second. GEXYGEN's CandlePane
 * is where the ET formatters come from. The library's TV mark stays: its licence
 * requires crediting TradingView, and `attributionLogo` is how that is done.
 *
 * THE LIBRARY ONLY DRAWS. The data is still the collector's: the full series on a
 * slow poll for the EMAs, VWAP, volume and signals, and on top of it, every second,
 * the last trade from the stream (sources/stream.py) laid on the last candle
 * (lib/chartLive.ts). A chart with no stream is a chart on its slow poll.
 *
 * QUIET'S RULES HOLD HERE TOO: hue only on what carries a side (the candles, the
 * level lines, the signals) and the wave tinted by the row's level state, faintly.
 * VWAP is ink, not amber: amber means the gamma flip on this terminal.
 *
 * EXTENDED HOURS ARE SHADED AND THEIR CANDLES DIMMED, because the strategy is a
 * regular-session one and the pre-market is where its levels come from.
 *
 * WHAT THE LIBRARY DOES NOT DRAW goes in one primitive, `Overlays`: the shading,
 * the 09:30 hairlines, the wave's fill, earlier sessions' levels over their own
 * days. The levels off the scale are named in the corner, because a price line
 * off the top of the pane simply is not there.
 */

const TFS: readonly ChartTf[] = ["1m", "3m", "5m", "10m", "D"];
const STEP: Record<ChartTf, number> = { "1m": 60, "3m": 180, "5m": 300, "10m": 600, D: 86400 };
const TF_NAME: Record<ChartTf, string> = {
  "1m": "one-minute",
  "3m": "three-minute",
  "5m": "five-minute",
  "10m": "ten-minute",
  D: "daily",
};
/**
 * How often the whole series is read again, for what a trade cannot tell the
 * chart: the EMAs' history, VWAP, volume, new signals. The 1m and 3m views read a
 * one-minute download with a twenty-second cache, so asking faster buys nothing.
 */
const POLL_SEC: Record<ChartTf, number> = { "1m": 20, "3m": 20, "5m": 15, "10m": 15, D: 120 };
const IDLE_POLL_SEC = 60;
const TICK_MS = 1000;
const IDLE_TICK_MS = 5000;

const LAYERS = ["ema8", "ema200", "vwap", "pd", "pm", "vol"] as const;
type Layer = (typeof LAYERS)[number];
const LAYER_NAME: Record<Layer, string> = {
  ema8: "8 EMA",
  ema200: "200",
  vwap: "VWAP",
  pd: "PD",
  pm: "PM",
  vol: "Vol",
};
const LAYER_TITLE: Record<Layer, string> = {
  ema8: "The 8 EMA wave",
  ema200: "The 200 EMA",
  vwap: "VWAP, from 09:30",
  pd: "The previous day's high and low",
  pm: "The pre-market high and low",
  vol: "Volume",
};
const LAYER_DEFAULT: Layer[] = ["ema8", "ema200", "vwap", "pd", "pm", "vol"];

const ET_HM = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false });
const ET_DAY = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const ET_WDAY = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" });
const ET_YMD = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const hm = (t: number) => ET_HM.format(new Date(t * 1000));
const md = (t: number) => ET_DAY.format(new Date(t * 1000));
const wd = (t: number) => ET_WDAY.format(new Date(t * 1000));
const ymd = (t: number) => ET_YMD.format(new Date(t * 1000));

interface Palette {
  up: string;
  down: string;
  upDim: string;
  downDim: string;
  ink: string;
  ink2: string;
  ink3: string;
  ring: string;
  ring2: string;
  shade: string;
  grid: string;
}

function rgba(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})` : hex;
}

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  const up = v("--call-fig");
  const down = v("--put-fig");
  return {
    up,
    down,
    upDim: rgba(up, 0.5),
    downDim: rgba(down, 0.5),
    ink: v("--ink"),
    ink2: v("--ink-2"),
    ink3: v("--ink-3"),
    ring: v("--ring"),
    ring2: v("--ring-2"),
    shade: rgba(v("--surface-2"), 0.55),
    grid: rgba(v("--ring"), 0.45),
  };
}

/* -------------------------------------------------------------------------- */
/* What the library does not draw                                              */
/* -------------------------------------------------------------------------- */

interface Segment {
  i0: number;
  i1: number;
  v: number;
  hue: string;
  dashed: boolean;
  label: string;
  /** Named at its right end (PMH / PML) or left (PDH / PDL), so a close pair does not collide. */
  labelEnd: boolean;
}

interface OverlayData {
  shades: Array<{ from: number; to: number }>;
  opens: number[];
  shadeHue: string;
  openHue: string;
  wave: { upper: Array<number | null>; lower: Array<number | null>; hue: string } | null;
  segments: Segment[];
  font: string;
}

const NO_OVERLAY: OverlayData = { shades: [], opens: [], shadeHue: "", openHue: "", wave: null, segments: [], font: "" };

class Overlays implements ISeriesPrimitive<Time> {
  private params: SeriesAttachedParameter<Time> | null = null;
  private data: OverlayData = NO_OVERLAY;

  attached(p: SeriesAttachedParameter<Time>): void {
    this.params = p;
  }

  detached(): void {
    this.params = null;
  }

  set(d: OverlayData): void {
    this.data = d;
    this.params?.requestUpdate();
  }

  updateAllViews(): void {}

  private renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      const p = this.params;
      const d = this.data;
      if (!p) return;
      const ts = p.chart.timeScale();
      const step = ts.options().barSpacing;
      const x = (i: number) => ts.logicalToCoordinate(i as Logical) as number | null;
      const y = (v: number) => p.series.priceToCoordinate(v) as number | null;
      target.useBitmapCoordinateSpace(({ context: c, bitmapSize, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        c.save();
        c.fillStyle = d.shadeHue;
        for (const s of d.shades) {
          const a = x(s.from);
          const b = x(s.to);
          if (a === null || b === null) continue;
          c.fillRect(Math.round((a - step / 2) * hr), 0, Math.round((b - a + step) * hr), bitmapSize.height);
        }
        c.fillStyle = d.openHue;
        for (const o of d.opens) {
          const a = x(o);
          if (a !== null) c.fillRect(Math.round((a - step / 2) * hr), 0, Math.max(1, Math.round(hr)), bitmapSize.height);
        }
        if (d.wave) {
          const { upper, lower, hue } = d.wave;
          c.fillStyle = hue;
          c.beginPath();
          let pen = false;
          const back: Array<[number, number]> = [];
          for (let i = 0; i < upper.length; i++) {
            const u = upper[i];
            const l = lower[i];
            const px = x(i);
            if (u == null || l == null || px === null) continue;
            const yu = y(u);
            const yl = y(l);
            if (yu === null || yl === null) continue;
            if (pen) c.lineTo(px * hr, yu * vr);
            else c.moveTo(px * hr, yu * vr);
            pen = true;
            back.push([px * hr, yl * vr]);
          }
          for (let i = back.length - 1; i >= 0; i--) c.lineTo(back[i][0], back[i][1]);
          c.closePath();
          c.fill();
        }
        c.font = `${Math.round(9 * vr)}px ${d.font}`;
        for (const s of d.segments) {
          const a = x(s.i0);
          const b = x(s.i1);
          const py = y(s.v);
          if (a === null || b === null || py === null) continue;
          const x1 = (a - step / 2) * hr;
          const x2 = (b + step / 2) * hr;
          const yy = Math.round(py * vr) + 0.5;
          c.strokeStyle = s.hue;
          c.fillStyle = s.hue;
          c.lineWidth = Math.max(1, Math.round(hr));
          c.setLineDash(s.dashed ? [5 * hr, 4 * hr] : []);
          c.beginPath();
          c.moveTo(x1, yy);
          c.lineTo(x2, yy);
          c.stroke();
          c.textAlign = s.labelEnd ? "right" : "left";
          c.fillText(s.label, s.labelEnd ? x2 - 2 * hr : x1 + 2 * hr, yy - 3 * vr);
        }
        c.restore();
      });
    },
  };

  private view: IPrimitivePaneView = { zOrder: () => "bottom", renderer: () => this.renderer };

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}

/* -------------------------------------------------------------------------- */

type LineSet = {
  ema8: ISeriesApi<"Line">;
  ema10: ISeriesApi<"Line">;
  vwap: ISeriesApi<"Line">;
  ema200: ISeriesApi<"Line">;
};

interface LevelLine {
  key: string;
  v: number;
  hue: string;
  title: string;
  dashed: boolean;
  faint: boolean;
  layer: Layer | null;
}

interface Built {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  lines: LineSet;
  volume: ISeriesApi<"Histogram">;
  markers: ISeriesMarkersPluginApi<Time>;
  overlays: Overlays;
  levels: IPriceLine[];
}

const t_ = (t: number) => t as UTCTimestamp;

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
  const [layers, setLayers] = usePersisted<Layer[]>("scan.layers", LAYER_DEFAULT, manyOf(...LAYERS));
  const [err, setErr] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [live, setLive] = useState<TickPayload | null>(null);
  const [offScale, setOffScale] = useState<string[]>([]);

  const host = useRef<HTMLDivElement | null>(null);
  const readout = useRef<HTMLParagraphElement | null>(null);
  const built = useRef<Built | null>(null);
  const data = useRef<ScanBars | null>(null);
  const palette = useRef<Palette | null>(null);
  const levelList = useRef<LevelLine[]>([]);
  // Which levels may set the scale: those near the candles, as the old chart's rule was.
  const scaleLevels = useRef<number[]>([]);
  const first = useRef(true);
  const seq = useRef(0);
  const tfRef = useRef(tf);
  tfRef.current = tf;
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const stateRef = useRef(state);
  stateRef.current = state;
  const emRef = useRef(em);
  emRef.current = em;
  const clockRef = useRef<string | undefined>(undefined);

  const refreshOffScale = useCallback(() => {
    const b = built.current;
    if (!b) return;
    const h = b.chart.paneSize().height;
    const out: string[] = [];
    for (const l of levelList.current) {
      const y = b.candles.priceToCoordinate(l.v);
      if (y === null) continue;
      if (y < 0) out.push(`${l.title} ${num(l.v)} ↑`);
      else if (y > h) out.push(`${l.title} ${num(l.v)} ↓`);
    }
    setOffScale((was) => (was.join("|") === out.join("|") ? was : out));
  }, []);

  /** Everything derived from the series, drawn again. */
  const paint = useCallback(() => {
    const b = built.current;
    const d = data.current;
    const p = palette.current;
    if (!b || !d || !d.ok || !p || d.bars.length === 0) return;
    const on = (l: Layer) => layersRef.current.includes(l);
    const tfNow = (d.tf ?? tfRef.current) as ChartTf;
    const inExt = (t: number) => {
      if (tfNow === "D") return false;
      const s = d.sessions.find((x) => t >= x.from && t < x.to);
      return !s || s.kind !== "rth";
    };

    const view = b.chart.timeScale().getVisibleLogicalRange();
    const candles: CandlestickData<Time>[] = d.bars.map((x) => {
      if (!inExt(x.t)) return { time: t_(x.t), open: x.o, high: x.h, low: x.l, close: x.c };
      const hue = x.c >= x.o ? p.upDim : p.downDim;
      return { time: t_(x.t), open: x.o, high: x.h, low: x.l, close: x.c, color: hue, wickColor: hue, borderColor: hue };
    });
    b.candles.setData(candles);

    const toLine = (a: Array<number | null> | undefined): Array<LineData<Time> | WhitespaceData<Time>> =>
      d.bars.map((x, i) => {
        const v = a?.[i];
        return v == null ? { time: t_(x.t) } : { time: t_(x.t), value: v };
      });
    b.lines.ema8.setData(toLine(d.ema8));
    b.lines.ema10.setData(toLine(d.ema10));
    b.lines.vwap.setData(toLine(d.vwap));
    b.lines.ema200.setData(toLine(d.ema200));
    const waveHue = stateRef.current > 0 ? p.up : stateRef.current < 0 ? p.down : p.ink3;
    b.lines.ema8.applyOptions({ color: rgba(waveHue, 0.7), visible: on("ema8") });
    b.lines.ema10.applyOptions({ color: rgba(waveHue, 0.45), visible: on("ema8") });
    b.lines.vwap.applyOptions({ color: rgba(p.ink2, 0.85), visible: on("vwap") });
    b.lines.ema200.applyOptions({ color: rgba(p.ink3, 0.9), visible: on("ema200") });

    const vol: HistogramData<Time>[] = d.bars.map((x) => ({
      time: t_(x.t),
      value: x.v,
      color: rgba(x.c >= x.o ? p.up : p.down, inExt(x.t) ? 0.14 : 0.32),
    }));
    b.volume.setData(vol);
    b.volume.applyOptions({ visible: on("vol") });

    // Shaded runs of extended-hours bars, and a hairline at each 09:30.
    const shades: OverlayData["shades"] = [];
    const opens: number[] = [];
    let run: number | null = null;
    d.bars.forEach((x, i) => {
      const ext = inExt(x.t);
      if (ext && run === null) run = i;
      if (!ext && run !== null) {
        shades.push({ from: run, to: i - 1 });
        opens.push(i);
        run = null;
      }
    });
    if (run !== null) shades.push({ from: run, to: d.bars.length - 1 });

    const segments: Segment[] = [];
    for (const h of d.history ?? []) {
      const pm = h.key === "PMH" || h.key === "PML";
      if (!on(pm ? "pm" : "pd")) continue;
      const i0 = d.bars.findIndex((x) => x.t >= h.from);
      let i1 = -1;
      for (let i = d.bars.length - 1; i >= 0; i--) {
        if (d.bars[i].t < h.to) {
          i1 = i;
          break;
        }
      }
      if (i0 < 0 || i1 < i0) continue;
      segments.push({
        i0,
        i1,
        v: h.v,
        hue: rgba(h.key === "PDH" || h.key === "PMH" ? p.up : p.down, 0.5),
        dashed: pm,
        label: h.key,
        labelEnd: pm,
      });
    }
    b.overlays.set({
      shades,
      opens,
      shadeHue: p.shade,
      openHue: p.ring2,
      wave: on("ema8") ? { upper: d.ema8, lower: d.ema10, hue: rgba(waveHue, 0.16) } : null,
      segments,
      font: getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || "monospace",
    });

    // The levels. Near ones help set the scale; a level far off must not crush the candles.
    for (const l of b.levels) b.candles.removePriceLine(l);
    b.levels = [];
    const L = d.levels;
    const forming = !L.pm_done;
    const list: LevelLine[] = [];
    const add = (key: string, v: number | null | undefined, hue: string, dashed: boolean, faint: boolean, layer: Layer | null, title: string) => {
      if (v == null) return;
      if (layer && !on(layer)) return;
      list.push({ key, v, hue, dashed, faint, layer, title });
    };
    add("PDH", L.pdh, p.up, false, false, "pd", "PDH");
    add("PMH", L.pmh, p.up, true, forming, "pm", forming ? "PMH ·f" : "PMH");
    add("PML", L.pml, p.down, true, forming, "pm", forming ? "PML ·f" : "PML");
    add("PDL", L.pdl, p.down, false, false, "pd", "PDL");
    const band = emRef.current;
    if (band) {
      add("EMH", band.hi, p.ink3, true, false, null, band.label);
      add("EML", band.lo, p.ink3, true, false, null, "EM");
    }
    levelList.current = list;
    for (const l of list) {
      b.levels.push(
        b.candles.createPriceLine({
          price: l.v,
          color: rgba(l.hue, l.faint ? 0.5 : 0.85),
          lineWidth: 1,
          lineStyle: l.key.startsWith("EM") ? LineStyle.Dotted : l.dashed ? LineStyle.Dashed : LineStyle.Solid,
          axisLabelVisible: true,
          title: l.title,
        }),
      );
    }
    scaleLevels.current = list.filter((l) => !l.key.startsWith("EM")).map((l) => l.v);

    const marks: SeriesMarker<Time>[] = [];
    const have = new Set(d.bars.map((x) => x.t));
    for (const s of d.signals) {
      if (!have.has(s.t)) continue;
      const long = s.side === "long";
      marks.push({
        time: t_(s.t),
        position: long ? "belowBar" : "aboveBar",
        shape: s.kind === "E_SETUP" ? "circle" : long ? "arrowUp" : "arrowDown",
        color: long ? p.up : p.down,
        text: s.kind === "BO" ? "◆" : s.kind === "E_SETUP" ? "E" : s.kind,
      });
    }
    marks.sort((x, y) => (x.time as number) - (y.time as number));
    b.markers.setMarkers(marks);

    const ts = b.chart.timeScale();
    if (first.current) {
      first.current = false;
      // Today's pre-market and six bars of the evening before it, or the most
      // recent bars that fit — the daily chart its most recent sessions.
      const n = d.bars.length;
      const lastT = d.bars[n - 1].t;
      const pre = [...d.sessions].reverse().find((s) => s.kind === "pre" && s.from <= lastT);
      let start = pre ? d.bars.findIndex((x) => x.t >= pre.from) : -1;
      start = tfNow === "D" ? Math.max(0, n - 70) : start < 0 ? Math.max(0, n - 80) : Math.max(0, start - 6);
      ts.setVisibleLogicalRange({ from: start, to: n + 5 });
    } else if (view) {
      ts.setVisibleLogicalRange(view);
    }
    requestAnimationFrame(refreshOffScale);
  }, [refreshOffScale]);

  // ---- build once; every later change is applied in place -----------------------
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const p = readPalette();
    palette.current = p;
    const font = getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim();
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: p.ink3,
        fontFamily: font || "monospace",
        fontSize: 11,
        attributionLogo: true,
      },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      rightPriceScale: { borderColor: p.ring, scaleMargins: { top: 0.08, bottom: 0.06 } },
      localization: {
        timeFormatter: (t: unknown) => {
          const v = t as number;
          return tfRef.current === "D" ? `${wd(v)} ${md(v)}` : `${md(v)} ${hm(v)}`;
        },
      },
      timeScale: {
        borderColor: p.ring,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        tickMarkFormatter: (t: unknown, kind: TickMarkType) => {
          const v = t as number;
          if (tfRef.current === "D" || kind <= TickMarkType.DayOfMonth) return md(v);
          return hm(v);
        },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: p.ink3, style: LineStyle.Dotted, width: 1 },
        horzLine: { color: p.ink3, style: LineStyle.Dotted, width: 1 },
      },
      handleScale: { axisPressedMouseMove: { price: true, time: true } },
      handleScroll: { vertTouchDrag: false },
    });

    const autoscale = (base: () => AutoscaleInfo | null): AutoscaleInfo | null => {
      const res = base();
      if (!res?.priceRange) return res;
      let lo = res.priceRange.minValue;
      let hi = res.priceRange.maxValue;
      const span = Math.max(hi - lo, hi * 0.002);
      for (const v of scaleLevels.current) {
        if (v > lo - span * 0.6 && v < hi + span * 0.6) {
          lo = Math.min(lo, v);
          hi = Math.max(hi, v);
        }
      }
      return { ...res, priceRange: { minValue: lo, maxValue: hi } };
    };

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: p.up,
      downColor: p.down,
      wickUpColor: p.up,
      wickDownColor: p.down,
      borderVisible: false,
      priceLineColor: p.ink3,
      priceLineStyle: LineStyle.Dotted,
      autoscaleInfoProvider: autoscale,
    });
    const quiet = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, lineWidth: 1 } as const;
    const lines: LineSet = {
      ema8: chart.addSeries(LineSeries, quiet),
      ema10: chart.addSeries(LineSeries, quiet),
      vwap: chart.addSeries(LineSeries, { ...quiet, lineStyle: LineStyle.Dashed }),
      // The 200 EMA never sets the scale: a name that gapped 25% would have its
      // candles crushed into a sliver for a line a long way off.
      ema200: chart.addSeries(LineSeries, { ...quiet, autoscaleInfoProvider: () => null }),
    };
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    const overlays = new Overlays();
    candles.attachPrimitive(overlays);
    built.current = { chart, candles, lines, volume, markers: createSeriesMarkers(candles, []), overlays, levels: [] };

    chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      const out = readout.current;
      const d = data.current;
      if (!out || !d) return;
      const t = param.time as number | undefined;
      const i = t === undefined ? -1 : d.bars.findIndex((x) => x.t === t);
      out.dataset.touched = i >= 0 ? "1" : "0";
      if (i < 0) {
        out.textContent = `${d.tf ?? tfRef.current} · ${(d.tf ?? tfRef.current) === "D" ? "regular session" : "ET"} · ${d.bars.length} bars`;
        return;
      }
      const x = d.bars[i];
      const when = (d.tf ?? tfRef.current) === "D" ? `${wd(x.t)} ${md(x.t)}` : hm(x.t);
      const parts = [when, `O ${num(x.o)}`, `H ${num(x.h)}`, `L ${num(x.l)}`, `C ${num(x.c)}`];
      if (x.v) parts.push(`V ${compact(x.v)}`);
      const v = d.vwap[i];
      const e = d.ema8[i];
      if (v != null) parts.push(`VWAP ${num(v)}`);
      if (e != null) parts.push(`8EMA ${num(e)}`);
      out.textContent = parts.join("  ");
    });
    let raf = 0;
    const onRange = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(refreshOffScale);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    // A new theme or interface: the same chart, recoloured in place.
    const obs = new MutationObserver(() => {
      const next = readPalette();
      if (JSON.stringify(next) === JSON.stringify(palette.current)) return;
      palette.current = next;
      chart.applyOptions({
        layout: { textColor: next.ink3 },
        grid: { vertLines: { color: next.grid }, horzLines: { color: next.grid } },
        rightPriceScale: { borderColor: next.ring },
        timeScale: { borderColor: next.ring },
      });
      candles.applyOptions({ upColor: next.up, downColor: next.down, wickUpColor: next.up, wickDownColor: next.down, priceLineColor: next.ink3 });
      paint();
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["style", "class", "data-theme"] });

    return () => {
      cancelAnimationFrame(raf);
      obs.disconnect();
      chart.remove();
      built.current = null;
    };
  }, [paint, refreshOffScale]);

  // ---- the whole series, on its slow poll ----------------------------------------
  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/bars/${encodeURIComponent(sym)}?tf=${tf}`, { cache: "no-store" });
      const d = (await r.json()) as ScanBars & { offline?: { reason: string } };
      if (mine !== seq.current) return;
      setErr(d.offline ? d.offline.reason : d.ok ? null : (d.error ?? "no bars"));
      if (!d.ok) return;
      data.current = d;
      setReady(true);
      paint();
      if (readout.current && readout.current.dataset.touched !== "1") {
        readout.current.textContent = `${d.tf ?? tf} · ${(d.tf ?? tf) === "D" ? "regular session" : "ET"} · ${d.bars.length} bars`;
      }
    } catch (e) {
      if (mine === seq.current) setErr(e instanceof Error ? e.message : "request failed");
    }
  }, [sym, tf, paint]);

  useEffect(() => {
    // A new name or timeframe starts blank rather than showing the last one's candles.
    first.current = true;
    data.current = null;
    setReady(false);
    setErr(null);
    setLive(null);
    void load();
    let id = 0;
    const again = () => {
      const open = clockRef.current !== "closed";
      id = window.setTimeout(
        () => {
          void load();
          again();
        },
        (open ? POLL_SEC[tf] : IDLE_POLL_SEC) * 1000,
      );
    };
    again();
    return () => clearTimeout(id);
  }, [load, tf]);

  // ---- the last trade, every second ----------------------------------------------
  useEffect(() => {
    let dead = false;
    let id = 0;
    const applyTick = (t: TickPayload) => {
      const b = built.current;
      const d = data.current;
      if (!b || !d?.ok || !t.ok || t.price == null || t.at == null || !t.session) return;
      const tfNow = (d.tf ?? tfRef.current) as ChartTf;
      const n = d.bars.length;
      if (n === 0) return;
      const lastBar = d.bars[n - 1];
      // A daily bar is the regular session, and one candle per day.
      if (tfNow === "D") {
        if (t.session !== "rth" || ymd(t.at) !== ymd(lastBar.t)) return;
      }
      const merged =
        tfNow === "D"
          ? {
              bar: { ...lastBar, h: Math.max(lastBar.h, t.price), l: Math.min(lastBar.l, t.price), c: t.price },
              isNew: false,
            }
          : mergeTick(lastBar, { price: t.price, at: t.at, minute: t.minute }, STEP[tfNow]);
      if (!merged) return;
      const p = palette.current;
      const { bar, isNew } = merged;
      if (isNew) {
        d.bars.push(bar);
        for (const a of [d.ema8, d.ema9, d.ema10, d.vwap, d.ema200 ?? []]) a.push(null);
      } else {
        d.bars[n - 1] = bar;
      }
      const ext = t.session !== "rth" && tfNow !== "D";
      const hue = !p || !ext ? undefined : bar.c >= bar.o ? p.upDim : p.downDim;
      b.candles.update({
        time: t_(bar.t),
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
        ...(hue ? { color: hue, wickColor: hue, borderColor: hue } : {}),
      });
      // The wave and the 200 move with the close; VWAP needs volume and waits for the poll.
      const i = d.bars.length - 1;
      const step = (arr: Array<number | null> | undefined, len: number, s: ISeriesApi<"Line">) => {
        const prev = arr?.[i - 1];
        if (!arr || prev == null) return;
        const v = nextEma(prev, bar.c, len);
        arr[i] = v;
        s.update({ time: t_(bar.t), value: v });
      };
      step(d.ema8, 8, b.lines.ema8);
      step(d.ema10, 10, b.lines.ema10);
      step(d.ema200, 200, b.lines.ema200);
    };
    const run = async () => {
      if (dead) return;
      if (document.visibilityState === "visible") {
        try {
          const r = await fetch(`/api/scanner/tick/${encodeURIComponent(sym)}`, { cache: "no-store" });
          const t = (await r.json()) as TickPayload;
          if (!dead && t.sym === sym) {
            clockRef.current = t.clock_session;
            applyTick(t);
            setLive((was) => (was?.at === t.at && was?.ok === t.ok && was?.overnight?.at === t.overnight?.at ? was : t));
          }
        } catch {
          /* a missed tick; the slow poll still runs */
        }
      }
      if (!dead) id = window.setTimeout(run, clockRef.current === "closed" ? IDLE_TICK_MS : TICK_MS);
    };
    void run();
    return () => {
      dead = true;
      clearTimeout(id);
    };
  }, [sym]);

  // A layer toggled or the row's state changed: repaint what is held.
  useEffect(() => {
    paint();
  }, [layers, state, em?.hi, em?.lo, paint]);

  const toggle = (l: Layer) => setLayers((was) => (was.includes(l) ? was.filter((x) => x !== l) : [...was, l]));

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2">
        <span className="seg shrink-0" role="group" aria-label="Chart timeframe">
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
        <span className="seg shrink-0" role="group" aria-label="What the chart draws">
          {LAYERS.map((l) => (
            <button key={l} type="button" title={LAYER_TITLE[l]} onClick={() => toggle(l)} aria-pressed={layers.includes(l)} {...segItem(layers.includes(l), { className: "text-[10.5px]" })}>
              {LAYER_NAME[l]}
            </button>
          ))}
        </span>
        {tf !== "10m" && tf !== "D" && (
          <span className="min-w-0 truncate text-[11px] text-ink-3" title="The (L) and (E) signals are read on ten-minute bars; on this view each sits on the bar holding the ten-minute close that confirmed it">
            signals read on 10m
          </span>
        )}
        <LiveChip t={live} />
      </div>
      <div className="relative min-h-0 flex-1">
        <div ref={host} className={cn("absolute inset-0", !ready && "invisible")} aria-label={`${sym} ${TF_NAME[tf]} chart with its levels`} />
        <p ref={readout} className="fig pointer-events-none absolute top-1 left-3 z-10 text-[11px] text-ink-3" />
        {offScale.length > 0 && (
          <p className="fig pointer-events-none absolute top-1 right-[76px] z-10 text-right text-[10.5px] leading-[1.5] text-ink-3" title="Levels off the top or bottom of the visible scale">
            {offScale.map((s) => (
              <span key={s} className="block">
                {s}
              </span>
            ))}
          </p>
        )}
        {!ready &&
          (err ? (
            <p className="absolute inset-0 flex items-center justify-center text-[12px] text-ink-3">No chart — {err}</p>
          ) : (
            <HelmLoader label={`Loading the ${tf} chart`} size={40} className="absolute inset-0" />
          ))}
      </div>
    </div>
  );
}

/**
 * How fresh the chart is, on its face: a live trade seconds old, the spark layer's,
 * or the bars alone — and overnight, the last print, which is not on the candles.
 */
function LiveChip({ t }: { t: TickPayload | null }) {
  let word = "bars only";
  let hue = "bg-ink-4";
  let title = "No live trades for this name right now: the chart is on its slow poll of the bars.";
  if (t?.ok && t.at != null && t.session) {
    const age = t.age_sec ?? 0;
    if (age < 90) {
      word = age < 10 ? `live ${Math.max(0, Math.round(age))}s` : `${Math.round(age)}s ago`;
      hue = age < 10 ? "bg-call-fig" : "bg-flip-fig";
      title = t.via === "spark" ? "The last trade, from the five-second quote layer" : "The last trade, from the live stream, laid on the last candle";
    }
  }
  return (
    <span className="fig ml-auto flex shrink-0 items-center gap-2 text-[11px] text-ink-3" title={title}>
      {t?.overnight && (
        <span title="The last overnight print. Overnight trades stay out of the candles and the levels.">
          overnight <span className="text-ink-2">{num(t.overnight.price)}</span>
        </span>
      )}
      <span aria-hidden className={cn("inline-block h-[6px] w-[6px] rounded-[1px]", hue)} />
      {word}
    </span>
  );
}
