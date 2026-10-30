/**
 * The Game plan — the stocks desk's pre-open brief (owner instruction,
 * 2026-10-13: the review's "a pre-open NY game-plan brief built from the
 * scanner's top names").
 *
 * The same two-author split the futures brief keeps: `facts` are tables the
 * collector computed from the live scanner payload — levels, relative
 * strength, the options context — and the page prints them; `plan` is the
 * model's words only, joined to those facts by ticker. A plan for a name the
 * facts do not carry never arrives here: the server drops it.
 *
 * THE CONVICTION ROUND (2026-10-14) adds the tape's count and its context to
 * the facts, and each name's option flow, pre-market and reporting peers.
 * Every one of those fields is optional: a plan written before it has none,
 * and the page prints what a plan carries.
 */

import type { Breadth, Conviction, FedPath, Fuel, GammaEtf, Print } from "@/types/market";
import type { NoteJob } from "@/types/terminal";

export type PlanSession = "pre" | "rth" | "post" | "closed";

export interface PlanTape {
  sym: string;
  chg_pct: number | null;
  ext_pct: number | null;
  trend: -1 | 0 | 1;
}

export interface PlanRegime {
  vix: number | null;
  vix_pct: number | null;
  band: string | null;
  /** quiet / heavy inside normal, panic inside stressed. Plans before 2026-10-23 have none. */
  sub?: string | null;
  shape: string | null;
  bias: "long" | "short" | null;
  confirm: string | null;
  spy_em_pct: number | null;
  tape: PlanTape[];
}

/** A contract at the first target: its value there and the option's own R (optcalc._target_fields). */
export interface PlanAtTarget {
  target: number | null;
  target_label: string | null;
  value_at_target: number | null;
  reward_per_contract: number | null;
  risk_per_contract: number | null;
  r: number | null;
}

export interface PlanName {
  sym: string;
  name: string | null;
  side: "long" | "short" | null;
  score: number;
  state: string;
  level: string | null;
  entry: { kind: string; price: number; dist_atr: number } | null;
  last: number | null;
  chg_pct: number | null;
  ext_pct: number | null;
  rs_spy: number | null;
  rvol: number | null;
  levels: { pdh: number | null; pdl: number | null; pmh: number | null; pml: number | null; pdc?: number | null };
  atr_d: number | null;
  atr_b: number | null;
  earnings: { date: string; when: string; days: number } | null;
  options: {
    iv30: number | null;
    iv_rv: number | null;
    premium: string | null;
    iv_rank: number | null;
    em_front_pct: number | null;
    em_weekly_pct: number | null;
    /** The front straddle's bounds and days to expiry — today's expected move when 0. */
    em_front_dte?: number | null;
    em_front_hi?: number | null;
    em_front_lo?: number | null;
    liquidity: string | null;
    earnings_in: string | null;
    long: { expiry: string; strike: number; right: string; mid: number; delta: number; at_target?: PlanAtTarget | null } | null;
    spread: { expiry: string; strike: number; short_strike: number; mid: number; at_target?: PlanAtTarget | null } | null;
    /** Long or spread, by R at the first target when both are priced, else by premium. Plans before 2026-10-22 have none. */
    structure?: { kind: "long" | "spread" | null; by: "r" | "premium" | null; long_r: number | null; spread_r: number | null } | null;
    /** At-the-money IV per expiry, front to back. */
    term?: Array<{ expiry: string | null; dte: number | null; iv: number | null }>;
    /** The move the chain prices for the report against the last realised. */
    earnings_move?: {
      implied_pct: number | null;
      implied_expiry: string | null;
      event_pct: number | null;
      realised_pct: Array<number | null>;
      avg_abs_pct: number | null;
    } | null;
  } | null;
  /** The daily frame against the live print, and whether the setup is with it. Plans before 2026-10-22 have none. */
  daily?: { trend: string | null; text: string | null; with_side: string | null } | null;
  short_interest?: { pct_float: number | null; days_to_cover: number | null; as_of: string | null; squeeze_risk: boolean } | null;
  headlines: Array<{
    id: string;
    title: string;
    publisher: string;
    age_min: number | null;
    /** rating · earnings · filing · news — plans written before 2026-10-13 have none. */
    kind?: string;
    url?: string;
  }>;
  /** The name's sector SPDR and its move against SPY today, in percentage points. */
  sector?: { key: string; label: string | null; rs_day: number | null } | null;
  /** The macro drivers this name answers to, with today's move and the verdict FOR THE STOCK. */
  macro?: PlanDriver[];
  filings?: Array<{ form: string; filed: string; desc: string }>;
  /** False when the name's news had not been read yet (just after a restart). */
  news_loaded?: boolean;
  /** Today's option volume: put ÷ call, which way it leans, and the busiest strike. */
  flow?: PlanFlow | null;
  /** Today's pre-market volume, and that as a share of the twenty-session average day. */
  premkt?: { volume: number | null; pct_adv: number | null } | null;
  /** Big caps in the same sector reporting from today through three trading days out. */
  peers?: Array<{ sym: string; date: string; when: string; days: number }>;
  /** Twenty-session average daily volume. */
  adv20?: number | null;
  /**
   * THE PRE-OPEN MODE (2026-10-14). Whether PMH / PML are still forming; the
   * final levels a plan may take as its target, nearest first; the strategy's
   * own invalidation; and, before the open, its trigger as an if/then.
   */
  pm_forming?: boolean;
  targets?: Array<{ label: string; price: number }>;
  invalid_if?: string | null;
  open_if?: string | null;
}

export interface PlanFlowStrike {
  strike: number;
  right: "C" | "P";
  expiry: string;
  volume: number;
  oi?: number;
}

export interface PlanFlow {
  pc_vol: number | null;
  lean: "calls" | "puts" | "balanced" | null;
  /** The busiest strike — one, or the chain's top few (the first is the busiest). */
  top?: PlanFlowStrike | PlanFlowStrike[] | null;
}

export interface PlanDriver {
  driver: string;
  label: string;
  move: string;
  effect: "tailwind" | "headwind" | "flat";
  why: string;
}

/** The day's macro, once per plan: the moves and the market's high-impact headlines. */
export interface PlanMacro {
  moves: Array<{ key: string; label: string; unit: string; move: number; text: string }>;
  headlines: Array<{ id: string; title: string; publisher: string; desk: string; age_min: number | null }>;
}

export interface PlanFacts {
  as_of: string;
  session: PlanSession;
  trading_day: string;
  regime: PlanRegime;
  names: PlanName[];
  calendar: Array<{ et: string; title: string; score: number; released: boolean }>;
  /** Plans written before 2026-10-13 have no macro block. */
  macro?: PlanMacro;
  partial: string[];
  /** The tape's conviction count — what each plan's conviction is capped by. */
  conviction?: Conviction | null;
  breadth?: Breadth | null;
  fuel?: Fuel[];
  /** Today's prints read against consensus — newer plans' version of `calendar`. */
  prints?: Print[];
  fed?: FedPath | null;
  /** Null when the gamma feed was off or down. */
  gamma?: GammaEtf[] | null;
}

export interface PlanItem {
  sym: string;
  side: "long" | "short";
  conviction: 1 | 2 | 3 | 4 | 5;
  plan: string;
  trigger: string;
  invalidation: string;
  target: string;
  options: string;
  why: string[];
  /** Why the collector lowered the model's conviction — "tape weak — at most 3". */
  capped?: string | null;
  /** The model's own number, kept when a cap lowered it. */
  conviction_model?: number | null;
  /** Fields the collector replaced because they broke the strategy, with the model's words. */
  fixes?: Array<{ field: "trigger" | "target" | "invalidation"; was: string; why: string }>;
}

export interface PlanBody {
  headline: string;
  market: string;
  plans: PlanItem[];
  avoid: Array<{ sym: string; why: string }>;
  /** Names the model carded with "no trade" — one line each: what would make it a trade. */
  watch?: Array<{ sym: string; why: string }>;
  /** The day's clock. Written by the collector from the calendar since 2026-10-14. */
  timing: string[];
  /** The day's high-impact releases still to come, as risks — the collector's, from the calendar. */
  events?: string[];
  /** The model's own risks: a level, the tape, a name's weak point. */
  risks: string[];
}

export interface Plan {
  id: string;
  created_utc: string;
  et_label: string;
  model: string;
  error?: string | null;
  raw?: string | null;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
  /** Exactly what the model saw. */
  digest: unknown;
  /** Figures the model printed that the facts do not contain — checked by the collector. */
  unverified?: string[];
  attempts?: unknown[];
  facts: PlanFacts;
  plan: PlanBody | null;
}

export interface PlanStub {
  id: string;
  et_label: string;
  headline: string | null;
  model: string;
  /** How many names it planned. */
  n: number;
}

export interface PlanFeed {
  config: { enabled: boolean; model: string };
  latest: Plan | null;
  history: PlanStub[];
  /** Set by the route handler when the collector could not be reached. */
  offline?: { reason: string; api: string };
  /** The plan being written right now, if any, or the job a poll settled. */
  job?: NoteJob | null;
}

/** How many of the scanner's top names a plan covers. */
export type PlanTop = 4 | 6 | 8 | 10;
export const PLAN_TOPS: readonly PlanTop[] = [4, 6, 8, 10];
