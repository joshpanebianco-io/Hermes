import type { ScanRow, ScanSession, Side, Verdict, WideBasis } from "@/types/scanner";
import type { BreadthAll } from "@/types/terminal";

/** GET /api/dashboard — the session on one page (server dashboard.py). */

export type DashRow = Pick<
  ScanRow,
  "sym" | "name" | "sector" | "last" | "chg_pct" | "ext_pct" | "rvol" | "trend" | "levels" | "broken" | "setup" | "catalyst" | "stage" | "spark" | "spark_ref"
> & {
  /** `kind` "inplay" before the bell: how in play the name is, as the Scanner list scores it. */
  score: { total: number; side: Side | null; kind?: "inplay" | null };
};

export interface DashStory {
  syms: string[];
  tag: string;
  title: string;
  url: string;
  provider: string;
  age_min: number;
}

/** A Today row of the High impact news card (server impact.py): a print, the Fed, reports, an IPO. */
export interface DashImpactRow {
  /** "08:30", or "Before" / "After" (the open, the close) / "Today" (an IPO). */
  t: string;
  /** "US data", "Fed", "Earnings", "IPO", or a country ("Japan", "UK", "Euro area"). */
  kind: string;
  line: string;
  /** Out already (a print released, a speaker who has spoken, a report in). */
  done: boolean;
  url?: string | null;
}

/** A headline of the High impact news card: the wire's high impact, then geopolitics, energy, policy. */
export interface DashImpactHead {
  t: string;
  kind: string;
  high: boolean;
  title: string;
  url: string | null;
  publisher: string | null;
  age_min: number;
}

export interface DashImpact {
  today: DashImpactRow[];
  heads: DashImpactHead[];
  /** The wire is reading. */
  live: boolean;
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

export interface DashOverview {
  id: string;
  et_label: string;
  created_utc: string | null;
  /** Written by the 09:00 ET clock rather than the button. */
  auto: boolean;
  trading_day: string | null;
  headline: string;
  /** What it means for the list. */
  focus: string;
  /** Up to three: the calendar's releases first, then the model's. */
  risks: string[];
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
      /** Under half the session's weight could vote: the grade is weak at most. Not drawn since 2026-11-15, when the score came to say it. */
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
  /** The latest market overview's card (server overview.latest_card), in In play's place since 2026-11-13; on no card since 2026-11-16. */
  overview?: DashOverview | null;
  stories: DashStory[];
  news_live: boolean;
  /** The High impact news card; absent from a collector older than 2026-11-19. */
  impact?: DashImpact;
  rotation: Array<{ key: string; label: string; day_pct: number | null; rs_day: number | null; leaders: string[] }>;
  /** "pre" before the bell: the focus lists and the rotation row are the funds' pre-market moves (2026-11-16). */
  sectors_basis?: "pre" | "session";
  /**
   * How long ago each card's figures were read, in minutes at this build (server
   * dashboard.card_ages): the oldest block a card is drawn from. Null for a block not read
   * yet; absent from a collector older than 2026-11-20.
   */
  ages?: Partial<Record<DashCard, number | null>>;
  offline?: { reason: string; api: string };
}

/** The cards with an age of their own; the Futures card's is the Terminal poll's quotes. */
export type DashCard = "plan" | "breadth" | "top" | "impact" | "stories" | "rotation";

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
  /** The sector a theme sits under; null is a theme under no sector (the two China funds), reached by its card. */
  parent: string | null;
  /** Where its stocks come from: every name in the group, the fund's top ten, or a hand-written list. */
  list: "sector" | "industry" | "fund" | "hand";
  /**
   * Outside the session (server universe.heatmap, 2026-11-16): the fund's last trade
   * before the bell or after the close, against its last regular close, and that against
   * SPY's; null when it has not traded in the stretch the cards show.
   */
  ext_pct?: number | null;
  rs_ext?: number | null;
  /** When that trade was (epoch seconds), and how many five-minute bars in the stretch had one. */
  ext_at?: number | null;
  ext_bars?: number | null;
}

/** Which stretch the cards show (server universe.cards_phase). */
export type CardsPhase = "pre" | "rth" | "post" | "last";

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
  /** Before the bell the cards are the pre-market's; after the close the after hours ride beside the day. */
  cards_phase?: CardsPhase;
  /** The day the extended trades are on, and SPY's last one (epoch seconds). */
  ext_day?: string | null;
  ext_at?: number | null;
  /** The cards' up/down counts and the industries are the stocks' own pre-market moves. */
  counts_pre?: boolean;
  read_age_min: number | null;
  delayed_min: number;
  source: string;
  error: string | null;
  floor: number;
  names: number;
  spy: { day: number | null; week: number | null; month: number | null; ext?: number | null };
  cards: HeatCard[];
  industries: HeatIndustry[];
  offline?: { reason: string; api: string };
}
