/**
 * The collector's payload, as the browser sees it.
 *
 * HAND-WRITTEN RATHER THAN GENERATED. The service is Python and there is no
 * shared schema; a generator would mean a build step and a second source of
 * truth for shapes that change about once a week. What keeps these honest is
 * that every one of them is read by exactly one panel, so a drift shows up as
 * a blank column immediately rather than as a silent `undefined`.
 *
 * `| null` is used liberally and on purpose. Almost every figure here can be
 * genuinely absent — an index has no day range, a release has no consensus, a
 * future has not traded yet — and modelling that as an optional rather than a
 * nullable would let `0` and "not published" become the same thing.
 */

/**
 * The wire's desks.
 *
 * `corp` was split out of `markets` (2026-09-01) because `markets` had become
 * a catch-all: index and rates news, single-company news and the analyst-action
 * wire all landed in it, and it was the largest desk by some way. They are not
 * the same kind of thing for a desk trading index futures.
 */
export type Desk = "markets" | "corp" | "macro" | "policy" | "geo" | "energy";

export type Impact = "high" | "medium" | "low";

/** Which desk's session a source or a release belongs to. */
export type Region = "us" | "uk" | "eu" | "apac" | "global" | "other";

/** The five trading windows the terminal segments on, in ET. */
export type SessionKey = "asia" | "london" | "euro_mid" | "preny" | "ny" | "closed";

export interface Quote {
  key: string;
  symbol: string | null;
  label: string;
  name: string;
  group: "core" | "global" | "rates" | "vol" | "fx" | "energy" | "metals" | "crypto";
  fmt: "px" | "pct" | "bp";
  last: number;
  prev: number | null;
  chg: number | null;
  pct: number | null;
  high: number | null;
  low: number | null;
  /** Where the last print sits in the day's range: 0 at the low, 1 at the high. */
  range_pos: number | null;
  wk52_high: number | null;
  wk52_low: number | null;
  volume: number | null;
  currency: string | null;
  exchange: string | null;
  quote_time: number | null;
  spark: number[];
}

export interface SectorRow {
  key: string;
  label: string;
  last: number;
  day_pct: number | null;
  week_pct: number | null;
  month_pct: number | null;
  /** Excess return over SPY. The only form of this that answers "rotating in". */
  rs_day: number | null;
  rs_week: number | null;
  rs_month: number | null;
  spark: number[];
}

export interface WireItem {
  title: string;
  url: string;
  publisher: string;
  section: string;
  category: Desk;
  summary: string;
  utc: string | null;
  ts: number | null;
  /**
   * How hard this headline hits. "high" is a released number or a decided
   * event that reprices on the spot; "medium" moves things over a session;
   * "low" is context. Replaced an earlier `hot` boolean, which could only
   * answer "shout or do not shout".
   */
  impact: Impact;
  /** Fixed by the feed, never by the headline — whose session this desk covers. */
  region: Region;
  /** Other outlets that filed the same story. */
  also?: string[];
}

export interface CalendarRow {
  event: string;
  country: string;
  region: Region;
  /** Which trading window this release prints into. Null when untimed. */
  session: SessionKey | null;
  /** inflation | jobs | rates | growth | energy | dollar. Can be several. */
  themes: string[];
  /** Does this reach NQ / ES / GC? Theme and weight, not country alone. */
  core: boolean;
  date: string;
  et: string | null;
  utc: string | null;
  ts: number | null;
  actual: number | null;
  actual_raw: string | null;
  consensus: number | null;
  consensus_raw: string | null;
  previous: number | null;
  previous_raw: string | null;
  surprise: number | null;
  released: boolean;
  /** 0–5; 5 is a release that stops the tape. */
  score: number;
  note: string | null;
}

export interface GexLevel {
  key: string;
  label: string;
  side: "call" | "put" | "flip";
  price: number;
  dist: number | null;
  dist_pct: number | null;
  rank: number;
}

export interface GexAsset {
  ok: boolean;
  error: string | null;
  levels: GexLevel[];
  spot: number | null;
  regime: string | null;
  book: string | null;
  generated_unix: number | null;
  note?: string | null;
}

export interface RateRow {
  key: string;
  label: string;
  value: number;
  chg_bp?: number | null;
  unit?: string;
  note?: string;
}

export interface Rates {
  curve: RateRow[];
  real: RateRow[];
  spreads: RateRow[];
  policy: Record<string, { rate: number; as_of: string }>;
  strip: { code: string; month: string; label: string; price: number; implied: number }[];
  path: {
    front?: number;
    front_label?: string;
    horizon?: number;
    horizon_label?: string;
    /** Signed basis points. Negative is easing priced, positive tightening. */
    move_bp?: number;
    direction?: "tightening" | "easing" | "flat";
    vs_effr_bp?: number;
  };
  as_of: string | null;
  attribution?: string;
}

export interface SessionRow {
  key: string;
  label: string;
  zone: string;
  open: boolean;
  weekend: boolean;
  local_time: string;
  local_date: string;
  hours: string;
  next: "opens" | "closes";
  next_min: number;
  weight: number;
}

export interface Clock {
  et: string;
  et_time: string;
  et_date: string;
  utc: string;
  weekend: boolean;
  sessions: SessionRow[];
  open_count: number;
  overlap: boolean;
  phase: { key: string; label: string; note: string };
  markers: { label: string; note: string; et: string; in_min: number }[];
}

export interface SourceStatus {
  name: string;
  ok: boolean;
  items: number;
  source: string;
  age_min: number | null;
  error: string | null;
  last_ok_utc: string | null;
  notes: string[];
}

export interface SessionRange {
  key: "asia" | "london" | "euro_mid" | "preny" | "ny";
  label: string;
  ok: boolean;
  high: number | null;
  low: number | null;
  open: number | null;
  close: number | null;
  range: number | null;
  chg_pct?: number | null;
  /** 0 at that session's low, 1 at its high. Above 1 means the high is gone. */
  pos: number | null;
  bars: number;
  start_et: string | null;
  end_et: string | null;
  /** The calendar day the window STARTED on — Asia begins the evening before. */
  date?: string | null;
  /** "live" while the clock is still inside this window, else "complete". */
  status?: "live" | "complete";
  /** This window has not come round again yet, so the row is yesterday's. */
  prior_day?: boolean;
}

export interface EarningsRow {
  symbol: string;
  name: string;
  date: string;
  when: "pre" | "after" | "unspecified";
  eps_forecast: string | null;
  eps_actual: string | null;
  /** Percent, positive for a beat — parsed to a number at the source. */
  surprise_pct: number | null;
  market_cap: number | null;
  bellwether: boolean;
}

export interface ExpiryEvent {
  key: string;
  date: string;
  kind: "monthly" | "quarterly" | "month-end" | "quarter-end";
  label: string;
  note: string;
  days: number;
  is_today: boolean;
}

export interface ExpiryState {
  today: string;
  /** The week containing a monthly expiry behaves differently from the others. */
  opex_week: boolean;
  monthly_expiry: string;
  days_to_opex: number | null;
  next: ExpiryEvent[];
  note: string | null;
}

export interface Mover {
  symbol: string;
  name: string;
  sector: string;
  /** Index weight, in percent. */
  weight: number;
  last: number;
  pct: number;
  /** weight x return, in index percentage points. The ranking figure. */
  contribution: number;
}

export interface IndexMovers {
  label: string;
  index: string;
  as_of: string | null;
  covered_weight: number;
  net_contribution: number;
  members: Mover[];
}

export interface VolTermPoint {
  key: string;
  label: string;
  horizon: string;
  value: number;
  pct: number | null;
}

export interface VolTerm {
  points: VolTermPoint[];
  /** Near over far. Above 1.00 is backwardation — the stressed shape. */
  ratio: number | null;
  ratio_label: string;
  shape: "contango" | "flat" | "backwardation" | "unknown";
  note: string | null;
  skew: number | null;
  skew_pct: number | null;
}

export interface PolicyMeeting {
  /** The decision day (a two-day meeting's last day), ISO. */
  date: string;
  label: string;
  /** Basis points this meeting has priced into it, signed. */
  move_bp: number;
  stance: "hike" | "cut" | "hold";
  implied_after: number;
  cum_bp: number;
  method: string | null;
}

export interface PolicyMeetings {
  meetings: PolicyMeeting[];
  /** The chain's starting rate. */
  anchor: number | null;
  anchor_src: string | null;
}

export interface VPRow {
  key: string;
  label: string;
  kind: "done" | "live";
  date: string;
  start_et: string;
  end_et: string;
  low: number;
  high: number;
  /** Point of control — the price with the most traded volume. */
  poc: number;
  /** Value area high/low — the 70% acceptance zone's edges. */
  vah: number;
  val: number;
  volume: number;
  bin: number;
  bars: number;
}

export interface VPAssets {
  assets: Record<
    string,
    { ok: boolean; error?: string | null; rows: VPRow[]; last?: number | null }
  >;
}

export interface AuctionEvent {
  /** "10Y", "30Y" — a reopening already renamed to what the market calls it. */
  term: string;
  label: string;
  security: string;
  date: string;
  /** The standard 13:00 ET competitive close — a display hint, not feed data. */
  et: string;
  utc: string;
  ts: number;
  in_days: number;
  /** Empty until the weekly announcement; never guessed. */
  amount_bn: number | null;
  reopening: boolean;
  /** The long end: the auctions that reprice equities when they tail. */
  major: boolean;
}

export interface FedEvent {
  kind: "FOMC" | "Speech" | "Testimony" | "Beige Book" | "Conference";
  title: string;
  note: string | null;
  date: string;
  /** 2 for a two-day meeting. */
  days: number;
  et: string | null;
  utc: string | null;
  ts: number | null;
  in_days: number;
  /** Reprices the front of the curve: the FOMC, or a principal speaking. */
  major: boolean;
}

export interface Terminal {
  ok: boolean;
  built_utc: string;
  started_utc: string;
  clock: Clock;
  status: Record<string, SourceStatus>;
  age_min: Record<string, number>;
  quotes: Quote[];
  sectors: SectorRow[];
  wire: WireItem[];
  wire_feeds?: SourceStatus[];
  calendar: CalendarRow[];
  rates: Rates;
  gex: { assets: Record<string, GexAsset>; enabled: boolean; book: string };
  ranges: { assets: Record<string, { last: number | null; sessions: SessionRange[] }> };
  constituents: { indices: Record<string, IndexMovers> };
  fed: FedEvent[];
  auctions: AuctionEvent[];
  profiles: VPAssets;
  volterm: VolTerm;
  policy_meetings: PolicyMeetings;
  earnings: EarningsRow[];
  expiry: ExpiryState;
  /** Set by the route handler when the collector could not be reached at all. */
  offline?: { reason: string; api: string };
}

/* ------------------------------------------------------------------------ *
 * The session report.
 *
 * A model reads the terminal and calls a bias — see server/newsterminal/
 * report.py for the owner's decision to have it form the view rather than
 * narrate a deterministic one, and for what that costs.
 * ------------------------------------------------------------------------ */

export type Bias =
  | "bullish"
  | "leaning bullish"
  | "neutral"
  | "leaning bearish"
  | "bearish";

export interface ReportBody {
  bias: Bias;
  /** 1–5. The model's own confidence, not a probability. */
  conviction: number;
  headline: string;
  summary: string;
  drivers: { point: string; evidence: string; direction: "bullish" | "bearish" | "neutral" }[];
  invalidation: { condition: string; flips_to: string }[];
  session_expectation: string;
  levels_to_watch: { instrument: string; level: string; why: string }[];
  risks: string[];
}

/* ---- the brief -------------------------------------------------------------
 * Format "brief", generated since 2026-09-16. `report` carries the model's
 * words and `facts` every table the page prints — computed by the collector,
 * never by the model, and joined to the words by `id`/`key`. Reports stored
 * before then have no `format` and a ReportBody.
 * ---------------------------------------------------------------------------- */

export type Book = "NQ" | "ES" | "GC";

/** A driver's lean for the book it is listed under. */
export type Tone = "bear" | "bull" | "mixed" | "neutral";

export interface BriefCall {
  book: Book;
  open_bias: Bias;
  /** 1–5. The model's own confidence, not a probability. */
  conviction: number;
  rest_of_day: string;
  rest_of_day_bias: Bias;
  wrong_if: string;
  /**
   * Why the bias is what it is, two to four bullets each prefixed with its
   * layer (Macro / Positioning / Structure / Session). Optional because notes
   * stored before 2026-09-16 predate the field.
   */
  why?: string[];
}

export interface BriefRead {
  book: Book;
  regime: string;
  /** The macro transmission, cause to effect. */
  chain: string[];
  at_open: string;
  wrong_if: string;
  rest_of_day: string;
  flips: string[];
  drivers: { label: string; text: string; tone: Tone }[];
}

export interface BriefBody {
  thesis: string;
  calls: BriefCall[];
  snapshot_watch: { key: string; note: string }[];
  gamma_read: string;
  catalysts_intro: string;
  catalyst_notes: { id: string; note: string }[];
  reads: BriefRead[];
  rotation_read: string;
  ratio_reads: { id: string; read: string }[];
  rotation_notes: string[];
  headlines: { id: string; books: Book[]; note: string }[];
  cross_asset: string;
  risks: string[];
}

export interface BriefSnapshotRow {
  key: string;
  label: string;
  last: number | null;
  /** A second figure on the same row — VXN beside VIX. */
  last2: number | null;
  dp: number;
  suffix: string;
  chg: number | null;
  chg_unit: "pct" | "bp" | "pts";
  tag: string | null;
  sub: string | null;
}

export interface BriefLadderRow {
  price: number;
  label: string;
  kind: "flip" | "call" | "put" | "range" | "em" | "ref" | "last";
  /** Price minus last. Null on the Last row itself. */
  dist: number | null;
  inside_em: boolean;
}

export interface BriefLadder {
  book: Book;
  label: string;
  last: number;
  dp: number;
  /** Half-width of the expected move. */
  em: number | null;
  /** "GEXYGEN", or the implied vol the move was derived from. */
  em_basis: string | null;
  rows: BriefLadderRow[];
  note: string | null;
}

export interface BriefGamma {
  book: Book;
  label: string;
  dp: number;
  regime: string | null;
  last: number | null;
  flip: number | null;
  /** Flip minus last. */
  flip_dist: number | null;
  flip_dist_pct: number | null;
  /** The flip's distance in expected moves. */
  flip_em: number | null;
  call_wall: number | null;
  put_wall: number | null;
  em: number | null;
  em_basis: string | null;
}

export interface BriefCatalyst {
  id: string;
  kind: "data" | "fed" | "auction" | "earnings";
  when: string;
  ts?: number;
  title: string;
  country: string | null;
  lands_in_session: SessionKey | null;
  released: boolean;
  actual: string | null;
  consensus: string | null;
  previous: string | null;
  surprise: number | null;
  high: boolean;
  note: string | null;
}

export interface BriefRatio {
  id: string;
  group: "equity" | "gold";
  level: number;
  /** The ratio's change over five sessions, in percent. */
  chg_5d: number | null;
  dir: "up" | "down" | "flat";
}

export interface BriefHeadline {
  id: string;
  time_et: string;
  impact: Impact;
  desk: Desk | null;
  region: Region | null;
  publisher: string;
  title: string;
  url: string | null;
}

export interface BriefFacts {
  books: Book[];
  as_of: string;
  /** What was down when the brief was written — the banner at its top. */
  partial: string[];
  snapshot: BriefSnapshotRow[];
  ladders: BriefLadder[];
  gamma: BriefGamma[];
  catalysts: BriefCatalyst[];
  rotation: {
    ratios: BriefRatio[];
    megacaps: { symbol: string; pct: number | null; weight: number | null }[];
    megacap_index: string | null;
    index_pct: number | null;
  };
  headlines: BriefHeadline[];
}

export type ReportSession = "asia" | "london" | "ny";

/** Which book the note is about. "all" covers the three together. */
export type ReportAsset = "all" | "NQ" | "ES" | "GC";

export interface Report {
  ok: boolean;
  id: string;
  /** Which trading session this note was written for. */
  session: ReportSession;
  session_label: string;
  /** Which book it is about. */
  asset: ReportAsset;
  asset_label: string;
  created_utc: string;
  created_et: string;
  et_label: string;
  model: string;
  label: string;
  /** "brief" for everything generated since 2026-09-16; absent on older notes. */
  format?: "brief";
  /**
   * Whether the session was ALREADY TRADING when this was written.
   *
   * Decides whether the call reads "at the open" or "from here" — a note
   * composed five hours into Asia is a call from the current price, and
   * printing it under "At the open" would misdate a correct read. Absent on
   * notes written before this was recorded, where the old pre-open labels are
   * the honest description of what the model was asked for.
   */
  session_underway?: boolean;
  /** The brief's tables, computed by the collector. */
  facts?: BriefFacts | null;
  report: ReportBody | BriefBody | null;
  error: string | null;
  /** Exactly what the model was shown. Stored so a call can be re-read later. */
  digest: Record<string, unknown> | null;
  usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
  /** Set when the model answered but ignored the schema. */
  raw?: string;
}

export interface ReportStub {
  id: string;
  session: ReportSession | null;
  session_label: string | null;
  asset: ReportAsset | null;
  asset_label: string | null;
  et_label: string;
  created_et: string;
  label: string;
  model: string;
  bias: Bias | null;
  conviction: number | null;
  headline: string | null;
}

export interface ReportFeed {
  config: { enabled: boolean; model: string };
  latest: Report | null;
  history: ReportStub[];
  /** Set by the route handler when the collector could not be reached. */
  offline?: { reason: string; api: string };
}
