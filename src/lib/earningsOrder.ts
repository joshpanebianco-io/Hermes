/**
 * The Earnings panel's days, nearest today first (owner, 2026-11-06). Today, then
 * the day either side of it, working outward, and on a tie the day just gone
 * comes before the day ahead: last night's results are what is moving this
 * morning. It replaced "ahead, then past", which left yesterday's prints under a
 * run of watchlist names reporting in December.
 *
 * Without a usable `today` it falls back to date order. Pure.
 */
/**
 * The same days once the session is over: today, then what is coming (nearest
 * first), then what has been (latest first).
 *
 * `nearestFirst` puts the day just gone above the days ahead because last night's
 * results are what is moving this morning. By the close they have been traded for a
 * whole session, and on a Friday evening five of Thursday's reports sat above
 * Tuesday's NVDA (2026-11-14). After the close, and through a weekend, what is next
 * leads. Before the close the order is `nearestFirst`, unchanged.
 */
export function aheadFirst<T>(days: readonly (readonly [string, T])[], today: string): (readonly [string, T])[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(today)) return nearestFirst(days, today);
  const rank = (d: string) => (d === today ? 0 : d > today ? 1 : 2);
  return [...days].sort(([a], [b]) => rank(a) - rank(b) || (a > today ? a.localeCompare(b) : b.localeCompare(a)));
}

export function nearestFirst<T>(days: readonly (readonly [string, T])[], today: string): (readonly [string, T])[] {
  const dayNumber = (d: string) => Math.round(Date.parse(`${d}T12:00:00Z`) / 86_400_000);
  const now = dayNumber(today);
  const byDate = (a: string, b: string) => a.localeCompare(b);
  return [...days].sort(([a], [b]) => {
    if (Number.isNaN(now)) return byDate(a, b);
    return Math.abs(dayNumber(a) - now) - Math.abs(dayNumber(b) - now) || byDate(a, b);
  });
}
