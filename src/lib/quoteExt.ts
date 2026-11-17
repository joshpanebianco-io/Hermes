import type { IndexMovers, Quote } from "@/types/terminal";

/**
 * What a figure shows outside the session (the audit of 2026-11-16, after the Sectors
 * cards: "make sure we dont have the same issue we had before with sectors in other
 * places"). At 08:16 ET on a Monday the SPY, QQQ and IWM tiles read Friday's close while
 * SPY traded 0.6% lower, and the Macro tab's index movers read Friday's moves.
 *
 *   a board fund   before the bell its pre-market price and its move against the last
 *                  close, tagged "pre"; after the close its after-hours price and move
 *                  against the close, tagged "AH"; the regular session's on the hover.
 *   index movers   before the bell each name's own pre-market move and its weight times
 *                  that, and what they add up to.
 *
 * Pure.
 */

const FMT = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const signed = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`;
const price = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** A quote as a tile or a board row shows it, with the tag beside its name and the hover's words. */
export function shownQuote(q: Quote): { q: Quote; tag: "pre" | "AH" | null; note: string | null } {
  const x = q.ext;
  if (!x || !Number.isFinite(x.px) || !Number.isFinite(x.pct)) return { q, tag: null, note: null };
  const pre = x.kind === "pre";
  const at = FMT.format(new Date(x.at * 1000));
  const session = q.pct != null ? `${price(q.last)} (${signed(q.pct)} on the day)` : price(q.last);
  return {
    // Live while it trades: a pre-market or after-hours print is not dimmed as closed.
    q: { ...q, last: x.px, pct: x.pct, chg: x.px - q.last, feed: "live" },
    tag: pre ? "pre" : "AH",
    note: `${pre ? "Pre-market" : "After hours"} ${price(x.px)} (${signed(x.pct)} against the ${pre ? "last" : "day's"} close), last trade ${at} ET. The regular session closed ${session}.`,
  };
}

/** The index movers as the panel shows them: each name's pre-market move before the bell. */
export function shownMovers(m: IndexMovers): { m: IndexMovers; pre: boolean } {
  if (m.pre_net == null) return { m, pre: false };
  return {
    pre: true,
    m: {
      ...m,
      net_contribution: m.pre_net,
      members: m.members.map((x) => ({ ...x, pct: x.pre_pct ?? (null as unknown as number), contribution: x.pre_contribution ?? 0 })),
    },
  };
}
