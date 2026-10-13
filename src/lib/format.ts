/**
 * Number formatting — one place, because a terminal that prints 29453.25 in
 * one panel and 29,453.3 in another has two voices.
 *
 * PRECISION FOLLOWS MAGNITUDE, NOT TYPE. A single rule ("two decimals") gives
 * 78382.77 for bitcoin and 2.89 for natural gas, and only one of those is
 * readable — the first has four digits of noise and the second is right. So
 * the decimal count is chosen from how big the number is, which is the same
 * judgement a person makes without thinking about it.
 */

export function num(v: number | null | undefined, dp?: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const d = dp ?? autoDp(v);
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

/** Decimals appropriate to the magnitude. */
export function autoDp(v: number): number {
  const a = Math.abs(v);
  if (a >= 10000) return 0;
  if (a >= 1000) return 1;
  if (a >= 100) return 2;
  if (a >= 1) return 2;
  if (a >= 0.01) return 4;
  return 5;
}

/** A signed percentage, always with its sign — "+0.42%". */
export function pct(v: number | null | undefined, dp = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%`;
}

/** A signed plain number, always with its sign. */
export function signed(v: number | null | undefined, dp?: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const d = dp ?? autoDp(v);
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })}`;
}

export function bp(v: number | null | undefined, dp = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(dp)}bp`;
}

/**
 * The direction class for a change. Returns "flat" for exactly zero AND for
 * null — an unknown change must not be painted green.
 */
export function dir(v: number | null | undefined): "up" | "down" | "flat" {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}

/** Compact volume: 91,573 → "91.6K". */
export function compact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v));
}

/**
 * "14m", "3h". Relative rather than absolute because the question a reader has
 * about a headline is how old it is, not what o'clock it was filed — and the
 * answer to the second requires arithmetic they should not have to do while
 * scanning.
 *
 * `now` IS REQUIRED AND MAY BE NULL, and that is not fussiness. Defaulting it
 * to `Date.now()` meant the server rendered "25m" at request time and the
 * browser rendered "26m" a minute later at hydration — a mismatch React reports
 * and repairs by throwing the server's markup away. Callers pass a clock that
 * is null until mounted, so the first paint carries no stamp and the stamps
 * appear a frame later, identical on both sides. GEXYGEN's WireTicker takes the
 * same nullable clock for the same reason.
 */
export function ago(utc: string | null | undefined, now: number | null): string {
  if (!utc || now === null) return "";
  const t = Date.parse(utc);
  if (Number.isNaN(t)) return "";
  const m = Math.floor((now - t) / 60000);
  if (m < 0) return "now";
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

/** Minutes as a countdown — "84m", "2h 24m", "3d". */
export function inMin(m: number | null | undefined): string {
  if (m === null || m === undefined || !Number.isFinite(m)) return "—";
  if (m < 1) return "now";
  if (m < 60) return `${Math.round(m)}m`;
  const h = Math.floor(m / 60);
  const rem = Math.round(m % 60);
  if (h < 24) return rem ? `${h}h ${rem}m` : `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

/**
 * An age rounded to what `age()` prints — so a module's props change when its
 * chip's TEXT would, not every poll as the raw minutes creep up by 0.33. That
 * is what lets a memoised panel skip a poll that changed nothing it shows.
 */
export function ageStep(m: number | null | undefined): number | null | undefined {
  if (m === null || m === undefined || !Number.isFinite(m)) return m;
  if (m < 1) return 0;
  if (m < 60) return Math.round(m);
  return Math.round(m / 6) * 6;
}

/** An age in minutes, for the freshness chips on each module. */
export function age(m: number | null | undefined): string {
  if (m === null || m === undefined || !Number.isFinite(m)) return "—";
  if (m < 1) return "live";
  if (m < 60) return `${Math.round(m)}m`;
  return `${(m / 60).toFixed(1)}h`;
}
