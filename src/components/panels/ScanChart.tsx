"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import type { ChartTf, ScanBars, TickPayload, VwapAnchor } from "@/types/scanner";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { Choice, Menu } from "@/components/panels/ScanWide";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { isBool, manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { mergeTick, nextEma } from "@/lib/chartLive";
import { CHART_COLORS, setChartColors, useChartColors } from "@/lib/chartColors";
import { extKind, shadeRuns, type ExtKind } from "@/lib/chartShade";
import { wallRank } from "@/lib/walls";
import { keepRead, lastRead } from "@/lib/lastRead";

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
 * THE PRE-MARKET IS SHADED, because the strategy is a regular-session one and the
 * pre-market is where its levels come from. Josh's colours (owner, 2026-11-12, from
 * their own chart: the shaded colours "the same as this ... and make sure that they dont
 * shade over the actual candles") shade the after-hours blue and the pre-market sand;
 * the default colours shade the pre-market alone (2026-11-13). Candles in either are at
 * full strength since 2026-11-13: the default chart drew them at half, and that read as
 * shade over them.
 *
 * A FUTURES BOOK IS NOT SHADED (owner, 2026-11-10: "the futures chart should mark
 * from the 18:00 open ... i dont like" the extended-hours shading). Its overnight
 * is part of its day, so its chart marks each 18:00 reopen with a hairline and
 * frames from the last one. Its VWAP is anchored where the reader picks (18:00,
 * London, 09:30 or the week) with up to three deviation bands, all sent by the
 * collector for every anchor so a switch draws at once. Its payload's `opens`
 * is what tells the chart it is a future.
 *
 * WHAT THE LIBRARY DOES NOT DRAW goes in one primitive, `Overlays`: the shading,
 * the 09:30 hairlines, the wave's fill, earlier sessions' levels over their own
 * days. The levels off the scale are named in the corner, because a price line
 * off the top of the pane simply is not there.
 */

const TFS: readonly ChartTf[] = ["1m", "3m", "5m", "10m", "30m", "60m", "D"];
/** What the strip calls each: the hour reads "1h" (owner, 2026-11-10), the key stays "60m" for the API and the saved choice. */
const TF_LABEL: Partial<Record<ChartTf, string>> = { "60m": "1h" };
const STEP: Record<ChartTf, number> = { "1m": 60, "3m": 180, "5m": 300, "10m": 600, "30m": 1800, "60m": 3600, D: 86400 };
const TF_NAME: Record<ChartTf, string> = {
  "1m": "one-minute",
  "3m": "three-minute",
  "5m": "five-minute",
  "10m": "ten-minute",
  "30m": "thirty-minute",
  "60m": "hourly",
  D: "daily",
};
/**
 * How often the whole series is read again, for what a trade cannot tell the
 * chart: the EMAs' history, VWAP, volume, new signals. The 1m and 3m views read a
 * one-minute download with a twenty-second cache, so asking faster buys nothing.
 */
const POLL_SEC: Record<ChartTf, number> = { "1m": 20, "3m": 20, "5m": 15, "10m": 15, "30m": 15, "60m": 15, D: 120 };
const IDLE_POLL_SEC = 60;
const TICK_MS = 1000;
const IDLE_TICK_MS = 5000;

const LAYERS = ["ema8", "ema20", "ema50", "ema200", "vwap", "pd", "pm", "vol"] as const;
type Layer = (typeof LAYERS)[number];
const LAYER_NAME: Record<Layer, string> = {
  ema8: "EMA 8",
  ema20: "EMA 20",
  ema50: "EMA 50",
  ema200: "EMA 200",
  vwap: "VWAP",
  pd: "PDH / PDL",
  pm: "PMH / PML",
  vol: "Vol",
};
const LAYER_TITLE: Record<Layer, string> = {
  ema8: "The 8 EMA wave",
  ema20: "The 20 EMA",
  ema50: "The 50 EMA",
  ema200: "The 200 EMA",
  vwap: "VWAP, from 09:30",
  pd: "The previous day's high and low (its 09:30 to 16:00 ET session), for the last day on the chart",
  pm: "The pre-market high and low, 04:00 to 09:30 ET, on a stock and a future alike",
  vol: "Volume",
};
// The 20 and the 50 are there to be picked, not on by default: the strategy reads
// the wave and the 200, and a chart that opens with four averages is a busier one.
const LAYER_DEFAULT: Layer[] = ["ema8", "ema200", "vwap", "pd", "pm", "vol"];

/*
 * WHAT THE CHART DRAWS IS PICKED FROM ONE MENU, "INDICATORS", ON EVERY CHART (owner,
 * 2026-11-12: "keep things consistent across the app, eg on the futures tab can we have
 * our charts indicators and levels like how it is in the stocks section", then "i meant
 * the design decisions should be consistent", and of the two toolbars shown side by
 * side they picked this one). The toolbar is the timeframes and that one menu, which
 * names the averages and VWAP that are on; in it are the averages, VWAP with its bands
 * (and, on a future, where it is anchored), the level and volume switches, and the
 * chart's colours.
 *
 * HOW IT GOT HERE. Six chips in a row at first; then two menus (averages, VWAP) and
 * three switches (2026-11-11: "a dropdown where you select what you want applied");
 * then, for the six charts of Multicharts, the same choices behind one menu because the
 * bar had no room for more. That left two designs for one job: one menu over the grid,
 * and two menus, four switches and a Colours button over two lines on the Futures chart
 * and the slide-out. There is one now. The cost is that a level switch is one click
 * further in than it was.
 *
 * A FUTURES CHART HAS ONE MORE SWITCH, GEX, for its gamma lines: the call walls, the
 * put walls and the flip (owner, 2026-11-11: "i only meant on the charts that we have
 * a toggle to remove the levels like the other indicators do"). It sits with the other
 * level switches, takes those lines off the chart and nothing else: the Gamma cards and
 * figures on the pages stay.
 */
const EMA_LAYERS = ["ema8", "ema20", "ema50", "ema200"] as const satisfies readonly Layer[];
const SWITCH_LAYERS = ["pd", "pm", "vol"] as const satisfies readonly Layer[];
/** A futures line's `tone` when it is a gamma level; "ref" is the settle and the opening range. */
const GEX_TONES: ReadonlySet<string> = new Set(["call", "put", "flip"]);
const EMA_LEN: Record<(typeof EMA_LAYERS)[number], number> = { ema8: 8, ema20: 20, ema50: 50, ema200: 200 };
const EMA_NOTE: Record<(typeof EMA_LAYERS)[number], string> = {
  ema8: "the wave, with the 10",
  ema20: "",
  ema50: "",
  ema200: "the side filter",
};

/** A futures VWAP's anchors (futures.ANCHORS) and how many deviation bands to draw. */
const ANCHORS = ["globex", "london", "rth", "week"] as const satisfies readonly VwapAnchor[];
const ANCHOR_CHOICES: ReadonlyArray<{ value: VwapAnchor; label: string }> = [
  { value: "globex", label: "18:00" },
  { value: "london", label: "London" },
  { value: "rth", label: "09:30" },
  { value: "week", label: "Week" },
];
const ANCHOR_WORD: Record<VwapAnchor, string> = { globex: "18:00", london: "London", rth: "09:30", week: "week" };
type BandCount = 0 | 1 | 2 | 3;
const isBandCount = (v: unknown): v is BandCount => v === 0 || v === 1 || v === 2 || v === 3;
const BAND_CHOICES: ReadonlyArray<{ value: BandCount; label: string }> = [
  { value: 0, label: "Off" },
  { value: 1, label: "1σ" },
  { value: 2, label: "1–2σ" },
  { value: 3, label: "1–3σ" },
];
const SHOW_CHOICES: ReadonlyArray<{ value: "on" | "off"; label: string }> = [
  { value: "on", label: "Shown" },
  { value: "off", label: "Hidden" },
];
/** The bands fade outward: the first is the one price leans on. */
const BAND_ALPHA = [0.55, 0.4, 0.28] as const;
const CLEAR = "rgba(0,0,0,0)";

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
  /** Behind the pre-market's bars and behind the after-hours': one neutral shade, unless the chart's colours name two. */
  shadePre: string;
  shadePost: string;
  /** The chart's ground and the line at the last price: the interface's, unless the chart has colours of its own. */
  bg: string;
  priceLine: string;
  /** The 20 and 50 EMAs: two of the desks' muted hues, so neither reads as a call, a put or the flip. */
  ma20: string;
  ma50: string;
}

function rgba(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})` : hex;
}

/**
 * The colours, read off the chart's own area and not the page: the interface's by
 * inheritance, or the chart's own where the area sets them (lib/chartColors; the
 * variables are in globals.css under "the chart's own colours").
 */
function readPalette(area: Element): Palette {
  const cs = getComputedStyle(area);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  const up = v("--call-fig");
  const down = v("--put-fig");
  // How strongly an extended-hours candle is drawn: in full, as Josh's colours always
  // did (owner, 2026-11-13: "can we have the shaded part not reduce the color of the
  // candles?"); a chart's colours may still give a figure of their own.
  const own = Number.parseFloat(v("--chart-ext-candle"));
  const dim = Number.isFinite(own) ? Math.min(1, Math.max(0, own)) : 1;
  // The default pre-market shade: a light lift on the dark ground. It was the surface
  // tone at 55%, a grey on a grey, and on the Luminous sheet it could not be seen at all
  // (owner, 2026-11-13: "you cant tell the difference on default"). 7% was seen but
  // faint; 13% after "can we also make the extended hours shading obvious".
  const shade = rgba(v("--ink"), 0.13);
  return {
    up,
    down,
    upDim: rgba(up, dim),
    downDim: rgba(down, dim),
    ink: v("--ink"),
    ink2: v("--ink-2"),
    ink3: v("--ink-3"),
    ring: v("--ring"),
    ring2: v("--ring-2"),
    shadePre: v("--chart-shade-pre") || shade,
    // THE TWO HALVES TOLD APART ON THE DEFAULT COLOURS (owner, 2026-11-13). With one
    // neutral shade for both, the evening ran into the morning as one block from 16:00
    // ("you cant tell the difference on default"); the after-hours went unshaded for an
    // hour, then came back as "like the pre market but less bright": the same lift at
    // half the strength, then "reduce the strength slightly more": 4.5%. Josh's colours
    // give each half its own hue.
    shadePost: v("--chart-shade-post") || rgba(v("--ink"), 0.045),
    bg: v("--chart-bg") || "transparent",
    priceLine: v("--chart-price") || v("--ink-3"),
    ma20: v("--desk-markets"),
    ma50: v("--desk-macro"),
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
  /** The chart's own level (the last day's): drawn on past the last bar to the right edge. */
  toEdge?: boolean;
}

interface OverlayData {
  /** One run per extended session, in its own colour: the evening's and the next morning's are neighbours. */
  shades: Array<{ from: number; to: number; hue: string }>;
  opens: number[];
  openHue: string;
  wave: { upper: Array<number | null>; lower: Array<number | null>; hue: string } | null;
  segments: Segment[];
  font: string;
}

const NO_OVERLAY: OverlayData = { shades: [], opens: [], openHue: "", wave: null, segments: [], font: "" };

/** A gamma wall's label, drawn by the chart and not the library (lib/walls). */
interface WallTag {
  v: number;
  word: string;
  /** Triangles: 3 for the heaviest wall on its side. */
  n: number;
  up: boolean;
  bg: string;
  fg: string;
}

/**
 * Black or white on a label of this colour, by the chart library's own weights (0.199,
 * 0.687, 0.114; over 160 is black), so a drawn wall label reads like the library's
 * labels beside it: dark on the teal, white on the pink, as PDH and PML are.
 */
function contrastInk(hex: string): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!m) return "#ffffff";
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16));
  return 0.199 * r + 0.687 * g + 0.114 * b > 160 ? "#000000" : "#ffffff";
}

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
        // Two runs that meet (the evening, then the next morning) share one edge to the
        // pixel: rounded apart they would leave a line of the ground between them, or
        // overlap into a darker one where the shade is see-through.
        let edge: { after: number; px: number } | null = null;
        for (const s of d.shades) {
          const a = x(s.from);
          const b = x(s.to);
          if (a === null || b === null) {
            edge = null;
            continue;
          }
          const left = edge && edge.after === s.from - 1 ? edge.px : Math.round((a - step / 2) * hr);
          const right = Math.round((b + step / 2) * hr);
          c.fillStyle = s.hue;
          c.fillRect(left, 0, right - left, bitmapSize.height);
          edge = { after: s.to, px: right };
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
        for (const s of d.segments) {
          const a = x(s.i0);
          const b = x(s.i1);
          const py = y(s.v);
          if (a === null || b === null || py === null) continue;
          const x1 = (a - step / 2) * hr;
          const x2 = s.toEdge ? bitmapSize.width : (b + step / 2) * hr;
          const yy = Math.round(py * vr) + 0.5;
          c.strokeStyle = s.hue;
          c.fillStyle = s.hue;
          c.lineWidth = Math.max(1, Math.round(hr));
          c.setLineDash(s.dashed ? [5 * hr, 4 * hr] : []);
          c.beginPath();
          c.moveTo(x1, yy);
          c.lineTo(x2, yy);
          c.stroke();
        }
        c.restore();
      });
    },
  };


  private view: IPrimitivePaneView = { zOrder: () => "bottom", renderer: () => this.renderer };

  /*
   * THE WALLS' LABELS, DRAWN HERE (owner, 2026-11-14: "do option 3"; lib/walls says why).
   * The library's own label for a level is text in one size, and no character is a solid
   * flat triangle between ▴ and ▲; so the walls' lines carry no title of their own and
   * this draws one in the same place, the right edge at the line's price: a box in the
   * line's colour, the name in the chart's type, then the triangles, each about two
   * thirds of the type's height.
   */
  private walls: { tags: WallTag[]; px: number; font: string } = { tags: [], px: 11, font: "monospace" };

  setWalls(tags: WallTag[], px: number, font: string): void {
    this.walls = { tags, px, font };
    this.params?.requestUpdate();
  }

  private labels: IPrimitivePaneRenderer = {
    draw: (target) => {
      const p = this.params;
      const w = this.walls;
      if (!p || w.tags.length === 0) return;
      target.useBitmapCoordinateSpace(({ context: c, bitmapSize, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        c.save();
        c.font = `${Math.round(w.px * vr)}px ${w.font}`;
        c.textBaseline = "middle";
        c.textAlign = "left";
        const padX = Math.round(5 * hr);
        const boxH = Math.round((w.px + 6) * vr);
        const triH = Math.round(w.px * 0.62 * vr);
        const triW = Math.round(w.px * 0.72 * hr);
        const gap = Math.round(2 * hr);
        const space = Math.round(5 * hr);
        for (const t of w.tags) {
          const py = p.series.priceToCoordinate(t.v);
          if (py === null) continue;
          const yy = Math.round(py * vr);
          const textW = Math.ceil(c.measureText(t.word).width);
          const width = padX * 2 + textW + space + t.n * triW + (t.n - 1) * gap;
          const x0 = bitmapSize.width - width;
          const y0 = yy - Math.round(boxH / 2);
          c.fillStyle = t.bg;
          c.fillRect(x0, y0, width, boxH);
          c.fillStyle = t.fg;
          c.fillText(t.word, x0 + padX, yy + Math.round(0.5 * vr));
          const top = yy - Math.round(triH / 2);
          const bottom = top + triH;
          let tx = x0 + padX + textW + space;
          for (let k = 0; k < t.n; k++) {
            c.beginPath();
            if (t.up) {
              c.moveTo(tx, bottom);
              c.lineTo(tx + triW, bottom);
              c.lineTo(tx + triW / 2, top);
            } else {
              c.moveTo(tx, top);
              c.lineTo(tx + triW, top);
              c.lineTo(tx + triW / 2, bottom);
            }
            c.closePath();
            c.fill();
            tx += triW + gap;
          }
        }
        c.restore();
      });
    },
  };

  private labelView: IPrimitivePaneView = { zOrder: () => "top", renderer: () => this.labels };

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view, this.labelView];
  }
}

/* -------------------------------------------------------------------------- */

type LineSet = {
  ema8: ISeriesApi<"Line">;
  ema10: ISeriesApi<"Line">;
  ema20: ISeriesApi<"Line">;
  ema50: ISeriesApi<"Line">;
  vwap: ISeriesApi<"Line">;
  ema200: ISeriesApi<"Line">;
  /** VWAP's ±1σ, ±2σ and ±3σ: a future's from its anchor, a stock's from 09:30. */
  bands: Array<{ up: ISeriesApi<"Line">; dn: ISeriesApi<"Line"> }>;
};

interface LevelLine {
  key: string;
  v: number;
  hue: string;
  title: string;
  dashed: boolean;
  faint: boolean;
  layer: Layer | null;
  /** The bar it starts at, when it is drawn from there and not across the whole chart. */
  from?: number;
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

/** The last bar as the chart's corner shows it while the cursor is elsewhere. */
function restingLine(d: ScanBars): string {
  const x = d.bars[d.bars.length - 1];
  if (!x) return "";
  const c = x.c - x.o;
  const p = x.o ? (c / x.o) * 100 : 0;
  const sign = c >= 0 ? "+" : "";
  const vol = x.v ? `  Vol ${compact(x.v)}` : "";
  // Two places but on a sub-dollar name, where two would round most moves to nothing.
  return `O ${num(x.o)}  H ${num(x.h)}  L ${num(x.l)}  C ${num(x.c)}  ${sign}${c.toFixed(x.c < 1 ? 4 : 2)} (${sign}${p.toFixed(2)}%)${vol}`;
}

/**
 * What a chart is set to draw: its timeframe, its layers, where a future's VWAP starts,
 * how many bands, a future's gamma lines. A chart keeps its own (`useChartPrefs`, under
 * its page's prefix), or is handed one set that several charts share: the Stocks tab's
 * Multicharts sets six from one toolbar (`ChartControls`), because six toolbars would
 * take the room the charts are there for.
 *
 * EACH PAGE KEEPS ITS OWN, ON PURPOSE. For twenty minutes on 2026-11-12 the layers and
 * bands were one choice shared by every chart: my reading of "keep things consistent
 * across the app". The owner meant the design, not the settings ("i meant the design
 * decisions should be consistent"), and asked for it undone: the Futures chart and the
 * Stocks chart are set separately.
 */
export interface ChartPrefs {
  tf: ChartTf;
  setTf: (v: ChartTf) => void;
  layers: Layer[];
  setLayers: (v: Layer[] | ((was: Layer[]) => Layer[])) => void;
  anchor: VwapAnchor;
  setAnchor: (v: VwapAnchor) => void;
  bands: BandCount;
  setBands: (v: BandCount) => void;
  gex: boolean;
  setGex: (v: boolean | ((was: boolean) => boolean)) => void;
}

/** The chart's choices, remembered under `store` so each page keeps its own. */
export function useChartPrefs(store: string, future = false): ChartPrefs {
  const [tf, setTf] = usePersisted<ChartTf>(`${store}.tf`, "10m", oneOf(...TFS));
  const [layers, setLayers] = usePersisted<Layer[]>(`${store}.layers`, LAYER_DEFAULT, manyOf(...LAYERS));
  const [anchor, setAnchor] = usePersisted<VwapAnchor>(`${store}.vwapAnchor`, "globex", oneOf(...ANCHORS));
  // A future's bands are on as they were; a stock's start off, so the chart the owner
  // knows does not grow four lines the day the menu arrives.
  const [bands, setBands] = usePersisted<BandCount>(`${store}.vwapBands`, future ? 2 : 0, isBandCount);
  // A futures chart's gamma lines, on until switched off. Kept beside `layers` and not
  // in it: a list saved before this switch existed would not name it, and the lines
  // would vanish from a chart that has always drawn them.
  const [gex, setGex] = usePersisted<boolean>(`${store}.gex`, true, isBool);
  return useMemo(
    () => ({ tf, setTf, layers, setLayers, anchor, setAnchor, bands, setBands, gex, setGex }),
    [tf, setTf, layers, setLayers, anchor, setAnchor, bands, setBands, gex, setGex],
  );
}

export function ScanChart({
  sym,
  state,
  em = null,
  barsUrl,
  tickUrl,
  live: streaming = true,
  store = "scan",
  prefs: shared,
  head,
  onLevels,
}: {
  sym: string;
  state: -2 | -1 | 0 | 1 | 2;
  /** The front expiry's expected move, drawn as a dotted band. */
  em?: { lo: number; hi: number; label: string } | null;
  /** Where the bars come from: a stock's by default, a futures book's on the Futures page. */
  barsUrl?: string;
  /**
   * Where the last trade comes from each second: a stock's stream by default; a futures
   * book's is its ETF's trade in the future's prices (server futfill.py, 2026-11-14).
   */
  tickUrl?: string;
  /** Lay the last trade on the last candle every second. */
  live?: boolean;
  /** The prefix the timeframe and layers are remembered under, so each page keeps its own. */
  store?: string;
  /** One set of choices held above several charts; this chart then keeps none of its own. */
  prefs?: ChartPrefs;
  /**
   * What stands over the chart in place of its toolbar: a chart in a grid is named
   * there, and set from the grid's one toolbar. How fresh it is still shows at the end.
   */
  head?: React.ReactNode;
  /**
   * Handed the four levels this chart has just been sent, each time its bars are read
   * (the Futures tab's Nearest levels card, 2026-11-15). The card measures from the same
   * PDH, PDL, PMH and PML the chart names, so the two cannot say different prices.
   */
  onLevels?: (levels: ScanBars["levels"] | null) => void;
}) {
  const onLevelsRef = useRef(onLevels);
  onLevelsRef.current = onLevels;
  const own = useChartPrefs(store, Boolean(barsUrl));
  const prefs = shared ?? own;
  const { tf, layers, anchor, bands, gex } = prefs;
  // The colours the chart is drawn in: one choice for every chart, set from any of them.
  const colors = useChartColors();
  // Whether these bars carry anchored VWAPs: a futures book off its daily view.
  const [anchored, setAnchored] = useState(false);
  // Whether there is a deviation to draw bands from: a future's anchors, or a stock's own from 09:30.
  const [hasBands, setHasBands] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [live, setLive] = useState<TickPayload | null>(null);
  const [offScale, setOffScale] = useState<string[]>([]);

  const host = useRef<HTMLDivElement | null>(null);
  const readout = useRef<HTMLParagraphElement | null>(null);
  const built = useRef<Built | null>(null);
  const data = useRef<ScanBars | null>(null);
  const palette = useRef<Palette | null>(null);
  // Read the colours again and repaint, once the chart is built (see where it is set).
  const recolor = useRef<() => void>(() => {});
  const levelList = useRef<LevelLine[]>([]);
  // Which levels may set the scale: those near the candles, as the old chart's rule was.
  const scaleLevels = useRef<number[]>([]);
  const first = useRef(true);
  // The opening window while it is still being put in place (see where it is set).
  const opening = useRef<{ range: { from: number; to: number }; until: number } | null>(null);
  const seq = useRef(0);
  const tfRef = useRef(tf);
  tfRef.current = tf;
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const stateRef = useRef(state);
  stateRef.current = state;
  const emRef = useRef(em);
  emRef.current = em;
  const anchorRef = useRef(anchor);
  anchorRef.current = anchor;
  const bandsRef = useRef(bands);
  bandsRef.current = bands;
  const gexRef = useRef(gex);
  gexRef.current = gex;
  const clockRef = useRef<string | undefined>(undefined);

  const refreshOffScale = useCallback(() => {
    const b = built.current;
    if (!b) return;
    const h = b.chart.paneSize().height;
    const out: string[] = [];
    // A futures book's walls and settle stay off this list: the strategy's levels are what it is for.
    for (const l of levelList.current.filter((x) => !x.key.startsWith("L:"))) {
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
    // A futures book: its 18:00 reopens marked, nothing shaded, VWAP from the chosen anchor.
    const fut = Array.isArray(d.opens);
    const av = d.vwaps?.[anchorRef.current] ?? null;
    // Each bar's half of the extended hours, or null: the collector's span where there
    // is one, New York's clock for a bar it has not placed (lib/chartShade).
    const kinds: Array<ExtKind | null> = d.bars.map((x) =>
      tfNow === "D" || fut ? null : extKind(d.sessions.find((s) => x.t >= s.from && x.t < s.to)?.kind, hm(x.t)),
    );

    const view = b.chart.timeScale().getVisibleLogicalRange();
    const candles: CandlestickData<Time>[] = d.bars.map((x, i) => {
      if (kinds[i] === null) return { time: t_(x.t), open: x.o, high: x.h, low: x.l, close: x.c };
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
    // VWAP starts again at each anchor. The library joins a line across an empty point
    // and colours a segment by the point it starts from, so the last point before a
    // new start is drawn clear: no stroke from yesterday's VWAP to today's. A future
    // says where its periods start; a stock's VWAP breaks with a gap.
    const breaks = new Set((av?.starts ?? []).map((i) => i - 1));
    const broken = (a: Array<number | null> | undefined) =>
      toLine(a).map((x, i, all) =>
        "value" in x &&
        (av
          ? breaks.has(i)
          : i + 1 < all.length && !("value" in all[i + 1]) && all.slice(i + 1).some((y) => "value" in y))
          ? { ...x, color: CLEAR }
          : x,
      );
    b.lines.vwap.setData(broken(av?.vwap ?? d.vwap));
    b.lines.ema20.setData(toLine(d.ema20));
    b.lines.ema50.setData(toLine(d.ema50));
    b.lines.ema200.setData(toLine(d.ema200));
    const waveHue = stateRef.current > 0 ? p.up : stateRef.current < 0 ? p.down : p.ink3;
    b.lines.ema8.applyOptions({ color: rgba(waveHue, 0.7), visible: on("ema8") });
    b.lines.ema10.applyOptions({ color: rgba(waveHue, 0.45), visible: on("ema8") });
    b.lines.ema20.applyOptions({ color: rgba(p.ma20, 0.9), visible: on("ema20") });
    b.lines.ema50.applyOptions({ color: rgba(p.ma50, 0.9), visible: on("ema50") });
    b.lines.vwap.applyOptions({ color: rgba(p.ink2, 0.85), visible: on("vwap") });
    b.lines.ema200.applyOptions({ color: rgba(p.ink3, 0.9), visible: on("ema200") });

    // The deviation bands, ±1σ outward, as many as the reader asked for: about a
    // future's VWAP from its anchor, or a stock's from 09:30.
    const bandVwap = av?.vwap ?? d.vwap;
    const bandSd = av?.sd ?? d.vwap_sd ?? null;
    const shownBands = bandSd && on("vwap") ? bandsRef.current : 0;
    b.lines.bands.forEach(({ up, dn }, k) => {
      const m = k + 1;
      const show = m <= shownBands;
      const side = (sign: 1 | -1) => (bandSd ? bandVwap.map((v, i) => (v == null || bandSd[i] == null ? null : v + sign * m * (bandSd[i] as number))) : []);
      up.setData(show ? broken(side(1)) : []);
      dn.setData(show ? broken(side(-1)) : []);
      const hue = rgba(p.ink3, BAND_ALPHA[k]);
      up.applyOptions({ color: hue, visible: show });
      dn.applyOptions({ color: hue, visible: show });
    });

    const vol: HistogramData<Time>[] = d.bars.map((x, i) => ({
      time: t_(x.t),
      value: x.v,
      color: rgba(x.c >= x.o ? p.up : p.down, kinds[i] === null ? 0.32 : 0.14),
    }));
    b.volume.setData(vol);
    b.volume.applyOptions({ visible: on("vol") });

    // Shaded runs of extended-hours bars, and a hairline at each 09:30; on a future,
    // a hairline at each 18:00 reopen and no shading.
    const shades: OverlayData["shades"] = [];
    const opens: number[] = [];
    if (fut) {
      const at = new Map(d.bars.map((x, i) => [x.t, i]));
      for (const t of d.opens ?? []) {
        const i = at.get(t);
        if (i !== undefined && i > 0) opens.push(i);
      }
    } else {
      const ext = shadeRuns(kinds);
      for (const r of ext.runs) {
        const hue = r.kind === "pre" ? p.shadePre : p.shadePost;
        if (hue) shades.push({ from: r.from, to: r.to, hue });
      }
      opens.push(...ext.opens);
    }

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
        // An earlier day's line has no name, as the Pine's has none: only the last day's
        // four are named, on the price axis, so there is one PDH on the chart to read.
        hue: rgba(h.key === "PDH" || h.key === "PMH" ? p.up : p.down, 0.4),
        dashed: pm,
      });
    }
    // The levels. Near ones help set the scale; a level far off must not crush the candles.
    for (const l of b.levels) b.candles.removePriceLine(l);
    b.levels = [];
    const L = d.levels;
    const forming = !L.pm_done;
    const list: LevelLine[] = [];
    /*
     * ONE NAMED SET, THE LAST DAY'S ON THE CHART, AS THE OWNER'S PINE DRAWS THEM (owner,
     * 2026-11-14: "i think there is a bug with the pdh/l and pmh/l levels on the stocks
     * charts", then, of the first fix, "you now have double ups of the levels"). The
     * collector sends the levels of the day the last bar is in (scan.chart_levels,
     * futures.day_levels): on a weekend Friday's, as it traded against them, not
     * Monday's over Friday's candles. They were the library's price lines, which cross
     * the whole chart, so today's also ran back over yesterday. Each now starts at its
     * day's first bar (`pd_from`, `pm_from`) and runs to the right edge, drawn here; the
     * library keeps the name on the price axis. Earlier days' lines are plain. A reply
     * without the starts (the daily view, an older collector) draws lines across.
     */
    const startOf = (from: number | null | undefined): number | undefined => {
      if (from == null || tfNow === "D") return undefined;
      const i = d.bars.findIndex((x) => x.t >= from);
      // Nothing on the chart from there yet: a stub at the last bar, so the level and its
      // label are still on the page.
      return i < 0 ? d.bars.length - 1 : i;
    };
    const pdFrom = startOf(L.pd_from);
    const pmFrom = startOf(L.pm_from);
    const add = (key: string, v: number | null | undefined, hue: string, dashed: boolean, faint: boolean, layer: Layer | null, title: string, from?: number) => {
      if (v == null) return;
      if (layer && !on(layer)) return;
      list.push({ key, v, hue, dashed, faint, layer, title, from });
    };
    add("PDH", L.pdh, p.up, false, false, "pd", "PDH", pdFrom);
    add("PMH", L.pmh, p.up, true, forming, "pm", forming ? "PMH ·f" : "PMH", pmFrom);
    add("PML", L.pml, p.down, true, forming, "pm", forming ? "PML ·f" : "PML", pmFrom);
    add("PDL", L.pdl, p.down, false, false, "pd", "PDL", pdFrom);
    for (const l of list) {
      if (l.from === undefined) continue;
      segments.push({ i0: l.from, i1: d.bars.length - 1, v: l.v, hue: rgba(l.hue, l.faint ? 0.5 : 0.85), dashed: l.dashed, toEdge: true });
    }
    b.overlays.set({
      shades,
      opens,
      // The reopen is the only mark a future's chart carries, so it is drawn a step firmer.
      openHue: fut ? rgba(p.ink3, 0.55) : p.ring2,
      wave: on("ema8") ? { upper: d.ema8, lower: d.ema10, hue: rgba(waveHue, 0.16) } : null,
      segments,
      font: getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || "monospace",
    });
    const band = emRef.current ?? d.em ?? null;
    if (band) {
      add("EMH", band.hi, p.ink3, true, false, null, band.label);
      add("EML", band.lo, p.ink3, true, false, null, "EM");
    }
    // A futures book's ladder: the flip and the walls, the settle, the opening range.
    const walls: WallTag[] = [];
    for (const x of d.lines ?? []) {
      // The walls and the flip go when this chart's GEX switch is off; the settle and
      // the opening range are not gamma and stay.
      if (!gexRef.current && GEX_TONES.has(x.tone)) continue;
      const hue = x.tone === "call" ? p.up : x.tone === "put" ? p.down : x.tone === "flip" ? p.ink2 : p.ink3;
      // A wall's label is the chart's to draw, its rank as triangles (Overlays, lib/walls):
      // the line itself carries no title.
      const wall = wallRank(x.label);
      if (wall) walls.push({ v: x.v, word: wall.word, n: wall.n, up: wall.up, bg: rgba(hue, 0.85), fg: contrastInk(hue) });
      list.push({ key: `L:${x.label}`, v: x.v, hue, dashed: true, faint: x.tone === "ref", layer: null, title: wall ? "" : x.label });
    }
    b.overlays.setWalls(
      walls,
      Math.round(11 * (Number(getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")) || 1)),
      getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || "monospace",
    );
    levelList.current = list;
    for (const l of list) {
      b.levels.push(
        b.candles.createPriceLine({
          price: l.v,
          color: rgba(l.hue, l.faint ? 0.5 : 0.85),
          lineWidth: 1,
          lineStyle: l.key.startsWith("EM") ? LineStyle.Dotted : l.dashed ? LineStyle.Dashed : LineStyle.Solid,
          // A level drawn from its own start is the overlay's line; this keeps its label.
          lineVisible: l.from === undefined,
          axisLabelVisible: true,
          title: l.title,
        }),
      );
    }
    scaleLevels.current = list.filter((l) => !l.key.startsWith("EM") && !l.key.startsWith("L:")).map((l) => l.v);

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
      // A future frames from its last 18:00 reopen, but no more than 300 bars back:
      // a whole futures day of one-minute bars is too fine to read at once.
      const n = d.bars.length;
      const lastT = d.bars[n - 1].t;
      const pre = [...d.sessions].reverse().find((s) => s.kind === "pre" && s.from <= lastT);
      let start = fut ? (opens.length ? opens[opens.length - 1] : -1) : pre ? d.bars.findIndex((x) => x.t >= pre.from) : -1;
      start = tfNow === "D" ? Math.max(0, n - 70) : start < 0 ? Math.max(0, n - 80) : Math.max(0, start - 6, fut ? n - 300 : 0);
      const open = { from: start, to: n + 5 };
      ts.setVisibleLogicalRange(open);
      /*
       * AND AGAIN ONCE THE CHART HAS ITS SIZE (design review, 2026-11-11). The first
       * paint lands before the price scale has taken its width, and the window set
       * then came out with every bar pressed into the right third of the slide-out
       * and the rest of it empty; picking the timeframe again drew it properly, so
       * the window was right and the moment was wrong. It is set again over the next
       * frames, and a repaint inside that half second keeps it rather than whatever
       * the chart reported in between.
       */
      opening.current = { range: open, until: performance.now() + 600 };
      const again = () => {
        if (built.current === b && opening.current?.range === open) ts.setVisibleLogicalRange(open);
      };
      requestAnimationFrame(() => requestAnimationFrame(again));
      window.setTimeout(again, 250);
    } else if (opening.current && performance.now() < opening.current.until) {
      ts.setVisibleLogicalRange(opening.current.range);
    } else if (view) {
      ts.setVisibleLogicalRange(view);
    }
    requestAnimationFrame(refreshOffScale);
  }, [refreshOffScale]);

  // ---- build once; every later change is applied in place -----------------------
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    // The area round the canvas is what carries the chart's colours (`data-colors`).
    const area = el.parentElement ?? el;
    const p = readPalette(area);
    palette.current = p;
    const font = getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim();
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: p.bg },
        textColor: p.ink3,
        fontFamily: font || "monospace",
        // The chart's area stays 1:1 where Luminous draws the page larger (`qt-chart`),
        // so its labels take the page's scale here instead, or they read a size small.
        fontSize: Math.round(11 * (Number(getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")) || 1)),
        attributionLogo: true,
      },
      // No grid (owner, 2026-11-13: "can we get rid of the grid lines on the charts"): the
      // level lines and the price scale carry the reading.
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
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
      priceLineColor: p.priceLine,
      priceLineStyle: LineStyle.Dotted,
      autoscaleInfoProvider: autoscale,
    });
    const quiet = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, lineWidth: 1 } as const;
    const lines: LineSet = {
      ema8: chart.addSeries(LineSeries, quiet),
      ema10: chart.addSeries(LineSeries, quiet),
      vwap: chart.addSeries(LineSeries, { ...quiet, lineStyle: LineStyle.Dashed }),
      // The 200 EMA never sets the scale: a name that gapped 25% would have its
      // candles crushed into a sliver for a line a long way off. The 20 and the 50
      // the same: on the morning of a gap both are still yesterday's prices.
      ema20: chart.addSeries(LineSeries, { ...quiet, visible: false, autoscaleInfoProvider: () => null }),
      ema50: chart.addSeries(LineSeries, { ...quiet, visible: false, autoscaleInfoProvider: () => null }),
      ema200: chart.addSeries(LineSeries, { ...quiet, autoscaleInfoProvider: () => null }),
      // The bands never set the scale either: a 3σ band would squeeze the candles.
      bands: [1, 2, 3].map(() => ({
        up: chart.addSeries(LineSeries, { ...quiet, visible: false, autoscaleInfoProvider: () => null }),
        dn: chart.addSeries(LineSeries, { ...quiet, visible: false, autoscaleInfoProvider: () => null }),
      })),
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
        out.textContent = restingLine(d);
        return;
      }
      const x = d.bars[i];
      const when = (d.tf ?? tfRef.current) === "D" ? `${wd(x.t)} ${md(x.t)}` : hm(x.t);
      const parts = [when, `O ${num(x.o)}`, `H ${num(x.h)}`, `L ${num(x.l)}`, `C ${num(x.c)}`];
      if (x.v) parts.push(`V ${compact(x.v)}`);
      const av = d.vwaps?.[anchorRef.current];
      const v = (av?.vwap ?? d.vwap)[i];
      const sd = (av?.sd ?? d.vwap_sd)?.[i];
      const shown = layersRef.current;
      if (v != null && shown.includes("vwap")) parts.push(`VWAP ${num(v)}`);
      if (v != null && sd != null && shown.includes("vwap") && bandsRef.current > 0) parts.push(`σ ${num(sd)}`);
      // Each average that is drawn, in its own order.
      for (const l of EMA_LAYERS) {
        const e = d[l]?.[i];
        if (e != null && shown.includes(l)) parts.push(`${EMA_LEN[l]}EMA ${num(e)}`);
      }
      out.textContent = parts.join("  ");
    });
    let raf = 0;
    const onRange = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(refreshOffScale);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    // A new theme, a new interface or a new choice of chart colours: the same chart,
    // recoloured in place.
    const repaintColors = () => {
      const next = readPalette(area);
      if (JSON.stringify(next) === JSON.stringify(palette.current)) return;
      palette.current = next;
      chart.applyOptions({
        layout: { background: { type: ColorType.Solid, color: next.bg }, textColor: next.ink3 },
        rightPriceScale: { borderColor: next.ring },
        timeScale: { borderColor: next.ring },
        crosshair: { vertLine: { color: next.ink3 }, horzLine: { color: next.ink3 } },
      });
      candles.applyOptions({ upColor: next.up, downColor: next.down, wickUpColor: next.up, wickDownColor: next.down, priceLineColor: next.priceLine });
      paint();
    };
    recolor.current = repaintColors;
    const obs = new MutationObserver(repaintColors);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["style", "class", "data-theme"] });

    return () => {
      cancelAnimationFrame(raf);
      obs.disconnect();
      recolor.current = () => {};
      chart.remove();
      built.current = null;
    };
  }, [paint, refreshOffScale]);

  // ---- the whole series, on its slow poll ----------------------------------------
  const barsKey = `${barsUrl ?? `/api/scanner/bars/${encodeURIComponent(sym)}`}?tf=${tf}`;
  /** A series in hand: held, and drawn. */
  const take = useCallback(
    (d: ScanBars) => {
      data.current = d;
      onLevelsRef.current?.(d.levels ?? null);
      setAnchored(d.vwaps != null);
      // A stock's bands can be picked before the bell, while there is no VWAP yet to
      // draw them about; a daily bar has neither.
      setHasBands(d.vwaps != null || (d.vwap_sd != null && d.tf !== "D"));
      setReady(true);
      paint();
      if (readout.current && readout.current.dataset.touched !== "1") readout.current.textContent = restingLine(d);
    },
    [paint],
  );
  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(barsKey, { cache: "no-store" });
      const d = (await r.json()) as ScanBars & { offline?: { reason: string } };
      if (mine !== seq.current) return;
      setErr(d.offline ? d.offline.reason : d.ok ? null : (d.error ?? "no bars"));
      if (!d.ok) return;
      take(keepRead(barsKey, d));
    } catch (e) {
      if (mine === seq.current) setErr(e instanceof Error ? e.message : "request failed");
    }
  }, [barsKey, take]);

  useEffect(() => {
    // A new name or timeframe starts blank rather than showing the last one's candles,
    first.current = true;
    data.current = null;
    setReady(false);
    setErr(null);
    setLive(null);
    // or on its own last series this session (lib/lastRead): a return to a page drew the
    // chart's loader for a second over candles it had just shown. The read below
    // replaces them, the view as it was left.
    const kept = lastRead<ScanBars>(barsKey);
    if (kept) take(kept);
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
  }, [load, tf, barsKey, take]);

  // ---- the last trade, every second ----------------------------------------------
  useEffect(() => {
    if (!streaming) return;
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
        for (const a of [d.ema8, d.ema9, d.ema10, d.vwap, d.ema200 ?? [], d.ema20 ?? [], d.ema50 ?? [], d.vwap_sd ?? []]) a.push(null);
        for (const v of Object.values(d.vwaps ?? {})) {
          v.vwap.push(null);
          v.sd.push(null);
        }
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
      step(d.ema20, 20, b.lines.ema20);
      step(d.ema50, 50, b.lines.ema50);
      step(d.ema200, 200, b.lines.ema200);
      if (readout.current && readout.current.dataset.touched !== "1") readout.current.textContent = restingLine(d);
    };
    const run = async () => {
      if (dead) return;
      if (document.visibilityState === "visible") {
        try {
          const r = await fetch(tickUrl ?? `/api/scanner/tick/${encodeURIComponent(sym)}`, { cache: "no-store" });
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
  }, [sym, streaming, tickUrl]);

  // A layer, the anchor, the bands or the GEX switch toggled, or the row's state changed: repaint what is held.
  useEffect(() => {
    paint();
  }, [layers, anchor, bands, gex, state, em?.hi, em?.lo, paint]);

  // The chart's colours were chosen, on this chart or another: the area carries the new
  // ones by the time this runs, so they are read again and the chart repainted.
  useEffect(() => {
    recolor.current();
  }, [colors]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className={cn("flex shrink-0 items-center gap-x-3", head ? "min-w-0 px-3 py-1.5" : "flex-wrap gap-y-1.5 px-4 py-2")}>
        {head ?? <ChartControls prefs={prefs} future={Boolean(barsUrl)} anchored={anchored} hasBands={hasBands} state={state} />}
        <LiveChip t={live} short={head != null} />
      </div>
      {/* `qt-chart`: Luminous draws the page 10% larger on a wide window and sets this
          area back to 1:1, so the canvas stays sharp and the crosshair sits under the
          pointer (globals.css, "Luminous, turned up"). */}
      <div className="qt-chart relative min-h-0 flex-1" data-colors={colors}>
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
            <HelmLoader label={`Loading the ${TF_LABEL[tf] ?? tf} chart`} size={40} className="absolute inset-0" />
          ))}
      </div>
    </div>
  );
}

/**
 * The chart's toolbar: the timeframes and one menu, Indicators, that holds everything
 * the chart can draw. The same on every chart. Over one chart it is that chart's own
 * (ScanChart draws it); over a grid it is drawn once and every chart follows it.
 * A fragment, so it sits in whatever row it is put in.
 */
export function ChartControls({
  prefs,
  future = false,
  anchored = false,
  hasBands,
  state = 0,
  menusLeft = true,
}: {
  prefs: ChartPrefs;
  /** One toolbar over several charts (Multicharts). Accepted; the note it worded is gone. */
  shared?: boolean;
  /** A futures book: one more switch, for its gamma lines. */
  future?: boolean;
  /** These bars carry anchored VWAPs: a futures book off its daily view. */
  anchored?: boolean;
  /** There is a deviation to draw bands from. */
  hasBands: boolean;
  /** The row's level state, for the wave's swatch; a toolbar over several charts has none. */
  state?: -2 | -1 | 0 | 1 | 2;
  /** Menus hang from their left edge (a chart's own row) or their right (the end of a bar). */
  menusLeft?: boolean;
}) {
  const { tf, setTf, layers, setLayers, anchor, setAnchor, bands, setBands, gex, setGex } = prefs;
  const colors = useChartColors();
  const toggle = (l: Layer) => setLayers((was) => (was.includes(l) ? was.filter((x) => x !== l) : [...was, l]));
  const setLayer = (l: Layer, on: boolean) => setLayers((was) => (was.includes(l) === on ? was : on ? [...was, l] : was.filter((x) => x !== l)));
  const emasOn = EMA_LAYERS.filter((l) => layers.includes(l));
  const vwapOn = layers.includes("vwap");
  // The swatch beside each average is the line's own colour: the wave takes the row's side.
  const emaHue = (l: (typeof EMA_LAYERS)[number]) =>
    l === "ema8" ? (state > 0 ? "var(--call-fig)" : state < 0 ? "var(--put-fig)" : "var(--ink-3)") : l === "ema20" ? "var(--desk-markets)" : l === "ema50" ? "var(--desk-macro)" : "var(--ink-3)";

  const strip = (
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
          {TF_LABEL[t] ?? t}
        </button>
      ))}
    </span>
  );
  /*
   * EACH AVERAGE ITS OWN ROW, NO BOX ROUND THE FOUR (owner, 2026-11-14: "on the indicators
   * card im not a fan of the huge box for all ema's", then, after a row of short switches,
   * "i prefer it the old way but without the one single box for all"). The rows are as they
   * were, the swatch, the name and the note; the one `seg` box that held all four is gone,
   * and each row is a pill of its own.
   */
  const averages = (
    <div>
      <p className="qt-cap mb-1 text-[10px] text-ink-3">Moving averages</p>
      <div className="flex flex-col gap-1" role="group" aria-label="Moving averages">
        {EMA_LAYERS.map((l) => (
          <button
            key={l}
            type="button"
            title={LAYER_TITLE[l]}
            onClick={() => toggle(l)}
            aria-pressed={layers.includes(l)}
            {...segItem(layers.includes(l), { className: "w-full justify-between gap-3 border border-ring-2" })}
          >
            <span className="flex items-center gap-2">
              {/* `chart-hue`: the swatch takes the chart's colours, as the line it stands for does. */}
              <span aria-hidden data-colors={colors} className="chart-hue h-[2px] w-[14px] shrink-0 rounded-full" style={{ background: emaHue(l) }} />
              {LAYER_NAME[l]}
            </span>
            {EMA_NOTE[l] && <span className="text-[10.5px] text-ink-3">{EMA_NOTE[l]}</span>}
          </button>
        ))}
      </div>
    </div>
  );
  /*
   * VWAP'S OWN SETTINGS SIT UNDER IT (owner, 2026-11-13: "make the vwap deviations bands
   * section looks like a subsection of vwap and not it's own"). The anchor and the bands
   * were headed sections of their own, level with VWAP and the averages; they are VWAP's,
   * so they hang from its switch on a rule, in sentence case, and fade while it is off.
   */
  const vwap = (
    <div>
      <Choice label="VWAP" options={SHOW_CHOICES} value={vwapOn ? "on" : "off"} set={(v) => setLayer("vwap", v === "on")} />
      {(anchored || hasBands) && (
        <div
          className={cn("mt-2 ml-[5px] flex flex-col gap-2 border-l border-ring-2 pl-3", !vwapOn && "opacity-50")}
          title={vwapOn ? undefined : "VWAP is off: these apply when it is on"}
        >
          {anchored && <SubChoice label="Anchored at" options={ANCHOR_CHOICES} value={anchor} set={setAnchor} />}
          {hasBands && <SubChoice label="Deviation bands" options={BAND_CHOICES} value={bands} set={setBands} />}
        </div>
      )}
    </div>
  );
  // On or off and nothing more: the levels and volume are switches.
  const switches = (
    <span className="seg shrink-0" role="group" aria-label="Levels and volume">
      {SWITCH_LAYERS.map((l) => (
        <button key={l} type="button" title={LAYER_TITLE[l]} onClick={() => toggle(l)} aria-pressed={layers.includes(l)} {...segItem(layers.includes(l), { className: "text-[10.5px]" })}>
          {LAYER_NAME[l]}
        </button>
      ))}
      {/* A futures chart draws the gamma levels as well: one more switch, for the chart alone. */}
      {future && (
        <button type="button" title="The gamma levels: the call walls, the put walls and the flip" onClick={() => setGex((was) => !was)} aria-pressed={gex} {...segItem(gex, { className: "text-[10.5px]" })}>
          GEX
        </button>
      )}
    </span>
  );
  const colours = <Choice label="Chart colours" options={CHART_COLORS} value={colors} set={setChartColors} />;

  /*
   * THE TIMEFRAMES AND ONE MENU, WHEREVER THE CHART IS. The button names the averages
   * and VWAP that are on, so what the chart is drawing is still read without opening
   * it; a future's says where its VWAP is anchored too.
   */
  const named = [
    emasOn.length ? `EMA ${emasOn.map((l) => EMA_LEN[l]).join(" · ")}` : null,
    vwapOn ? `VWAP${anchored ? ` ${ANCHOR_WORD[anchor]}` : ""}${bands && hasBands ? ` ±${bands}σ` : ""}` : null,
  ].filter(Boolean);
  return (
    <>
      {strip}
      {/* 308 wide: a future's four switches (the three and GEX) sit on one line. */}
      <Menu left={menusLeft} width={308} label={<span className="fig text-[10.5px]">Indicators · {named.length ? named.join(" · ") : "none"}</span>}>
        {averages}
        {vwap}
        <div>
          <p className="qt-cap mb-1 text-[10px] text-ink-3">{future ? "Levels, volume and gamma" : "Levels and volume"}</p>
          {switches}
        </div>
        {colours}
        {/* No note at the foot (owner, 2026-11-13: "can remove this from the indicator pop
            up"): how the averages, VWAP, the signals and the colours behave was told there. */}
      </Menu>
    </>
  );
}

/** A setting that belongs to the one above it (VWAP's anchor and bands): a quieter label, no caps. */
function SubChoice<T extends string | number>({
  label,
  options,
  value,
  set,
}: {
  label: string;
  options: ReadonlyArray<{ value: T; label: string }>;
  value: T;
  set: (v: T) => void;
}) {
  return (
    <div>
      <p className="mb-1 text-[11px] text-ink-3">{label}</p>
      <span className="seg flex-wrap">
        {options.map((o) => (
          <button key={String(o.value)} type="button" onClick={() => set(o.value)} {...segItem(value === o.value)}>
            {o.label}
          </button>
        ))}
      </span>
    </div>
  );
}

/**
 * How fresh the chart is, on its face: a live trade seconds old, the spark layer's,
 * or the bars alone — and overnight, the last print, which is not on the candles.
 * `short` is the form under a grid's chart name: the mark and the word, no overnight print.
 */
function LiveChip({ t, short = false }: { t: TickPayload | null; short?: boolean }) {
  let word = "bars only";
  let hue = "bg-ink-4";
  let title = "No live trades for this name right now: the chart is on its slow poll of the bars.";
  if (t?.ok && t.at != null && t.session) {
    const age = t.age_sec ?? 0;
    if (age < 90) {
      word = age < 10 ? `live ${Math.max(0, Math.round(age))}s` : `${Math.round(age)}s ago`;
      hue = age < 10 ? "bg-call-fig" : "bg-flip-fig";
      title =
        t.via === "etf"
          ? `${t.proxy ?? "The ETF"}'s last trade in ${t.sym}'s prices (× ${t.ratio?.toFixed(4) ?? "the ratio"}): CME's own bars run ten minutes behind, so the minutes since are ${t.proxy ?? "the ETF"}'s, scaled. Between 04:00 and 17:00 ET.`
          : t.via === "spark"
            ? "The last trade, from the five-second quote layer"
            : "The last trade, from the live stream, laid on the last candle";
      if (t.via === "etf" && t.source === "bars") {
        // The ETF's newest minute bar stood in for a trade the stream did not send.
        word = "≤1 min";
        hue = "bg-flip-fig";
        title = `${t.proxy ?? "The ETF"}'s newest one-minute bar in ${t.sym}'s prices: the live stream sends no trades for ${t.proxy ?? "it"}, so the last candle is up to a minute behind. CME's own bars run ten minutes behind.`;
      }
      if (t.via === "etf" && !short) word = `${word} · via ${t.proxy}`;
    }
  } else if (t && !t.ok && t.sym && ["NQ", "ES", "GC", "SIL", "CL"].includes(t.sym)) {
    word = "10 min delayed";
    title = "CME's bars run ten minutes behind. Between 04:00 and 17:00 ET the minutes since come from the tracking ETF; outside those hours there is no live fill.";
  }
  return (
    <span className="fig ml-auto flex shrink-0 items-center gap-2 text-[11px] text-ink-3" title={title}>
      {t?.overnight && !short && (
        <span title="The last overnight print. Overnight trades stay out of the candles and the levels.">
          overnight <span className="text-ink-2">{num(t.overnight.price)}</span>
        </span>
      )}
      <span aria-hidden className={cn("inline-block h-[6px] w-[6px] rounded-[1px]", hue)} />
      {word}
    </span>
  );
}
