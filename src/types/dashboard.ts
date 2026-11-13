import type { ScanRow, ScanSession, Side, Verdict, WideBasis } from "@/types/scanner";
import type { BreadthAll } from "@/types/terminal";

/** GET /api/dashboard — the session on one page (server dashboard.py). */

export type DashRow = Pick<
  ScanRow,
  "sym" | "name" | "sector" | "last" | "chg_pct" | "ext_pct" | "rvol" | "trend" | "levels" | "broken" | "setup" | "catalyst" | "stage" | "spark"
> & { score: { total: number; side: Side | null } };

export interface DashStory {
  syms: string[];
  tag: string;
  title: string;
  url: string;
  provider: string;
  age_min: number;
}

/** One name on the In play card: the pool's rank entry and the engine's verdict on it. */
export interface DashInPlayRow {
  sym: string;
  name: string | null;
  score: number;
  reason: string;
  gap_atr: number | null;
  vol_pct: number | null;
  through: "PDH" | "PDL" | null;
  day: number | null;
  reports: string | null;
  last: number | null;
  verdict: Verdict | null;
}

export interface DashInPlay {
  rows: DashInPlayRow[];
  qualified: number | null;
  screened: number | null;
  basis: string;
  promoted: number;
  marks_done: string[];
  next_mark: string | null;
  slots: number | null;
  /** The most a name can score on the pool's rank, for the row's bar. Absent from an older collector. */
  score_max?: number | null;
  on: boolean;
}

export interface DashFocus {
  key: string;
  label: string;
  pct: number | null;
  rs: number;
}

export interface DashSetup {
  key: "day23" | "pdh" | "pdl";
  word: string;
  view: "day23" | "breakouts";
  chip: "through" | null;
  n: number | null;
}

export interface DashboardPayload {
  ok: boolean;
  session: ScanSession;
  trading_day: string;
  read: {
    title: string;
    lines: string[];
    foot: string;
    reports: Array<{ sym: string; when: "pre" | "after" | "unspecified" }>;
  };
  plan: {
    bias: {
      side: Side | null;
      score: number | null;
      grade: string | null;
      live: number | null;
      total: number | null;
      cap: number | null;
      /** Under half the session's weight could vote: the chip prints the count. Absent from an older collector. */
      thin?: boolean | null;
    };
    focus: DashFocus[];
    themes: DashFocus[];
    setups: DashSetup[];
    event: { title: string; et: string; in_min: number; score: number } | null;
    /** False when the economic calendar is not loading. Absent from an older collector. */
    calendar_ok?: boolean | null;
  };
  breadth: Pick<BreadthAll, "basis" | "floor" | "names" | "of" | "advancers" | "decliners" | "buckets"> | null;
  top: DashRow[];
  /** The pool's rank with the engine's verdict; null until the pool has been read. */
  inplay: DashInPlay | null;
  stories: DashStory[];
  news_live: boolean;
  rotation: Array<{ key: string; label: string; day_pct: number | null; rs_day: number | null; leaders: string[] }>;
  offline?: { reason: string; api: string };
}

/* -------------------------------------------------------------------------- */
/* GET /api/scanner/sectors (sources/universe.py heatmap)                      */
/* -------------------------------------------------------------------------- */

export type HeatSpan = "day" | "week" | "month";

export interface SpanRead {
  up: number;
  down: number;
  /** The median stock: one 40% name cannot carry it the way it carries an average. */
  median: number | null;
  leaders: Array<{ sym: string; chg: number }>;
}

interface GroupRead {
  /** Stocks in the group at the floor ($2bn+). */
  names: number;
  day: SpanRead;
  week: SpanRead;
  month: SpanRead;
}

export interface HeatCard extends GroupRead {
  key: string;
  label: string;
  last: number | null;
  day_pct: number | null;
  week_pct: number | null;
  month_pct: number | null;
  rs_day: number | null;
  rs_week: number | null;
  rs_month: number | null;
  kind: "sector" | "theme";
  /** Ranks with the eleven sectors. */
  top: boolean;
  /** The sector a theme sits under; null is the Global menu. */
  parent: string | null;
  /** Where its stocks come from: every name in the group, the fund's top ten, or a hand-written list. */
  list: "sector" | "industry" | "fund" | "hand";
}

export interface HeatIndustry extends GroupRead {
  key: string;
  label: string;
  sector: string | null;
}

export interface HeatmapPayload {
  ok: boolean;
  basis: WideBasis;
  day: string;
  /** The session the cards' moves are about. */
  cards_day: string;
  read_age_min: number | null;
  delayed_min: number;
  source: string;
  error: string | null;
  floor: number;
  names: number;
  spy: { day: number | null; week: number | null; month: number | null };
  cards: HeatCard[];
  industries: HeatIndustry[];
  offline?: { reason: string; api: string };
}
