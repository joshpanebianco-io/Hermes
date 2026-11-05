/**
 * A non-negative integer query value, clamped; anything else falls back. Pure,
 * and free of imports so its test runs without a bundler.
 *
 * A MISSING VALUE IS NOT A ZERO (2026-11-05). `Number(null)` is 0, a perfectly
 * good integer, so an absent `limit` went to the collector as `limit=0`, which it
 * refuses. The signal log's first request names no limit: it answered 422 and
 * `latest: 0`, the log then asked for the events after id 0, and the Signal log
 * tab showed an error over the OLDEST five hundred events, from mid-October, as
 * "newest first". The fallback here had never once fired for a missing value.
 */
export function intParam(v: string | null, fallback: number, max: number): number {
  if (v == null || v.trim() === "") return fallback;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 ? Math.min(n, max) : fallback;
}
