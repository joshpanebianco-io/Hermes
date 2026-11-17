/**
 * The stocks desk's market context — GET /api/market on the collector.
 *
 * EVERYTHING HERE IS COMPUTED BY THE ENGINE: the tape conviction count, the
 * breadth, how much of the implied move the index has used, today's prints
 * read against consensus, the Fed path, dealer gamma translated into ETF
 * prices, the index ETFs' option flow, and which sector peers report this
 * week. The page prints it; nothing on it is the model's.
 *
 * EVERY BLOCK MAY BE EMPTY OR NULL — a source that has not answered is a gap
 * the page names, never a value it invents. `gamma` in particular is null
 * whenever the terminal's optional gamma feed is off or down.
 */

export type Side = "long" | "short";

export interface Vote {
  key: string;
  label: string;
  /** The figure as printed: "▼ below PDL", "+3.1%", "3 up · 8 down", "−4bp". */
  value: string;
  vote: Side | "neutral";
  /** Why that reads as a long, short or neutral vote. */
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
  /** The highest conviction a plan may carry on this tape. */
  max_conviction: 1 | 2 | 3 | 4 | 5;
  /** A lean with under half the session's weight able to vote: its grade is weak at most. No page draws it since 2026-11-15: the score says it. */
  thin?: boolean;
  votes: Vote[];
}

export interface OptionsFlow {
  call_vol: number;
  put_vol: number;
  /** Put volume ÷ call volume, today. */
  pc_vol: number | null;
  call_oi: number;
  put_oi: number;
  /** Total volume ÷ total open interest — how much of today's trade is fresh positioning. */
  vol_oi: number | null;
  lean: "calls" | "puts" | "balanced" | null;
  top: Array<{ strike: number; right: "C" | "P"; expiry: string; volume: number; oi: number }>;
}

export interface BreadthIndex {
  key: "NDX" | "SPX";
  up: number;
  down: number;
  total: number;
  pct_up: number | null;
  /** |top-3 contributions| ÷ Σ|contributions| of the shown names. */
  top3_share: number | null;
  /** The shown names' summed contribution to the index, %. */
  contrib_pct: number | null;
}

export interface Breadth {
  sectors_up: number;
  sectors_down: number;
  sectors_total: number;
  /** RSP's day % minus SPY's, percentage points. */
  rsp_vs_spy: number | null;
  indices: BreadthIndex[];
}

export interface Fuel {
  sym: "SPY" | "QQQ" | "IWM";
  /** The one-day one-sigma move the index vol implies, %. */
  implied_pct: number | null;
  /** Today's regular-session high − low, % of the previous close. Null before the open. */
  range_pct: number | null;
  /** range_pct ÷ implied_pct. */
  used: number | null;
  gap_pct: number | null;
  gap_vs_implied: number | null;
  rvol: number | null;
  state: "room" | "normal" | "stretched" | null;
}

export interface Print {
  et: string;
  title: string;
  score: number;
  released: boolean;
  /**
   * Its time has passed — released, or a speech (which never has an actual), or
   * a print whose figures have not loaded yet. Absent from an older collector.
   */
  done?: boolean;
  actual: string | null;
  consensus: string | null;
  previous: string | null;
  surprise: number | null;
  read: "hot" | "cold" | "inline" | null;
  themes: string[];
}

export interface FedPath {
  next: string | null;
  next_bp: number | null;
  next_rate: number | null;
  path: Array<{ date: string; bp: number | null; rate: number | null }>;
  change_bp: number | null;
  note: string | null;
}

export interface MacroMove {
  key: string;
  label: string;
  text: string;
  move: number | null;
}

export interface GammaEtf {
  etf: "QQQ" | "SPY";
  book: "NQ" | "ES";
  regime: "POS" | "NEG" | null;
  flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
  spot: number | null;
  /** ETF ÷ futures — the conversion the levels were translated through. */
  ratio: number | null;
  note: string;
}

export interface IndexOptions {
  sym: "SPY" | "QQQ" | "IWM";
  iv30: number | null;
  iv_rv: number | null;
  premium: string | null;
  skew: number | null;
  em_front_pct: number | null;
  flow: OptionsFlow | null;
}

export interface PeerSector {
  sector: string;
  label: string | null;
  reports: Array<{ sym: string; date: string; when: string; days: number }>;
  /** The watchlist names in that sector. */
  watch: string[];
}

export interface MarketCtx {
  ok: boolean;
  built_utc: string;
  session: "pre" | "rth" | "post" | "closed";
  conviction: Conviction;
  breadth: Breadth;
  fuel: Fuel[];
  prints: Print[];
  fed: FedPath | null;
  macro: MacroMove[];
  gamma: GammaEtf[] | null;
  index_options: IndexOptions[];
  peers: PeerSector[];
  /** Set by the Next proxy when the collector could not be reached. */
  offline?: { reason: string; api: string };
}
