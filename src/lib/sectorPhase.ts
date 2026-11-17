import type { CardsPhase, HeatCard, HeatSpan } from "@/types/dashboard";

/**
 * What the Sectors cards say about the stretch of trading they show (owner, 2026-11-16:
 * "make the app update as to what they're actually doing. right now im missing the
 * sectors information going into the open"; server universe.heatmap has the rest).
 *
 *   pre    before the bell: a card's day is the fund's pre-market move against the last
 *          close, ranked and tinted by it, with the last session's move on a small line
 *          beside it ("Fri −2.01%").
 *   post   after the close, overnight and over a weekend: the day is the session's, with
 *          the after-hours move beside it ("AH +0.35%").
 *   rth    the session: as it always was.
 *
 * A fund trades thinly outside the session and Yahoo gives no volume for it then, so a
 * card's hover says when its last trade was and in how many five-minute bars it traded.
 *
 * Pure.
 */

const FMT = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** "06:40", New York's, from epoch seconds. */
export function etHm(sec: number | null | undefined): string {
  return sec == null ? "—" : FMT.format(new Date(sec * 1000));
}

/** "Fri" from "2026-11-13". */
export function weekday(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
}

const signed = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`;

/** Whether a card's day is the pre-market's: before the bell, on the 1D span. */
export const showsPre = (phase: CardsPhase | undefined, span: HeatSpan) => phase === "pre" && span === "day";

/** The card's figure for the span: its pre-market move before the bell on 1D, else the span's. */
export function cardPct(c: HeatCard, phase: CardsPhase | undefined, span: HeatSpan): number | null {
  return showsPre(phase, span) ? (c.ext_pct ?? null) : c[`${span}_pct`];
}

/** Its distance from SPY over the same. */
export function cardRs(c: HeatCard, phase: CardsPhase | undefined, span: HeatSpan): number | null {
  return showsPre(phase, span) ? (c.rs_ext ?? null) : c[`rs_${span}`];
}

/**
 * The small line beside a card's figure, and its hover: the last session's move before
 * the bell, the after-hours move after the close. Null in the session, on a longer span,
 * or with nothing to say.
 */
export function cardNote(c: HeatCard, phase: CardsPhase | undefined, span: HeatSpan, lastDay: string): { text: string; title: string } | null {
  if (span !== "day") return null;
  const traded =
    c.ext_at != null
      ? `Last trade ${etHm(c.ext_at)} ET, in ${c.ext_bars ?? 0} of the five-minute bars since ${phase === "pre" ? "04:00" : "the close"}. These funds trade thinly outside the session.`
      : "";
  if (phase === "pre") {
    const last = c.day_pct != null ? `${weekday(lastDay)} ${signed(c.day_pct)}` : "";
    if (c.ext_pct == null) return { text: last, title: `No pre-market trade in ${c.key} yet: the figure waits for one. ${last ? `${weekday(lastDay)} was ${signed(c.day_pct as number)}.` : ""}`.trim() };
    return { text: last, title: `${c.key} ${signed(c.ext_pct)} before the bell against ${weekday(lastDay)}'s close. ${traded}`.trim() };
  }
  if (phase === "post" && c.ext_pct != null) {
    return { text: `AH ${signed(c.ext_pct)}`, title: `${c.key} ${signed(c.ext_pct)} after the close, against the close. ${traded}`.trim() };
  }
  return null;
}

/** The header's line on what the cards read. */
export function phaseLine(p: { cards_phase?: CardsPhase; cards_day: string; day: string; ext_day?: string | null; ext_at?: number | null }, dayName: (iso: string) => string): string {
  switch (p.cards_phase) {
    case "pre":
      return `Cards read ${dayName(p.ext_day ?? p.day)} pre-market · SPY last traded ${etHm(p.ext_at)} ET`;
    case "post":
      return `Cards read ${dayName(p.ext_day ?? p.cards_day)} · after hours to ${etHm(p.ext_at)} ET`;
    case "rth":
      return `Cards read ${dayName(p.day)}`;
    default:
      return `Cards read ${dayName(p.cards_day)}`;
  }
}
