import type { Frame, SourceStatus } from "@/types/terminal";

/**
 * The scanner's payload — GET /api/scanner on the collector.
 *
 * The Pine script's scanner, served by the engine instead of drawn by
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
  /** `divergence_down` (SPY down, VIX down) is the mirror of `divergence`, since 2026-11-14. */
  confirm: "confirm" | "divergence" | "risk_off" | "divergence_down" | "chop" | null;
  event: { title: string; et: string; in_min: number; score: number } | null;
  /** False when the economic calendar is not loading: no `event` then is a gap, not a clear morning. */
  calendar_ok?: boolean | null;
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
  /** False when it cannot vote at this hour: shut or missing, which is not the same as flat. */
  live?: boolean;
}

/** One family of reads, weighed for the session (server bias.py). Absent on a plan stored before them. */
export interface ScoreFamily {
  key: string;
  label: string;
  /** The strip's short name: "Structure", "Risk". */
  short: string;
  /** Its share of the session's score. */
  weight: number;
  /** -100 to +100; null when none of its reads can vote at this hour. */
  score: number | null;
  /** What it puts on the score, in the score's points (bias.py, 2026-11-19). Absent from an older collector. */
  points?: number;
  live: number;
  total: number;
}

export interface Conviction {
  bias: Side | null;
  /** -100 to +100 over the whole of the session's weight (bias.py, 2026-11-15). A plan stored before 2026-11-05 has none. */
  score?: number;
  /** "whole" on a read scored by that rule; a plan stored before it was scored over the live weight alone (lib/biasScale wholeScore). */
  basis?: "whole";
  coverage?: number;
  weight_label?: string;
  families?: ScoreFamily[];
  agree: number;
  against: number;
  neutral: number;
  live?: number;
  cannot_vote?: number;
  total: number;
  grade: "strong" | "moderate" | "weak" | "none";
  max_conviction: 1 | 2 | 3 | 4 | 5;
  /**
   * A lean with under half the session's weight able to vote (overnight: two reads of
   * eleven). The grade is weak at most. No page draws it since 2026-11-15: the score is
   * over the whole weight, so the mark sits near the middle by itself (lib/biasScale).
   */
  thin?: boolean;
  votes: ConvictionVote[];
}

export interface ScoreRow {
  key: string;
  label: string;
  pts: number;
  max: number;
  note: string;
}

/** The charts signals are read on (scan.TF_SEC, 2026-11-19); 10m is the Pine's own. */
export type SignalTf = "3m" | "5m" | "10m";

export interface ScanSignal {
  /** (L) level retest, (E) EMA-wave entry and (V) VWAP retest (both after an extended run only, from 2026-11-19), ◆ breakout. */
  kind: "L" | "E" | "V" | "BO" | "E_SETUP";
  side: Side;
  /** The level broken and retested; "VWAP" for a (V). */
  level: LevelKey | "VWAP" | null;
  at_et: string;
  price: number;
  note: string;
  /** The bar's open, epoch seconds — what the chart places it by. */
  t?: number;
  /** The Pine's stop idea for an (L) / (E) / (V). */
  stop?: number | null;
  /** The chart it printed on; absent from a collector older than 2026-11-19 (the 10m). */
  tf?: SignalTf;
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
    | "catalyst"
    | "insider"
    /** The previous session's major story (scanscore.prior_story): context, never score. */
    | "prior";
  tone: "good" | "warn" | "info";
  text: string;
}

/**
 * What the model made of the story that decided a name's catalyst part (server
 * newsread.py): how big it is, in one line. Context on the row and in the signal log;
 * it earns no points. `line` is empty where the model's words did not pass the guard.
 */
/** A pre-market row's four unscored figures (server premarket_record.pre_context). */
export interface PreContext {
  /** The gap in daily ATRs, signed, and SPY's; `own` is the first less the second. */
  gap: number | null;
  spy: number | null;
  own: number | null;
  /** The sector fund's pre-market move, %. */
  sector_pct: number | null;
  /** Pre-market volume against the name's own usual pre-market; an estimate under five mornings. */
  rvol: number | null;
  rvol_est: boolean;
  catalyst: {
    tag: string | null;
    major: boolean;
    report: string | null;
    size: NewsRead["size"] | null;
    direction: NewsRead["direction"];
    line: string | null;
    text?: boolean | null;
  };
  /** Where the last trade sits in the pre-market range toward the gap, 0 to 1, and in words. */
  hold: number | null;
  hold_word: string | null;
}

export interface NewsRead {
  size: "big" | "ordinary" | "unclear";
  line: string;
  /** The headline it read. */
  headline?: string | null;
  /**
   * Which way it read the story for this name (2026-11-18). It replaces the headline's
   * words and the EPS sign in the "reads against" flag and the tie-break; never points.
   * Absent on a read made before it was asked.
   */
  direction?: "bullish" | "bearish" | "mixed" | "unclear" | null;
  /** Whether it read the story's own text, not the headline alone. */
  text?: boolean;
}

/** An insider trade worth a line (server sources/insiders.py): an open-market buy of
 *  $100k+, or a sale of $1M+ not under a 10b5-1 plan, from the SEC's Form 4s. */
export interface InsiderTrade {
  side: "buy" | "sell";
  /** "CEO Doe Jane", "Director Smith John", "10% owner …". */
  who: string;
  value: number;
  shares: number;
  /** The average price across the filing's fills. */
  price: number;
  /** The trade's date, and the filing's. */
  date: string;
  filed: string;
  /** The filing on the SEC's site. */
  url: string;
  /** "CEO Doe Jane bought $1.2M at $41.20 on 10 Nov". */
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
  /** Set on the Today list's rows (server today.scan_row), for its Filters menu. */
  market_cap?: number | null;
  /** The month's insider trades worth a line, newest first (Form 4s); context, never scored. */
  insiders?: InsiderTrade[];
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
    /**
     * The previous session's high and low as the 5-minute bars alone have them. `pdh` and
     * `pdl` are the official day's, which reach further when the bars missed the opening
     * prints (scan.technicals); the page says so where the two differ.
     */
    pdh_bars?: number | null;
    pdl_bars?: number | null;
    /**
     * Today's pre-market high and low as the 5-minute bars alone have them. `pmh` and
     * `pml` take whichever of these and a second read (Nasdaq's, or the wide scan's
     * screener) reaches further, so on a day the bars start late they sit past the
     * candles (2026-11-11: no Nasdaq-listed name had a bar before 05:20 ET). Null
     * with no pre-market bars yet; absent from an older collector.
     */
    pmh_bars?: number | null;
    pml_bars?: number | null;
    /** `open` is the daily bar's official print, not the first 5-minute bar's. */
    open_official?: boolean;
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
  /** The 10m chart's signals: the ones the score, the record and the contract read. */
  signals: ScanSignal[];
  /** The 3m and 5m charts' signals, each with its `tf` (2026-11-19); absent from an older collector. */
  signals_fast?: ScanSignal[];
  score: {
    total: number;
    side: Side | null;
    parts: ScoreRow[];
    /** The uncapped sum the list is ranked on (2026-11-13); `total` is it capped to 0–100. */
    raw?: number;
    /** The name's place in the engine's order, 1 first: the raw sum, then the RVOL gate. */
    rank?: number;
    /** Why the RVOL gate kept a name out of the top ten, when it did. */
    gated?: string;
    /**
     * "inplay" before the bell: the Scanner ranks how in play a name is, and the row and
     * the slide-out both carry that read (server today._inplay_score). Absent: the setup score.
     */
    kind?: "inplay";
  };
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
  /** The name's average day: the last thirty completed sessions' volume (scanscore.avg_day). */
  adv?: number | null;
  /** Today's pre-market from Nasdaq's extended-trading feed (about fifteen minutes delayed). */
  premkt?: {
    volume: number | null;
    pct_adv: number | null;
    high: number | null;
    low: number | null;
    last: number | null;
    asof: string | null;
    /** "screener" when the wide read stood in because Nasdaq had not answered for the name. */
    source?: string;
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
  /** The most important story of the last day, graded (catalysts.py). Null when there is none. */
  catalyst?: Catalyst | null;
  /** The model's read of the story the score counted, once it has read it. Absent from an older collector. */
  news_read?: NewsRead | null;
  /** Which day of a multi-day move this is (momentum.py), when it is on one. */
  stage?: number | null;
  /**
   * Before the bell, four figures shown and logged and NEVER scored until the pre-market
   * record says which earn points (server premarket_record.py, 2026-11-18). Null in the session.
   */
  pre_ctx?: PreContext | null;
  /**
   * The small chart's five-minute closes: the slide-out chart's opening view (server
   * scan.spark_of), the evening before's last bars, then the pre-market from 04:00 ET to
   * now, after hours included.
   */
  spark?: number[] | null;
  /** The last regular close before them, which the line is coloured against. */
  spark_ref?: number | null;
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
    held_r: number | null;
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
  /**
   * `r` is the signal's floor, not the script's stop idea: that stop was nearer than a
   * quarter of the ten-minute ATR, the script's own retest buffer (scanlog). Absent on
   * an outcome settled before 2026-11-11 whose bars were gone by then.
   */
  floored?: boolean | null;
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
  /** (L) retest, (E) trigger, (V) VWAP retest, ◆ breakout, or NEAR — 90% of the way to a level. */
  kind: "L" | "E" | "V" | "BO" | "NEAR";
  side: Side;
  level: LevelKey | "VWAP" | null;
  /** The chart it printed on (absent before 2026-11-19: the 10m). */
  tf?: SignalTf;
  /**
   * False when the same setup printed on another chart first (scanlog.SAME_SETUP_SEC):
   * logged, never alerted. `after` names those charts.
   */
  alert?: boolean;
  after?: SignalTf[];
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
  held_r: number | null;
  med_mfe_r: number | null;
  med_mae_r: number | null;
}

export interface ScanStats {
  days: number;
  from: string;
  to: string;
  total: number;
  groups: ScanStatGroup[];
  /**
   * How much of the record is on the floored stop: `ruled` were read with a floor to
   * hand, `floored` are those it moved the stop on, `unruled` are older signals whose
   * bars were gone before they could be read again. Absent from an older collector.
   */
  floor?: { ruled: number; floored: number; unruled: number };
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
export type ChartTf = "1m" | "3m" | "5m" | "10m" | "30m" | "60m" | "D";

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
  /** The 20 and 50 EMAs on the chart's own bars (2026-11-11), drawn when picked; blank until that many bars are held. Absent from an older collector. */
  ema20?: Array<number | null>;
  ema50?: Array<number | null>;
  vwap: Array<number | null>;
  /** A stock's VWAP deviation, volume-weighted from 09:30, for the bands (2026-11-11); a future carries its own in `vwaps`. */
  vwap_sd?: Array<number | null>;
  /**
   * The chart's own four levels: ONE named set, the levels of the day the last bar is
   * in, as the owner's Pine script draws them (scan.chart_levels, futures.day_levels).
   * On a weekend they are Friday's, as it traded against them: its PDH and PDL the
   * session before it, its PMH and PML its own 04:00 to 09:30 ET, on a stock and a
   * future alike. `day` is whose they are; `pd_from` and `pm_from` the bar each pair
   * starts at (epoch seconds), from where the chart draws it to its right edge. Null on
   * the daily view and absent from a collector older than 2026-11-14, which draw them
   * across; there they are the trading day's.
   */
  levels: {
    pdh: number | null;
    pdl: number | null;
    pmh: number | null;
    pml: number | null;
    pm_done: boolean;
    pd_from?: number | null;
    pm_from?: number | null;
    day?: string | null;
  };
  /**
   * Each earlier day's four levels over its own bars (scan.history_levels,
   * futures.day_levels) — the Pine's "keep previous days' levels": plain lines, no
   * names. Absent from a collector older than 2026-10-14.
   */
  history?: Array<{ key: "PDH" | "PDL" | "PMH" | "PML"; v: number; from: number; to: number; day: string }>;
  sessions: Array<{ kind: "pre" | "rth" | "post"; from: number; to: number }>;
  /** The view's own chart's signals: 3m and 5m their own, 1m the 3m's, 10m and longer the 10m's. */
  signals: Array<{ t: number; kind: "L" | "E" | "V" | "BO" | "E_SETUP"; side: Side; price: number; tf?: SignalTf }>;
  /** A futures book's ladder rows drawn as lines: the flip, the walls, the settle, the opening range. */
  lines?: Array<{ v: number; label: string; tone: "call" | "put" | "flip" | "ref" }>;
  /** A futures book's expected move, from the collector rather than an options row. */
  em?: { lo: number; hi: number; label: string } | null;
  /** A futures book's VWAP from each anchor with its deviation (futures.anchored); null on the daily view. */
  vwaps?: Record<VwapAnchor, AnchoredVwap> | null;
  /** A futures book's 18:00 reopens, marked on the chart in place of a stock's extended-hours shading. */
  opens?: number[];
}

/** Where a futures VWAP starts again: each 18:00 reopen, London open, cash open, or Sunday reopen. */
export type VwapAnchor = "globex" | "london" | "rth" | "week";

export interface AnchoredVwap {
  vwap: Array<number | null>;
  /** The volume-weighted standard deviation about it, from the same start. */
  sd: Array<number | null>;
  /** The bars a new period starts on, where the line breaks. */
  starts: number[];
}

/* -------------------------------------------------------------------------- */
/* The wide scan, the stream and the slide-out (2026-11-09)                    */
/* -------------------------------------------------------------------------- */

/** A name's most important story of the last day (catalysts.py, sources/tvnews.py). */
export interface Catalyst {
  title: string;
  url: string;
  provider: string;
  /** Earnings, Guidance, FDA, Deal, Contract, Offering, Legal, Move, Analyst, Target, Preview, List, News. */
  tag: string;
  /** 1 major, 2 notable, 3 minor. */
  tier: 1 | 2 | 3;
  age_min: number;
  /** Tier 1 and under eighteen hours old: what puts a name ahead in the tables. */
  major: boolean;
}

/** GET /api/scanner/tick/{sym} — what an open chart asks for every second. */
export interface TickPayload {
  ok: boolean;
  sym: string;
  connected?: boolean;
  price?: number;
  /** Epoch seconds of the trade. */
  at?: number;
  /** The session the trade fell in; never overnight. */
  session?: "pre" | "rth" | "post" | "closed" | null;
  clock_session?: ScanSession;
  /** "etf": a futures chart's tick, the tracking ETF's trade in the future's prices (server futfill.py). */
  via?: "stream" | "spark" | "etf";
  /** The ETF a futures tick is carried by, and the future ÷ ETF ratio it was scaled with. */
  proxy?: string;
  ratio?: number;
  /** A futures tick's source: the ETF's live trade, or its newest one-minute bar (up to a minute old). */
  source?: "trade" | "bars";
  age_sec?: number | null;
  minute?: { t: number; o: number; h: number; l: number; c: number } | null;
  /** The newest overnight print, when it is newer than the last session trade. */
  overnight?: { price: number; at: number };
  offline?: { reason: string; api: string };
}

/** GET /api/scanner/name/{sym} — one whole row, tracked or not. */
export interface NamePayload {
  ok: boolean;
  sym: string;
  row: (ScanRow & { float_shares?: number | null; market_cap?: number | null; industry?: string | null }) | null;
  error: string | null;
  tracked: boolean;
  pinned: boolean;
  session: ScanSession | null;
  trading_day: string | null;
  stage: number | null;
  offline?: { reason: string; api: string };
}

export interface SearchHit {
  sym: string;
  name: string | null;
  cap: number | null;
  sector: string | null;
}

export type WideBasis = "pre" | "rth" | "post" | "last";

interface WideHead {
  ok: boolean;
  basis: WideBasis;
  /** The session the figures are about. */
  day: string;
  read_age_min: number | null;
  delayed_min: number;
  source: string;
  error: string | null;
  shown: number;
  matched: number;
  offline?: { reason: string; api: string };
}

export type RangeState = "above" | "below" | "inside";

export interface BreakoutRow {
  sym: string;
  name: string | null;
  cap: number | null;
  sector: string | null;
  theme: string | null;
  industry: string | null;
  last: number;
  chg: number | null;
  gap: number | null;
  ext: number | null;
  rvol: number | null;
  vol: number | null;
  /** The past week, as TradingView's screener counts it. */
  week?: number | null;
  /** Every theme this name is in (the Sectors view's chips). */
  themes: string[];
  adv_pct: number | null;
  pmh: number | null;
  pml: number | null;
  pdh: number;
  pdl: number;
  pdc: number | null;
  pm_state: RangeState | "forming" | null;
  pd_state: RangeState;
  both: "up" | "down" | null;
  inside: boolean;
  live: boolean;
  catalyst: Catalyst | null;
  tracked: boolean;
  pinned: boolean;
  stage: number | null;
  verdict?: Verdict | null;
  spark: number[] | null;
  spark_ref?: number | null;
}

/**
 * What the engine does with a name today (sources/pool.verdict): on the list for
 * good, tracked by hand, taken by the pool at a mark, on the list another way, in
 * the pool over its bar but not taken, in it under the bar, or not in it at all.
 */
export interface Verdict {
  state: "pinned" | "hand" | "promoted" | "tracked" | "inplay" | "quiet" | "out";
  score: number | null;
  reason: string | null;
  mark: string | null;
  at: string | null;
}

export type BreakoutChip = "all" | "both" | "news" | "gaps" | "through" | "inside" | "day23" | "pinned";

export interface BreakoutsPayload extends WideHead {
  scanned: number;
  chips: Record<BreakoutChip, number>;
  stats: {
    up: number;
    down: number;
    /** Through the previous day's high, and low, on their own. */
    pdh: number;
    pdl: number;
    top_rvol: { sym: string; v: number } | null;
    top_move: { sym: string; v: number } | null;
    live: number;
  };
  themes: Array<{ key: string; label: string }>;
  rows: BreakoutRow[];
}

export interface ExtendedRow {
  sym: string;
  name: string | null;
  cap: number | null;
  sector: string | null;
  float: number | null;
  last: number;
  chg: number;
  vol: number | null;
  adv_pct: number | null;
  /** This session's volume against its own average; an estimate until five sessions are on file. */
  rvol?: number | null;
  rvol_est?: boolean;
  /** The move in the name's daily ATRs, and the in-play read the default order sorts by
   *  (the pool's pre-market part: the move in ATRs and the share of an average day). */
  gap_atr?: number | null;
  in_play?: number;
  session?: "pre" | "post";
  hi?: number;
  lo?: number;
  state?: RangeState;
  /** The pre-market range, on either session's row. */
  pmh?: number | null;
  pml?: number | null;
  /** The base bar sits inside the bar before it. */
  inside?: boolean;
  live?: boolean;
  catalyst: Catalyst | null;
  tracked?: boolean;
  pinned?: boolean;
  stage?: number | null;
  verdict?: Verdict | null;
  spark?: number[] | null;
  spark_ref?: number | null;
}

export type ExtendedChip = "all" | "up" | "down" | "news" | "through" | "inside" | "day23" | "pinned";

export interface ExtendedPayload extends WideHead {
  session: "pre" | "post" | "all";
  active: boolean;
  volume_floor: number;
  scanned?: number;
  chips: Record<ExtendedChip, number>;
  stats: {
    up: ExtendedRow | null;
    down: ExtendedRow | null;
    through?: number;
    inside?: number;
    gap_up?: number;
    gap_up_news?: number;
    gap_down?: number;
    gap_down_news?: number;
  };
  reference: ExtendedRow[];
  reference_is_last: boolean;
  rows: ExtendedRow[];
}

export interface Day23Row {
  sym: string;
  name: string | null;
  cap: number | null;
  sector: string | null;
  side: Side;
  stage: number;
  moved: string;
  move: number;
  vx: number | null;
  chg: number | null;
  last: number;
  pdh: number;
  pdl: number;
  level: number;
  to_level: number | null;
  vol?: number | null;
  adv_pct: number | null;
  /** The table's own rough order (momentum.score_of), not the Scanner's score. */
  score?: number;
  state: string;
  kind: "confirmed" | "inside" | "watch" | "failed";
  through: boolean;
  live: boolean;
  since: number | null;
  catalyst: Catalyst | null;
  tracked: boolean;
  pinned: boolean;
  spark: number[] | null;
  spark_ref?: number | null;
}

export type Day23Chip = "all" | "long" | "short" | "day1" | "day2" | "day3" | "inside" | "through";

export interface Day23Payload extends WideHead {
  min_move: number;
  cap: number;
  chips: Record<Day23Chip, number>;
  rows: Day23Row[];
  last_day: string | null;
}
