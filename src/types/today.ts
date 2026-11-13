import type { Catalyst, ScanRow } from "@/types/scanner";

/** GET /api/scanner/today — the Stocks tab's one list (server today.py). */

export type PhaseKey = "after" | "overnight" | "pre" | "session";

export interface TodayPhase {
  key: PhaseKey;
  label: string;
  title: string;
  /** The session the list is for: today, or the next one in the evening and overnight. */
  day: string;
  ends_utc: string;
  ends_in_min: number;
  next: PhaseKey;
  next_label: string;
}

export interface TodayTrigger {
  level: "PMH" | "PDH" | "PML" | "PDL";
  price: number;
  /** Already through it: the trigger is its retest, not its break. */
  held: boolean;
}

export interface TodaySetup {
  state: string | null;
  side: "long" | "short" | null;
  level: string | null;
  note: string | null;
  entry?: { kind?: string; price?: number; dist_atr?: number } | null;
  lost_vwap?: boolean | null;
}

export interface TodayRow {
  rank: number;
  sym: string;
  name: string | null;
  sector: string | null;
  cap?: number | null;
  last: number | null;
  /** A live trade from the stream, not the delayed screener's. */
  live: boolean;
  /** The move since the previous close, %; `move` says which session it was made in. */
  chg: number | null;
  move: "pre" | "after" | "day";
  score: number | null;
  score_max: number;
  /** "in play" before the bell and in the evening; "setup" in the session. */
  score_kind: "in play" | "setup";
  raw?: number | null;
  gated?: boolean;
  why: string[];
  story: Catalyst | null;
  lean: "long" | "short" | null;
  plan: { long: TodayTrigger | null; short: TodayTrigger | null } | null;
  setup: TodaySetup | null;
  levels: { pdh?: number | null; pdl?: number | null; pmh?: number | null; pml?: number | null; pdc?: number | null; vwap?: number | null };
  gap_atr: number | null;
  vol_pct: number | null;
  rvol: number | null;
  stage: number | null;
  fav: boolean;
  tracked: boolean;
  /** Came into the top ten in the last fifteen minutes. */
  new: boolean;
  /** The open's order: 0 an entry live, 1 through a level, 2 not triggered, 3 failed. */
  group?: number;
  status?: string;
  spark?: number[] | null;
  /** The row as the Setups table draws it (server today.scan_row): the engine's own for a
   *  tracked name, built from the wide read for the rest; its score is the phase's. */
  row: ScanRow;
}

export interface TodayPayload {
  ok: boolean;
  phase: TodayPhase;
  phases: { key: PhaseKey; label: string }[];
  rows: TodayRow[];
  note: string | null;
  /** The favourites the engine tracks today, or null while it tracks every pin. */
  favs_tracked: string[] | null;
  updated_utc: string;
  /** Set on a replay of a past day (the preview), never by the live collector. */
  replay?: string;
}
