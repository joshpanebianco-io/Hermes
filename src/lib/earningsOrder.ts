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

/**
 * The card's window: the collector's own (server sources/earnings.collect, two days
 * back and DAYS_AHEAD on, fourteen since the owner asked to see further ahead on
 * 2026-11-17; it was four), for the Scanner's names as for the large caps (owner, the
 * same day: "do what you recommend"). A Scanner name's next report reaches months ahead
 * since its history reads TradingView, and the card listed 29 of them, 26 Nov to
 * 4 Mar 2027 and mostly with no time of day. Without a usable day either way, a row is
 * kept. Pure.
 */
export const EARN_BACK = 2;
export const EARN_AHEAD = 14;
export function inWindow(date: string, today: string, back = EARN_BACK, ahead = EARN_AHEAD): boolean {
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  if (!iso.test(date) || !iso.test(today)) return true;
  const n = (d: string) => Math.round(Date.parse(`${d}T12:00:00Z`) / 86_400_000);
  const k = n(date) - n(today);
  return k >= -back && k <= ahead;
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
