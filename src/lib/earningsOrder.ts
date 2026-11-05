/**
 * The Earnings panel's days, nearest today first (owner, 2026-11-06). Today, then
 * the day either side of it, working outward, and on a tie the day just gone
 * comes before the day ahead: last night's results are what is moving this
 * morning. It replaced "ahead, then past", which left yesterday's prints under a
 * run of watchlist names reporting in December.
 *
 * Without a usable `today` it falls back to date order. Pure.
 */
export function nearestFirst<T>(days: readonly (readonly [string, T])[], today: string): (readonly [string, T])[] {
  const dayNumber = (d: string) => Math.round(Date.parse(`${d}T12:00:00Z`) / 86_400_000);
  const now = dayNumber(today);
  const byDate = (a: string, b: string) => a.localeCompare(b);
  return [...days].sort(([a], [b]) => {
    if (Number.isNaN(now)) return byDate(a, b);
    return Math.abs(dayNumber(a) - now) - Math.abs(dayNumber(b) - now) || byDate(a, b);
  });
}
