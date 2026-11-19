import type { SourceStatus } from "@/types/terminal";

/** The snapshots' last pass (server sources/webull.py `WebullFeed.snap_status`). */
export interface SnapshotPass {
  on: boolean;
  /** Names read: every wanted name Webull's live connection does not hold. */
  names: number;
  rows: number;
  /** Rows carrying a trade of today's, put into the price books. */
  booked: number;
  calls: number;
  calls_last_min: number;
  /** Seconds to the next pass; null outside every session. */
  every_sec: number | null;
  age_sec: number | null;
  error: string | null;
  idle: boolean;
}

/** Which feed's trade each wanted name's last price is (server collector._feed_coverage). */
export interface FeedCoverage {
  names: number;
  /** No trade of today's from any feed. */
  none: number;
  /** "webull", "webull_snap", "yahoo": names, and the median age of their last trade. */
  by_feed: Record<string, { names: number; age_p50_sec: number }>;
}

/** The live-price feed switch (server collector.feed, GET/POST /api/feed). */
export interface PriceFeed {
  /** "webull": Webull's trades beside Yahoo's stream, the newer trade wins; "yahoo": Yahoo alone. */
  feed: "webull" | "yahoo";
  /** Where the choice came from: the app, NT_PRICE_FEED in .env.local, or the keys. */
  why: string;
  choices: ("webull" | "yahoo")[];
  webull_keys: boolean;
  /** Webull's health, while it runs. */
  webull: SourceStatus | null;
  yahoo: SourceStatus;
  /** Webull's snapshots of the names past the live hundred, while Webull runs. */
  snapshots?: SnapshotPass | null;
  coverage?: FeedCoverage;
}
