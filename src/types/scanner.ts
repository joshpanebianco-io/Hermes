import type { Frame, SourceStatus } from "@/types/terminal";

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
    /** The VIX against its own month (volterm.vix_month). Absent from an older collector. */
    month?: { pctile: number; lo: number; hi: number; days: number } | null;
  };
  band: "grind" | "normal" | "elevated" | "stressed" | null;
  /** quiet / heavy inside normal (the median, 18), panic inside stressed (35) — words, never score. */
  sub?: "quiet" | "heavy" | "panic" | null;
  spy_em_pct: number | null;
  tape: { SPY: TapeRow | null; QQQ: TapeRow | null; IWM: TapeRow | null };
  bias: Side | null;
  confirm: "confirm" | "divergence" | "risk_off" | "chop" | null;
  event: { title: string; et: string; in_min: number; score: number } | null;
  notes: string[];
  /** How many independent signals agree with the bias — computed, never the model's. */
  conviction?: Conviction | null;
}

/** One signal in the tape's conviction count. */
export interface ConvictionVote {
  key: string;
  label: string;
  value: string;
  vote: Side | "neutral";
  note: string;
}

export interface Conviction {
  bias: Side | null;
  agree: number;
  against: number;
  neutral: number;
  total: number;
  grade: "strong" | "moderate" | "weak" | "none";
  max_conviction: 1 | 2 | 3 | 4 | 5;
  votes: ConvictionVote[];
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
  kind:
    | "earnings"
    | "event"
    | "filing"
    | "news"
    | "extended"
    | "fuel"
    | "gap"
    | "halt"
    | "frame"
    | "short_interest"
    | "catalyst";
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
  /** Set when the pool put this name on the list today (sources/pool.py). */
  promoted?: Promoted | null;

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
    /** The 200 EMA on ten-minute bars — the side filter (structure.py). Absent from an older collector. */
    ema200?: number | null;
  };
  progress: { pdh: number | null; pdl: number | null; pmh: number | null; pml: number | null };
  broken: { pdh: boolean; pdl: boolean; pmh: boolean; pml: boolean };
  lvl_state: -2 | -1 | 0 | 1 | 2;
  trend: -1 | 0 | 1;
  /** 1 above the ten-minute 200 EMA, -1 below, 0 on it or unknown. */
  trend200?: -1 | 0 | 1;
  ema200_slope?: "rising" | "falling" | "flat" | null;
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
  /** The name's options, from Cboe's delayed chain. Null until the first chain arrives. */
  options?: OptionsCtx | null;
  /** Twenty-session average daily volume. */
  adv20?: number | null;
  /** Today's pre-market from Nasdaq's extended-trading feed (about fifteen minutes delayed). */
  premkt?: {
    volume: number | null;
    pct_adv: number | null;
    high: number | null;
    low: number | null;
    last: number | null;
    asof: string | null;
  } | null;
  /** Big caps in the same sector reporting from today through three trading days out. */
  peers?: Array<{ sym: string; date: string; when: string; days: number }>;
  /** The daily levels (frame.frame_of) and their read against the live print. Absent from an older collector. */
  frame?: Frame | null;
  frame_read?: FrameRead | null;
  /** Short interest and float from Yahoo's summary (sources/shortint). */
  short?: ShortInterest | null;
  /** The first targets by the plan's rule (targets.py), nearest first. */
  targets?: Target[];
  /**
   * The record line (scanscore.record_for): settled signals of the kind this
   * setup implies, the side and the score band, from ten of them; `small`
   * under thirty. Null until there are enough.
   */
  record?: {
    kind: "L" | "E";
    side: Side;
    band: "<40" | "40-59" | "60+";
    n: number;
    win_1r: number | null;
    avg_close_r: number | null;
    sessions: number | null;
    small: boolean;
  } | null;
}

/** The daily frame against the live print (frame.read). */
export interface FrameRead {
  /** Up above both the 20 and 50-day, down below both, mixed between. */
  trend: "up" | "down" | "mixed" | null;
  above20: boolean | null;
  above50: boolean | null;
  above200: boolean | null;
  /** Distance from the 52-week high and low, %. */
  wk52_hi_pct: number | null;
  wk52_lo_pct: number | null;
  pw: "above" | "inside" | "below" | null;
  text: string | null;
}

export interface ShortInterest {
  /** Share of the float sold short, %. */
  pct_float: number | null;
  days_to_cover: number | null;
  shares_short: number | null;
  prior_month: number | null;
  float_shares: number | null;
  /** FINRA's settlement date the figure is as of. */
  as_of: string | null;
}

export interface Target {
  label: string;
  price: number;
}

/** Today's options volume against open interest, read for which way it leans. */
export interface OptionsFlow {
  call_vol: number;
  put_vol: number;
  pc_vol: number | null;
  call_oi: number;
  put_oi: number;
  vol_oi: number | null;
  lean: "calls" | "puts" | "balanced" | null;
  top: Array<{ strike: number; right: "C" | "P"; expiry: string; volume: number; oi: number; oi_chg?: number | null }>;
  /** Open interest since the previous session, each side (sources/options.OiLog); null until a second session is logged. */
  oi_chg_calls?: number | null;
  oi_chg_puts?: number | null;
  oi_prev_day?: string | null;
  /** Today's chain volume against the name's own 20-session average. */
  vol_avg20?: number | null;
  vol_x?: number | null;
  vol_days?: number;
  /** vol_x at or past 2 with at least a hundred contracts. */
  unusual?: boolean;
}

/* -------------------------------------------------------------------------- */
/* Options — the stocks desk trades the options, not the shares                */
/* -------------------------------------------------------------------------- */

/**
 * One suggested contract for the row's side. `front` is the nearest expiry —
 * today's while it is listed, until 15:00 ET on SPY / QQQ / IWM and 14:00 ET
 * on a single name; `weekly` is the nearest with two trading days or more to
 * run. Which of the two the desk trades is `OptionsCtx.pick` (the collector's
 * expiry rule — `ExpiryRule`). A `long` is the strike nearest 0.60 delta; a
 * `spread` buys that and sells the strike nearest 0.30 delta in the same expiry.
 */
export interface OptContract {
  key: "front" | "weekly";
  kind: "long" | "spread";
  right: "C" | "P";
  expiry: string;
  dte: number;
  strike: number;
  short_strike: number | null;
  symbol: string;
  short_symbol: string | null;
  bid: number;
  ask: number;
  mid: number;
  delta: number;
  /** Per day; a spread's is the net of its legs. */
  theta: number | null;
  /** The long leg's implied volatility, in percent (as iv30 is). */
  iv: number | null;
  /** A spread's short leg's implied volatility; null on a long. */
  short_iv?: number | null;
  /** Bid-ask as a % of mid — a spread's natural market (long bid − short ask … long ask − short bid). */
  spread_pct: number | null;
  max_value: number | null;
  /**
   * The stock-level trade the contract is sized against: the latest signal's
   * price and stop, else the setup's entry and that ∓ the Pine buffer, else the
   * last print and one ATR — and how it was found.
   */
  stock_entry?: number | null;
  stock_stop?: number | null;
  risk_basis?: string | null;
  /** $ per share from the entry to the stop. */
  stock_risk: number | null;
  /** The contract's estimated mid with the stock at the entry. */
  entry_mid?: number | null;
  /**
   * What the stop costs one contract: its value at the entry minus its value at
   * the stop (re-marked by delta and gamma), plus half its bid-ask, capped at its
   * price at the entry.
   */
  risk_per_contract: number | null;
  /**
   * The contract re-marked to the stock's live price (Cboe's quote is fifteen
   * minutes old): the quoted mid moved by delta and gamma. Only 09:30 to the
   * close, on a same-day chain; null otherwise.
   */
  est_mid?: number | null;
  est_delta?: number | null;
  /** The live stock price the estimate is for, and the price Cboe's quote was taken at. */
  est_spot?: number | null;
  quote_spot?: number | null;
  /**
   * The contract at the first target (targets[0]): its value there — by delta
   * and gamma inside the re-mark range, intrinsic value as a floor beyond it
   * (`target_basis` says which) — the reward per contract after half the
   * bid-ask, and that against the risk: the option's own R.
   */
  target_price?: number | null;
  target_label?: string | null;
  target_mid?: number | null;
  target_basis?: string | null;
  reward_per_contract?: number | null;
  r_multiple?: number | null;
  /** This is the structure the engine picks for the expiry, by R. */
  better_r?: boolean;
  note: string;
}

export interface OptTerm {
  expiry: string;
  dte: number;
  /** At-the-money implied volatility for the expiry, %. */
  iv: number;
}

/** The earnings number: the move the chain prices for the report against the last realised. */
export interface EarningsMove {
  implied: {
    report: string;
    when: string | null;
    expiry: string;
    dte: number;
    /** The covering expiry's straddle, % of spot. */
    pct: number;
    straddle: number;
    /** Net of the expiry before the report — the event alone, about. */
    clean_pct: number | null;
    before_expiry: string | null;
    before_pct: number | null;
  } | null;
  /** Close to close across each past report, newest first, the reaction day picked by volume. */
  realised: Array<{ date: string; reaction: string; pct: number }>;
  avg_abs: number | null;
  max_abs: number | null;
}

export interface OptExpectedMove {
  key: "front" | "weekly";
  expiry: string;
  dte: number;
  straddle: number;
  pct: number;
  lo: number;
  hi: number;
}

export interface OptionsCtx {
  ok: boolean;
  error?: string | null;
  asof: string | null;
  age_min: number | null;
  iv30: number | null;
  rv20: number | null;
  iv_rv: number | null;
  premium: "cheap" | "fair" | "rich" | null;
  iv_rank: number | null;
  iv_pct: number | null;
  iv_days: number;
  skew: number | null;
  em: OptExpectedMove[];
  liquidity: {
    spread_pct: number | null;
    oi: number | null;
    volume: number | null;
    grade: "good" | "ok" | "poor" | null;
  };
  zero_dte: boolean;
  /** The contract the expiry rule picks for this name — the front on SPY / QQQ / IWM, else the weekly. */
  pick?: "front" | "weekly" | null;
  earnings_in: string | null;
  contracts: OptContract[];
  /** Long or spread for the pick expiry: by R at the first target when both are priced, else by premium. */
  structure?: { kind: "long" | "spread"; by: "r" | "premium"; long_r: number | null; spread_r: number | null } | null;
  targets?: Target[];
  /** The name's own term structure, front to back. */
  term?: OptTerm[];
  earnings_move?: EarningsMove | null;
  flow?: OptionsFlow | null;
}

/** The expiry rule in the collector's words (optcalc.expiry_rule) — what Settings prints. */
export interface ExpiryRule {
  zero_dte_names: string[];
  etf_cutoff_et: string;
  single_cutoff_et: string;
  weekly_min_sessions: number;
  text: string;
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
  /** Every name the rows are built for: the pinned list, then today's promotions. */
  watchlist: string[];
  /** The owner's list alone. */
  pinned?: string[];
  /** The pool's view — today's promotions, the names in play, the marks. */
  pool?: PoolView | null;
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
  /** The options expiry rule, for Settings' copy. */
  options_rule?: ExpiryRule;
  /** The pool's view (sources/pool.py). */
  pool?: PoolView;
}

/** A name the pool promoted into the list today, and why. */
export interface Promoted {
  symbol: string;
  score: number;
  reason: string;
  /** ET, HH:MM — when the promotion happened. */
  at: string;
  /** The mark it happened at: 08:00, 09:00, 09:25 or 10:00. */
  mark: string;
  name?: string | null;
  sector?: string | null;
}

/** One name of the pool as ranked. */
export interface PoolName {
  symbol: string;
  name: string | null;
  sector: string | null;
  close: number | null;
  cap: number | null;
  score: number;
  reason: string;
  gap_atr: number | null;
  vol_pct: number | null;
  reports: string | null;
  promoted: boolean;
}

/**
 * The pool (sources/pool.py): hundreds of large caps read in one request,
 * ranked by the scanner's own in-play arithmetic, the top promoted into the
 * list at the marks. `basis` says which figures the rank reads: the
 * pre-market, the day so far, or the last session's when no session is on.
 */
export interface PoolView {
  ok: boolean;
  on: boolean;
  read_utc: string | null;
  age_min: number | null;
  source: string;
  error: string | null;
  screened: number;
  qualified: number;
  basis: "pre" | "day" | "last";
  gates: { cap_usd: number; dollar_vol_usd: number; atr_pct: number; price_usd: number; min_score: number };
  top: PoolName[];
  promoted: Promoted[];
  day: string | null;
  marks_done: string[];
  next_mark: string | null;
  /** How many names the pool may add: 40 less the pinned list. */
  slots: number;
  post_open_slots: number;
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
  /** The final bars no longer hold this signal — kept in the log, out of the record. */
  retracted?: boolean;
  retracted_ts?: string;
  /** The final bars moved its price or stop: the figures it was first logged with. */
  revised?: { price: number; stop: number | null; note: string };
  /** A finished day, settled against bars read after its bell. */
  checked?: boolean;
}

export interface ScanEvents {
  latest: number;
  events: ScanEvent[];
  /** Ids withdrawn over the last two sessions — a page that announced one says so. */
  retracted?: number[];
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

/** The chart's timeframes — 10m is the one the script's signals are read on. */
export type ChartTf = "1m" | "3m" | "5m" | "10m" | "D";

export interface ScanBars {
  ok: boolean;
  sym: string;
  tf?: ChartTf;
  error?: string;
  bars: ScanBar[];
  ema8: Array<number | null>;
  ema9: Array<number | null>;
  ema10: Array<number | null>;
  /** The 200 EMA on the chart's own bars (structure.py, 2026-10-30); null until 200 bars are held. Absent from an older collector. */
  ema200?: Array<number | null>;
  vwap: Array<number | null>;
  levels: { pdh: number | null; pdl: number | null; pmh: number | null; pml: number | null; pm_done: boolean };
  /**
   * Each earlier session's four levels over its own regular hours
   * (scan.history_levels) — the Pine's "keep previous days' levels". Absent
   * from a collector older than 2026-10-14.
   */
  history?: Array<{ key: "PDH" | "PDL" | "PMH" | "PML"; v: number; from: number; to: number; day: string }>;
  sessions: Array<{ kind: "pre" | "rth" | "post"; from: number; to: number }>;
  signals: Array<{ t: number; kind: "L" | "E" | "BO" | "E_SETUP"; side: Side; price: number }>;
}
