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
export type SessionKey = "asia" | "london" | "premkt" | "ny" | "closed";

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
  /**
   * How current `last` is (quotes.feed_state): inside its trading hours
   * "live" or "delayed" (Yahoo's CME futures trail by ten minutes), "stale"
   * past half an hour, or "closed". Absent on a snapshot from before
   * 2026-10-14.
   */
  feed?: "live" | "delayed" | "stale" | "closed";
  /** Minutes the last print trails the collector's clock. */
  lag_min?: number | null;
  /**
   * A US-listed fund's last trade outside the session (server quotes.with_ext, 2026-11-16):
   * before the bell its pre-market, after the close its after hours, against the last
   * regular close (`last`). Absent in the session and on every other row.
   */
  ext?: { kind: "pre" | "post"; px: number; pct: number; at: number; day?: string } | null;
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

/** Every US stock at $2bn+ by the size of its move (sources/universe.breadth). */
export interface BreadthAll {
  basis: "pre" | "rth" | "post" | "last";
  floor: number;
  /** The names counted: before the bell, only those that have traded in the pre-market. */
  names: number;
  /** Every name at the floor, whatever it has done today (2026-11-13). */
  of?: number;
  advancers: number;
  decliners: number;
  buckets: Array<{ label: string; n: number; side: "up" | "down" }>;
  /** Each sector's biggest movers at $5bn+. */
  leaders: Record<string, { up: Array<{ sym: string; chg: number }>; down: Array<{ sym: string; chg: number }> }>;
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
  /**
   * Once printed: hot (the stronger economy), cold, or in line — the
   * collector's read (releases.read_of). Absent from an older collector.
   */
  read?: "hot" | "cold" | "inline" | null;
  /** What that read means for each book, in the collector's words (releases.implication). */
  meaning?: Record<"NQ" | "ES" | "GC", string> | null;
  /**
   * The agency's own figure for this print, when it publishes one a program can read
   * (server sources/official.py, 2026-11-15): the BLS, the Census Bureau, the BEA or
   * the EIA. With it, `actual` IS the agency's figure. Absent on every other row,
   * which is the calendar feed's alone.
   */
  official?: {
    by: "BLS" | "Census" | "BEA" | "EIA";
    /** The figure, in the units the row is in. */
    text: string;
    /** What it measures: "October 2026", "week ending 6 Nov". */
    period: string;
    /** The agency's release. */
    url: string;
    /** true: the feed said the same. false: it said `feed`. null: it had said nothing yet. */
    agrees: boolean | null;
    feed: string | null;
  } | null;
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
  /** The exchange holiday this venue is shut for today, when there is one. */
  holiday?: string | null;
}

/** One of the four session boxes on the clock (sessions.box_state): open or not, and how long until that changes. */
export interface BoxRow {
  key: "asia" | "london" | "premkt" | "ny";
  label: string;
  open: boolean;
  /** The occurrence being counted down to — today's London box reads 03:00 in a clock-mismatch week. */
  start_et: string;
  end_et: string;
  next: "opens" | "closes";
  next_min: number;
  /** The same occurrence as instants, for printing the box in the reader's own zone. */
  opens_utc: string;
  closes_utc: string;
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
  /** The four boxes the Sessions panel draws (2026-10-30). */
  boxes: BoxRow[];
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
  /** The four boxes the panel draws, and the overnight the brief's ladder reads (sessions.BOXES). */
  key: "asia" | "london" | "premkt" | "ny" | "overnight";
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

/* ------------------------------------------------------------------------ *
 * The driver board (server/newsterminal/drivers.py) and the inputs it added.
 * ------------------------------------------------------------------------ */

/** One family of reads, weighed for the session (server bias.py). */
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

export interface DriverVote {
  key: string;
  label: string;
  /** Macro sets the direction, positioning how far a move runs, structure whether the tape accepts it. */
  layer: "macro" | "positioning" | "structure";
  /** The figure as printed: "4.10% +6.0bp", "negative γ · below flip 30,200". */
  value: string;
  vote: "long" | "short" | "neutral";
  /** Why that reads as it does — or why it is neutral (closed, missing, inside the band). */
  note: string;
  /** False when it cannot vote at this hour: shut or missing, which is not the same as flat. */
  live: boolean;
  /** For a read in no family: why it is never a side, in the collector's words. */
  aside?: string;
  /** Which family it scores in; event risk (a damper), dealer gamma and the VIX curve (regimes) and the heavyweights' prints (already in the price) have none. */
  family: string | null;
  /** How much of a full vote a long or short read's size earns, 0 to 1 (drivestats.py, 2026-11-19); absent is a whole vote. */
  strength?: number;
  /** The heavyweights' prints only: the side they would have voted before 2026-11-19. */
  said?: "long" | "short" | "neutral";
}

/** What a move will find — positioning, the market-wide put/call, OpEx — never a vote. */
export interface DriverContext {
  key: string;
  label: string;
  value: string;
  note: string;
}

export interface DriverBook {
  key: string;
  last: number | null;
  bias: "long" | "short" | null;
  /** -100 to +100 over the whole of the session's weight: a family that cannot vote counts as no lean (bias.py, 2026-11-15). */
  score: number;
  /** "whole" on a read scored by that rule; absent on one scored over the live weight alone (lib/biasScale wholeScore). */
  basis?: "whole";
  /** The share of the session's weight that is live, percent. */
  coverage: number;
  /** "London's weight": what `coverage` is a share of. */
  weight_label: string;
  /** The session the weights are for: asia, london, ny_pre, ny_live (bias.session_key). */
  session_key?: string;
  families: ScoreFamily[];
  agree: number;
  against: number;
  /** Reads that can vote and sit inside their threshold. */
  neutral: number;
  live: number;
  cannot_vote: number;
  /** Every read that scores: live and shut. Event risk is not one. */
  total: number;
  grade: "strong" | "moderate" | "weak" | "none";
  /** The ceiling the Analysis brief's call is capped at. */
  max_conviction: 1 | 2 | 3 | 4 | 5;
  votes: DriverVote[];
  macro_lean: "long" | "short" | null;
  structure_lean: "long" | "short" | null;
  /** Macro and structure disagree: lower conviction, trade the levels. */
  conflict: boolean;
  regime: "POS" | "NEG" | null;
  /** One line on how to treat the score. */
  treatment: string;
  context: DriverContext[];
}

export interface Drivers {
  built_utc: string;
  /** The scanner's session, which says whether the cash-market reads may vote. */
  session: string;
  ny_open: boolean;
  /**
   * Which session's weights the board reads now (drivers.weights_for): the session
   * trading or opening next, New York split at its bell. The Market Report page lights
   * that session's pill.
   */
  weights?: "asia" | "london" | "ny_pre" | "ny_live";
  books: Record<string, DriverBook>;
  error?: string;
}

/** A book's or a name's daily levels (frame.frame_of), from finished sessions only. */
export interface Frame {
  ok?: boolean;
  error?: string | null;
  as_of: string | null;
  sessions: number;
  prev_close: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  wk52_hi: number | null;
  wk52_lo: number | null;
  /** Last completed week's range. */
  pw_hi: number | null;
  pw_lo: number | null;
  pw_close: number | null;
}

export interface History {
  books: Record<string, Frame>;
  today?: string;
}

/** One book's Commitments of Traders read (sources/cot.py). */
export interface CotBook {
  ok: boolean;
  error?: string | null;
  market?: string;
  /** The Tuesday the report is as of. */
  as_of?: string;
  /** "Leveraged funds" for the index futures, "Managed money" for gold. */
  spec?: string;
  net?: number;
  prev?: number | null;
  chg?: number | null;
  oi?: number | null;
  pct_oi?: number | null;
  /** The net's percentile over the last year of weeks. */
  pctile?: number | null;
  word?: "crowded long" | "crowded short" | "middling" | null;
  read?: string;
  other?: { label: string; net: number } | null;
  weeks?: number;
}

export interface Cot {
  books: Record<string, CotBook>;
}

/** Cboe's daily put/call ratios (sources/cboepc.py) with the log's averages. */
export interface PutCall {
  date: string;
  ratios: Partial<Record<"total" | "index" | "equity" | "etp" | "vix" | "spx", number>>;
  avg20: Partial<Record<"total" | "index" | "equity" | "etp" | "vix" | "spx", number | null>>;
  pctile: Partial<Record<"total" | "index" | "equity" | "etp" | "vix" | "spx", number | null>>;
  /** Days held in the log — the averages and percentiles are over these. */
  days: number;
  read: { equity: string | null; total: string | null };
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
  /** Before the bell: its own pre-market move and that times its weight; null when it has not traded. */
  pre_pct?: number | null;
  pre_contribution?: number | null;
}

export interface IndexMovers {
  label: string;
  index: string;
  /** The fund the card's tab is labelled by: QQQ, SPY (the key stays the futures book). */
  fund?: string | null;
  /** The holdings file's date, "12 Nov 2026" whoever published it. */
  as_of: string | null;
  /** Whose file the weights are: "iShares", or the second issuer while iShares is not answering. */
  weights_from?: string | null;
  covered_weight: number;
  net_contribution: number;
  members: Mover[];
  /** Before the bell (server constituents.with_pre): what the names' own pre-market moves add up to, and how many have traded. */
  pre_net?: number | null;
  pre_traded?: number | null;
}

export interface VolTermPoint {
  key: string;
  label: string;
  horizon: string;
  value: number;
  pct: number | null;
}

/**
 * A book's implied day — volterm.implied_day. The one-sigma move in the book's
 * own points from its own index, how much of it today's Globex range has used,
 * and implied against realised; GEXYGEN's 0DTE band beside it when that is up.
 * Every word (`fuel`, `premium`) is the server's, scored with the stocks desk's
 * thresholds — lib/vix mirrors them for the tables behind the row.
 */
export interface ImpliedBook {
  key: string;
  /** Decimals the book is quoted to: NQ 0, ES 2, GC 1. */
  dp: number;
  last: number;
  prev: number | null;
  /** The index the day is read from: VXN, VIX or GVZ. */
  vol_key: string;
  vol: number | null;
  vol_pct: number | null;
  /** The one-sigma day in percent and in points, and the band it draws round the last print. */
  sigma_pct: number | null;
  sigma: number | null;
  lo: number | null;
  hi: number | null;
  /** Today's range since the 18:00 ET reopen, in points and against the previous close. */
  range: number | null;
  range_pct: number | null;
  /** range_pct ÷ sigma_pct, and marketctx's word for it. */
  used: number | null;
  fuel: "room" | "normal" | "stretched" | null;
  /** Twenty-session realised, the day it implies in points, implied over it, and optcalc's word. */
  rv20: number | null;
  rv_day: number | null;
  iv_rv: number | null;
  premium: "cheap" | "fair" | "rich" | null;
  /** GEXYGEN's own 0DTE expected-move band and regime; null while it is down. */
  gex_lo: number | null;
  gex_hi: number | null;
  regime: string | null;
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
  /** Each book's implied day — on the terminal snapshot; the scanner's own curve carries none. */
  books?: ImpliedBook[];
  /** The VIX against its own month (volterm.vix_month): percentile of the last twenty closes, their low and high. */
  vix_month?: { pctile: number; lo: number; hi: number; days: number } | null;
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

/** A profile window's market-profile shape; absent from an older collector. */
export interface VPShape {
  shape?: string | null;
  poc_pos?: number | null;
  second_node?: number | null;
  open?: number | null;
}

/** The profile's reads (profile.reads): the facts the brief is handed and the panel's sentence. */
export interface ProfileReads {
  developing_profile_open?: {
    price: number;
    anchored_et: string | null;
    this_is: string;
    vs_prev_rth_value: "above_value" | "inside_value" | "below_value";
  };
  price_now?: {
    price: number;
    vs_prev_rth_value?: "above_value" | "inside_value" | "below_value";
    vs_overnight_value?: "above_value" | "inside_value" | "below_value";
  };
  text?: string | null;
}

export interface VPAssets {
  assets: Record<
    string,
    {
      ok: boolean;
      error?: string | null;
      rows: Array<VPRow & VPShape>;
      last?: number | null;
      reads?: ProfileReads | null;
    }
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

/* -------------------------------------------------------------------------- */
/* Session type — will New York trend or range (newsterminal/daytype.py)       */
/* -------------------------------------------------------------------------- */

export type DayCall = "range" | "trend" | "mixed" | "none";

export interface DayHold {
  condition: string;
  /** The card's own figure for the condition ("0.31 ATR so far"), when it has one. */
  shown: string | null;
  n: number;
  trend: number;
  range: number;
  /**
   * Which side the condition's counts vote for; null when it only shows. "no_trend" is a
   * trend rate under half of every session's: a vote against a trend call (2026-11-16).
   */
  vote: "range" | "trend" | "no_trend" | null;
}

export interface DayLean {
  call: DayCall;
  word: string;
  /** The voting conditions with their counts, in one line. */
  why: string;
  holds: DayHold[];
  base: { n: number; trend: number; range: number };
  night: { atr: number | null; done: boolean | null; asia: number | null; london: number | null; pre: number | null };
  prev: { type: string | null; dir: string | null; range_atr: number | null };
}

/** The day's own label once New York has closed (the ladder's rule). */
export interface DayLabel {
  type: "trend" | "range" | "normal";
  dir: "up" | "down" | null;
  inside: boolean | null;
  range_atr: number | null;
  close_pos: number | null;
}

export interface DayTypeBook {
  card: Record<string, unknown>;
  lean: DayLean;
  label: DayLabel | null;
}

export interface DayType {
  day: string;
  /** Null for a book whose ranges or daily bars have not arrived. */
  books: Record<string, DayTypeBook | null>;
  record: Record<string, { n: number; backfill: number; live: number; from: string | null; to: string | null }>;
  error?: string;
}

/**
 * A day a market the desk trades through is shut or shuts early (server holidays.py):
 * US stocks and bonds as one row, London, Tokyo. Hand-kept from the published schedules.
 */
export interface HolidayNotice {
  /** The ET calendar day, "2026-11-11". */
  date: string;
  market: "us" | "uk" | "japan";
  country: string;
  region: Region;
  /** The holiday: "Veterans Day". */
  name: string;
  kind: "closed" | "early";
  /** What is shut, in a few words: "US bond market closed". */
  label: string;
  /** What that does to the session and the reads. */
  note: string;
  /** The calendar's own scale: 5 the NYSE shut, 4 the bond market alone, 3 an early close or a foreign holiday. */
  score: number;
}

export interface Terminal {
  ok: boolean;
  built_utc: string;
  started_utc: string;
  clock: Clock;
  /** Yesterday through three weeks out. Absent from an older collector. */
  holidays?: HolidayNotice[];
  status: Record<string, SourceStatus>;
  age_min: Record<string, number>;
  quotes: Quote[];
  sectors: SectorRow[];
  /** The theme ETFs, the same shape as the sectors (sources/quotes.collect_themes). */
  themes?: SectorRow[];
  breadth_all?: BreadthAll | null;
  wire: WireItem[];
  wire_feeds?: SourceStatus[];
  calendar: CalendarRow[];
  rates: Rates;
  gex: { assets: Record<string, GexAsset>; enabled: boolean; book: string };
  ranges: {
    assets: Record<
      string,
      {
        last: number | null;
        sessions: SessionRange[];
        /** VWAP from the Globex reopen and from the cash open (ranges.py). */
        vwap?: { globex: number | null; rth: number | null };
        opening_range?: { high: number; low: number; complete: boolean } | null;
        /** The ten-minute 200 EMA from the same bars (structure.ema200_10m). */
        ema200_10m?: Ema200 | null;
      }
    >;
  };
  /** The live levels ladder per book, computed per request (report.live_ladders). */
  ladders?: Record<string, BriefLadder | null>;
  /** Will New York trend or range, per book, computed on read (daytype.py). */
  daytype?: DayType;
  constituents: { indices: Record<string, IndexMovers> };
  fed: FedEvent[];
  auctions: AuctionEvent[];
  profiles: VPAssets;
  volterm: VolTerm;
  policy_meetings: PolicyMeetings;
  earnings: EarningsRow[];
  expiry: ExpiryState;
  /**
   * The driver board and its own inputs (2026-10-22): the engine's count per
   * book, a year of daily levels per book, the CFTC's positioning and Cboe's
   * daily put/call. Each absent from an older collector.
   */
  drivers?: Drivers;
  history?: History;
  cot?: Cot;
  putcall?: PutCall | null;
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

/**
 * A book a brief can carry a call for. Silver and crude since 2026-11-15 (server
 * report.BOOKS); the three index funds since 2026-11-16, for the Stocks tab's report
 * (server report.ETF_BOOKS).
 */
export type Book = "NQ" | "ES" | "GC" | "SIL" | "CL" | "SPY" | "QQQ" | "IWM";

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
  /** The heavyweight print or the event moving this book, with its figure; "" when none (2026-10-30). */
  catalyst?: string;
  /** The `heavyweights` / `event_risk` ids the sentence cites. */
  catalyst_ids?: string[];
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

/**
 * A call in the short brief (2026-11-15, server report.SCHEMA): the side, its reasons,
 * the map and what kills it. The longer call above (a label for the rest of the day, a
 * catalyst sentence) is what a note stored before then carries.
 *
 * The reasons came in two shapes the same day: `why` (version 2, at most three
 * bullets) and `factors` (version 3, the market report: one comment a factor the bias
 * weighs, joined by `key` to the engine's row in `BriefFacts.factors`).
 */
export interface ShortCall {
  book: Book;
  open_bias: Bias;
  /** 1–5. The model's own confidence, not a probability; capped by the engine's board. */
  conviction: number;
  /** Version 2: one to three reasons, strongest first. */
  why?: string[];
  /** Version 3: the model's comment on a factor, by the factor's key. */
  factors?: { key: string; line: string }[];
  /** One line: the level that has to hold or break, and where that carries. */
  plan: string;
  wrong_if: string;
}

/**
 * The short brief: what a report is since 2026-11-15 (`Report.brief_version` 2, and 3
 * for the market report it became that evening). Five parts, each under a word limit
 * the collector checks (report.LIMITS).
 */
export interface ShortBriefBody {
  thesis: string;
  /** The Stocks report's comments on the market's factors, written once (`facts.market_factors`). */
  factors?: { key: string; line: string }[];
  calls: ShortCall[];
  /** What is on the clock, each by the id of its row in `facts.catalysts`. */
  today: { id: string; note: string }[];
  risks: string[];
  headlines: { id: string; books: Book[]; note: string }[];
  /**
   * Version 4, the briefing (2026-11-19): what can move prices, each item a row of the
   * facts (a `catalysts` id, a `headlines` id, or a `context_movers` id). Absent before.
   */
  movers?: BriefMover[];
}

/** One item of the briefing's list (server report._movers). */
export interface BriefMover {
  id: string;
  impact: "high" | "medium" | "low";
  /** What it does to the book. "regime" is the VIX's alone: the ranges it makes, never a side. */
  effect: "supportive" | "pressure" | "two-way" | "neutral" | "priced" | "regime";
  /** The model's line on why it moves the book; the server's where it wrote none. */
  why: string;
  /** Put on the list by the server: a high-impact release the model left off twice. */
  server?: boolean;
}

/** A list item that is no calendar row or headline (server report.context_movers). */
export interface BriefContextMover {
  id: "rates" | "vix" | "positioning";
  /** What it is, in the collector's words: "10Y 5.145% (+2.4bp) · Dollar 103.61 (+0.06%)". */
  what: string;
  /** The VIX's: the ranges its band makes ("Wider ranges"), the effect column's word. */
  regime?: string;
  why?: string;
}

/**
 * One row of "what is driving the bias" (server report.factors_of): a family the bias
 * weighs in this session, with the engine's own tag and share of the score, heaviest
 * first; the last row is event risk, which is no side and lowers the ceiling instead.
 * No row for dealer gamma and none for a trend: the bias weighs neither.
 */
export interface BriefFactor {
  /** The family's key, or "event". What a call's comment is joined on. */
  key: string;
  name: string;
  /** The small line under the name: "rates & dollar". */
  sub: string | null;
  /** Its share of the session's hundred; null on the event row. */
  weight: number | null;
  /** bull and bear are the book's side; none is a family with no read live at this hour. */
  lean: "bull" | "bear" | "mixed" | "neutral" | "none" | "damp";
  /** The word on the row's tag: "Bearish", "Nothing yet", "2 stories". */
  tag: string;
  /** The engine's figures behind it, for the hover and for a row the model left bare. */
  reads: string[];
}

/** The levels a call is traded against, low to high (server report.key_levels). */
export interface BriefLevels {
  dp: number;
  marks: { price: number; label: string; kind: "range" | "poc" | "value" | "last" }[];
}

/** The engine's read for one book as a brief stores it (server report._drivers). */
export interface BriefBoard {
  bias: "long" | "short" | null;
  score?: number | null;
  /** The share of the session's weight that could vote, 0 to 100. */
  coverage?: number | null;
  /** "whole" when the score is over the whole weight (lib/biasScale wholeScore). */
  basis?: string | null;
  grade?: string | null;
  max_conviction?: number | null;
  live?: number | null;
  total?: number | null;
  /** Whose weights scored it: "London", "New York". */
  weights_for?: string | null;
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
  /** `vwap`, `open` and `ema` appear only on the live ladder (Structure), never in a note. */
  kind: "flip" | "call" | "put" | "range" | "em" | "ref" | "last" | "vwap" | "open" | "ema";
  /** Price minus last. Null on the Last row itself. */
  dist: number | null;
  inside_em: boolean;
  /** The confluence band this row belongs to (structure.confluence), highest band first. */
  band?: number | null;
}

/** Rows within a quarter of an ATR of each other: the level is the band (structure.confluence). */
export interface ConfluenceBand {
  hi: number;
  lo: number;
  n: number;
  labels: string[];
  dist: number | null;
  text: string;
}

/** Today's range so far against a normal day, and where it was spent (structure.fuel). */
export interface Fuel {
  range: number;
  high: number;
  low: number;
  atr: number | null;
  atr_pct: number | null;
  em: number | null;
  em_pct: number | null;
  overnight: number | null;
  ny: number | null;
  line: string;
  read: string;
}

/** The prior cash session's shape and the gap at the reopen (structure.yesterday). */
export interface Yesterday {
  shape: string | null;
  open: number;
  high: number;
  low: number;
  close: number;
  range: number;
  range_atr: number | null;
  close_pos: number | null;
  gap: number | null;
  gap_atr: number | null;
  text: string;
}

/** The daily 200 EMA as the regime line (structure.regime). */
export interface Regime {
  ema200: number;
  pct: number;
  above: boolean;
  text: string;
}

/** The ten-minute 200 EMA and its slope (structure.ema_read). */
export interface Ema200 {
  value: number;
  slope: "rising" | "falling" | "flat";
  bars: number;
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
  /** The bands, on every ladder; the cards below ride only with the live one (Structure). */
  confluence?: ConfluenceBand[];
  fuel?: Fuel | null;
  yesterday?: Yesterday | null;
  regime?: Regime | null;
  ema200_10m?: Ema200 | null;
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
  /** "holiday" is a day a market is shut or shuts early (holidays.py); absent from a brief stored before 2026-11-12. */
  kind: "data" | "fed" | "auction" | "earnings" | "holiday";
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
  /** The release's other series, its lead being this row (report.py, releases.py). */
  also?: Array<{ title: string; actual: string | null; consensus: string | null; previous: string | null }>;
  /** Whose figure the actual is, when it is the agency's own: "BLS", "Census", "BEA", "EIA". */
  official?: string;
  /** Printed earlier this week, before the twelve hours the calendar reads (2026-11-19). */
  earlier?: boolean;
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
  /** The engine's board per book when the note was written: the scale beside each call. */
  drivers?: Partial<Record<Book, BriefBoard>>;
  /** The market report's drivers table, a row a factor, per book (version 3). */
  factors?: Partial<Record<Book, BriefFactor[]>>;
  /** The market report's key levels per book (version 3). */
  levels?: Partial<Record<Book, BriefLevels>>;
  /**
   * The Stocks report's one bias (server report.market_board): the Stocks tape count,
   * read for all three funds, null when it had not been read. Only on that report.
   */
  market?: BriefBoard | null;
  /** Its table, printed once above the calls (server report.factors_of("TAPE")). */
  market_factors?: BriefFactor[];
  /** The briefing's rows that are no calendar row or headline (version 4). */
  context_movers?: BriefContextMover[];
  /** How the engine's bias counts each item the list can hold, by id (server report.bias_links). */
  bias_links?: Record<string, BriefBiasLink>;
}

/**
 * The factor of the engine's bias an item is counted in, as the report's table prints it,
 * or (`key` null) why the bias does not count it.
 */
export interface BriefBiasLink {
  key: string | null;
  name: string;
  weight?: number | null;
  tag?: string;
  lean?: BriefFactor["lean"];
  note?: string;
}

export type ReportSession = "asia" | "london" | "ny";

/**
 * What the note is about. Since 2026-11-16 the Futures tab writes one book at a time
 * (NQ, ES, GC, SIL, CL) and the Stocks tab writes "etfs", SPY, QQQ and IWM together
 * for New York. "indexes" (NQ and ES, the Market Report page's for a day) and "all"
 * (NQ, ES and gold) are what older notes were written about; they still open, under
 * each book they carry.
 */
export type ReportAsset = "indexes" | "GC" | "SIL" | "CL" | "all" | "NQ" | "ES" | "etfs";

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
   * 2 is the short brief (2026-11-15) and 3 the market report it became the same day
   * (a comment a factor, no dealer gamma): `report` is a ShortBriefBody. Absent on a
   * brief written before then, whose `report` is the longer BriefBody.
   */
  brief_version?: number;
  /** How many words the model wrote in it (short briefs only). */
  words?: number;
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
  report: ReportBody | BriefBody | ShortBriefBody | null;
  error: string | null;
  /** Exactly what the model was shown. Stored so a call can be re-read later. */
  digest: Record<string, unknown> | null;
  usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
  /** Set when the model answered but ignored the schema. */
  raw?: string;
  /**
   * Figures the model printed that the data it was shown does not contain —
   * checked by the collector after the answer (and re-asked once). Absent on
   * reports written before the check existed.
   */
  unverified?: string[];
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

/**
 * A generation in progress, or one a poll just settled. The collector writes
 * a note on a thread of its own and the page asks after it by id (server
 * jobs.py; src/lib/jobs.ts): `running` means keep asking; `done` means the
 * feed it rode in on carries the note as `latest`; `lost` means the collector
 * restarted underneath it, and `latest` is the failed envelope that says so.
 */
export interface NoteJob {
  id: string;
  state: "running" | "done" | "lost";
  /** When it was started, ISO — the clock a reloaded page resumes from. */
  started_utc?: string;
  model?: string;
  /** What a report job is writing about, and for which session (api.py's job meta). */
  asset?: ReportAsset;
  session?: ReportSession;
}

export interface ReportFeed {
  config: { enabled: boolean; model: string };
  latest: Report | null;
  history: ReportStub[];
  /** Set by the route handler when the collector could not be reached. */
  offline?: { reason: string; api: string };
  /** The report being written right now, if any, or the job a poll settled. */
  job?: NoteJob | null;
}
