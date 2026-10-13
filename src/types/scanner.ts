import type { SourceStatus } from "@/types/terminal";

/**
 * The scanner's payload — GET /api/scanner on the collector.
 *
 * LE_Model.pine's scanner, served by the engine instead of drawn by
 * TradingView: the four levels (PDH / PDL / PMH / PML) and how close each name
 * is to breaking them, relative strength against SPY and QQQ scaled by each
 * name's own ATR, the 8 EMA wave, VWAP, and the (L) / (E) signals replayed on
 * confirmed ten-minute bars — joined to the tape (VIX and its curve, SPY / QQQ
 * against their own levels, the sectors, the calendar) and to each name's own
 * headlines, earnings date and SEC filings.
 *
 * EVERY FIELD MAY BE NULL. The engine never fills a gap with a guess; the panel
 * prints a dash and, where it matters, says why.
 */

export type Side = "long" | "short";
export type ScanSession = "pre" | "rth" | "post" | "closed";
export type LevelKey = "PDH" | "PDL" | "PMH" | "PML";

export type SetupState =
  | "retest"
  | "pullback"
  | "extended"
  | "approaching"
  | "chop"
  | "failed"
  | "forming";

export interface TapeRow {
  sym: string;
  last: number | null;
  chg_pct: number | null;
  /** Pre-market vs the previous close, or post-market vs today's; null in the session. */
  ext_pct: number | null;
  trend: -1 | 0 | 1;
  lvl_state: -2 | -1 | 0 | 1 | 2;
}

export interface Regime {
  vix: {
    last: number | null;
    pct: number | null;
    chg: number | null;
    ratio: number | null;
    shape: "contango" | "flat" | "backwardation" | "unknown";
    vvix: number | null;
    vvix_pct: number | null;
  };
  band: "grind" | "normal" | "elevated" | "stressed" | null;
  spy_em_pct: number | null;
  tape: { SPY: TapeRow | null; QQQ: TapeRow | null; IWM: TapeRow | null };
  bias: Side | null;
  confirm: "confirm" | "divergence" | "risk_off" | "chop" | null;
  event: { title: string; et: string; in_min: number; score: number } | null;
  notes: string[];
}

export interface ScoreRow {
  key: string;
  label: string;
  pts: number;
  max: number;
  note: string;
}

export interface ScanSignal {
  kind: "L" | "E" | "BO" | "E_SETUP";
  side: Side;
  level: LevelKey | null;
  at_et: string;
  price: number;
  note: string;
  /** The bar's open, epoch seconds — what the chart places it by. */
  t?: number;
  /** The Pine's stop idea for an (L) / (E). */
  stop?: number | null;
}

export interface ScanFlag {
  kind: "earnings" | "event" | "filing" | "news" | "extended" | "fuel" | "gap" | "halt";
  tone: "good" | "warn" | "info";
  text: string;
}

export interface ScanNews {
  title: string;
  url: string;
  publisher: string;
  utc: string | null;
  age_min: number | null;
  kind: "rating" | "earnings" | "filing" | "news";
}

export interface ScanFiling {
  form: string;
  /** EDGAR's acceptance time, ISO UTC. */
  filed: string;
  desc: string;
  url: string;
}

export interface ScanRow {
  sym: string;
  name: string | null;
  sector: string | null;
  sector_rs: number | null;
  ok: boolean;
  error: string | null;
  age_min: number | null;

  last: number | null;
  prev_close: number | null;
  chg_pct: number | null;
  ext_pct: number | null;
  volume: number | null;
  rvol: number | null;
  atr_d: number | null;
  atr_b: number | null;
  rs: { SPY: number | null; QQQ: number | null };
  rs_1h: { SPY: number | null; QQQ: number | null };

  levels: {
    pdh: number | null;
    pdl: number | null;
    pdc: number | null;
    pmh: number | null;
    pml: number | null;
    pm_done: boolean;
    vwap: number | null;
    wave_hi: number | null;
    wave_lo: number | null;
    ema8: number | null;
    day_hi: number | null;
    day_lo: number | null;
    open: number | null;
  };
  progress: { pdh: number | null; pdl: number | null; pmh: number | null; pml: number | null };
  broken: { pdh: boolean; pdl: boolean; pmh: boolean; pml: boolean };
  lvl_state: -2 | -1 | 0 | 1 | 2;
  trend: -1 | 0 | 1;
  range_used: number | null;

  setup: {
    side: Side | null;
    state: SetupState;
    level: LevelKey | null;
    /** EMA8 is the 8 EMA wave's near edge — its top for a long, its bottom for a short. */
    entry: { kind: LevelKey | "VWAP" | "EMA8"; price: number; dist_atr: number } | null;
    note: string;
  };
  signals: ScanSignal[];
  score: { total: number; side: Side | null; parts: ScoreRow[] };
  flags: ScanFlag[];
  earnings: {
    date: string;
    when: "pre" | "after" | "unspecified";
    days: number;
    eps_forecast: string | null;
    eps_actual: string | null;
    surprise_pct: number | null;
  } | null;
  news: ScanNews[];
  filings: ScanFiling[];
}

export interface ScannerPayload {
  ok: boolean;
  built_utc: string;
  status: SourceStatus | null;
  age_min: number | null;
  session: ScanSession;
  trading_day: string;
  pm_locked: boolean;
  bench: "SPY";
  watchlist: string[];
  regime: Regime;
  rows: ScanRow[];
  /** Set by the Next proxy when the collector could not be reached. */
  offline?: { reason: string; api: string };
}

export interface Watchlist {
  symbols: string[];
  default: string[];
  /** Symbols a POST dropped as malformed. */
  rejected?: string[];
  /** The collector's reason when a POST was refused. */
  error?: string;
}

/* -------------------------------------------------------------------------- */
/* Round 2: the event feed (alerts and the signal log), and one name's bars    */
/* -------------------------------------------------------------------------- */

/**
 * What a signal did afterwards, in R — one unit of the Pine's own "stop idea"
 * (the signal bar's low for a long, its high for a short). Updated as bars
 * arrive; `final` once the session has closed.
 */
export interface ScanOutcome {
  r: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  hit_1r: boolean | null;
  hit_2r: boolean | null;
  stopped: boolean | null;
  ret_30m_r: number | null;
  ret_60m_r: number | null;
  ret_close_r: number | null;
  final: boolean;
}

export interface ScanEvent {
  id: number;
  ts: string;
  bar_ts: string;
  /** `bar_ts` as epoch seconds. */
  t?: number;
  at_et: string;
  day: string;
  sym: string;
  /** (L) retest, (E) trigger, ◆ breakout, or NEAR — 90% of the way to a level. */
  kind: "L" | "E" | "BO" | "NEAR";
  side: Side;
  level: LevelKey | null;
  price: number;
  stop: number | null;
  score: number | null;
  note: string;
  /** Seen within two bars of its close. False = found by a replay after a restart — never alerted. */
  live: boolean;
  outcome: ScanOutcome | null;
}

export interface ScanEvents {
  latest: number;
  events: ScanEvent[];
  offline?: { reason: string; api: string };
}

export interface ScanStatGroup {
  key: string;
  n: number;
  win_1r: number | null;
  avg_close_r: number | null;
  avg_mfe_r: number | null;
  avg_mae_r: number | null;
}

export interface ScanStats {
  days: number;
  from: string;
  to: string;
  total: number;
  groups: ScanStatGroup[];
  offline?: { reason: string; api: string };
}

export interface ScanBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface ScanBars {
  ok: boolean;
  sym: string;
  error?: string;
  bars: ScanBar[];
  ema8: Array<number | null>;
  ema9: Array<number | null>;
  ema10: Array<number | null>;
  vwap: Array<number | null>;
  levels: { pdh: number | null; pdl: number | null; pmh: number | null; pml: number | null; pm_done: boolean };
  sessions: Array<{ kind: "pre" | "rth" | "post"; from: number; to: number }>;
  signals: Array<{ t: number; kind: "L" | "E" | "BO" | "E_SETUP"; side: Side; price: number }>;
}
