/**
 * The Market Report sheet's pure parts (components/panels/Brief.tsx MarketReportView).
 *
 * THE SHEET WAS TRIMMED (owner, 2026-11-17: "get rid of our more drop down and refine the
 * structure ... get rid of snapshot, calendar, maybe a brief summary on sector rotation?
 * and keep headlines that move price", then "keep the calendar in the first section and
 * only include things that affect us for every current day"). The More button and its
 * tables went; the calendar beside the risks lists the report's own trading day; the
 * headlines the model picked and a short rotation block are a second pair under it.
 */
import type { BriefCatalyst, BriefMover, BriefRatio } from "@/types/terminal";

const ET_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
});
const DAY_MS = 86_400_000;

/**
 * The trading day an instant belongs to, as "2026-11-17": its New York date, the next
 * day from 18:00 ET (the futures day opens then: Japan's GDP at 18:50 on a Sunday is
 * Monday's), and a Saturday or Sunday rolls on to the Monday. Market holidays are not
 * skipped: on one the day simply has the holiday's own row. Null for no instant.
 */
export function tradingDay(sec: number | null | undefined): string | null {
  if (sec == null || !Number.isFinite(sec)) return null;
  const p = Object.fromEntries(ET_PARTS.formatToParts(new Date(sec * 1000)).map((x) => [x.type, x.value]));
  let d = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day));
  if (Number(p.hour) >= 18) d += DAY_MS;
  const wd = new Date(d).getUTCDay();
  if (wd === 6) d += 2 * DAY_MS;
  else if (wd === 0) d += DAY_MS;
  return new Date(d).toISOString().slice(0, 10);
}

/**
 * Whether a calendar row belongs on a report's Calendar: inside the report's trading
 * day, and something that reaches its books. America's releases, the Fed, the auctions,
 * the earnings and a market holiday always do; another country's print does when it
 * lands in the session the report is about (Japan's GDP for an Asia note, the UK's jobs
 * for a London one), and not otherwise (the UK's 02:00 jobs on a New York note).
 */
export function onTheDay(
  c: Pick<BriefCatalyst, "ts" | "kind" | "country" | "lands_in_session">,
  day: string,
  session: string,
): boolean {
  if (tradingDay(c.ts) !== day) return false;
  if (c.kind !== "data") return true;
  if (c.country === "United States") return true;
  const lands = c.lands_in_session;
  return session === "ny" ? lands === "premkt" || lands === "ny" : lands === session;
}

/*
 * WHAT CAN MOVE PRICES (brief_version 4; owner, 2026-11-19: a report "given to a ceo ...
 * list what things can impact prices going into a session, eg news, macro events,
 * headlines, earnings, geopolitics, vix, economic calender events on the day or earlier in
 * the week ... and then a brief summary on why"). The model picks the items; the page
 * files each under its kind, in a fixed order, so the list reads the same way every day.
 */
export type MoverSection = "data" | "week" | "fed" | "earnings" | "news" | "rates" | "vol";

export const MOVER_SECTIONS: ReadonlyArray<{ key: MoverSection; title: string; sub?: string }> = [
  { key: "data", title: "Economic data" },
  { key: "week", title: "Earlier this week", sub: "already in the price" },
  { key: "fed", title: "Central bank & Treasury" },
  { key: "earnings", title: "Earnings" },
  { key: "news", title: "Geopolitics & headlines" },
  { key: "rates", title: "Rates & dollar" },
  { key: "vol", title: "Volatility & positioning", sub: "how far moves run, not which way" },
];

/**
 * Which section an item sits in: rates and the dollar, the VIX and positioning by their
 * ids; a headline under the news; a calendar row by its kind, a release or a Fed event
 * from before the report's trading day under "Earlier this week" (`earlier`, or its day).
 * Null for an id the facts do not have. Pure.
 */
export function moverSection(
  id: string,
  cat: Pick<BriefCatalyst, "kind" | "ts" | "earlier"> | undefined,
  headline: boolean,
  day: string | null,
): MoverSection | null {
  if (id === "rates") return "rates";
  if (id === "vix" || id === "positioning") return "vol";
  if (headline) return "news";
  if (!cat) return null;
  if (cat.kind === "earnings") return "earnings";
  const before = cat.earlier === true || (day != null && cat.ts != null && (tradingDay(cat.ts) ?? day) < day);
  if (before && (cat.kind === "data" || cat.kind === "fed")) return "week";
  if (cat.kind === "fed" || cat.kind === "auction") return "fed";
  return "data";
}

/**
 * The list in its sections, in MOVER_SECTIONS order, empty sections left out. Inside a
 * section a calendar row goes by its time; anything else keeps the model's order, which
 * is most important first. Pure.
 */
export function groupMovers<M extends Pick<BriefMover, "id">>(
  movers: readonly M[],
  catOf: (id: string) => Pick<BriefCatalyst, "kind" | "ts" | "earlier"> | undefined,
  isHeadline: (id: string) => boolean,
  day: string | null,
): { key: MoverSection; title: string; sub?: string; items: M[] }[] {
  const by = new Map<MoverSection, { m: M; i: number }[]>();
  movers.forEach((m, i) => {
    const s = moverSection(m.id, catOf(m.id), isHeadline(m.id), day);
    if (s) by.set(s, [...(by.get(s) ?? []), { m, i }]);
  });
  return MOVER_SECTIONS.flatMap((sec) => {
    const rows = by.get(sec.key);
    if (!rows?.length) return [];
    const items = [...rows]
      .sort((a, b) => {
        const ta = catOf(a.m.id)?.ts;
        const tb = catOf(b.m.id)?.ts;
        return ta != null && tb != null ? ta - tb : a.i - b.i;
      })
      .map((x) => x.m);
    return [{ ...sec, items }];
  });
}

/** A ratio leg in words. */
const WORD: Record<string, string> = {
  XLK: "Tech", XLU: "Utilities", SPY: "S&P 500", XLC: "Comms", XLP: "Staples", QQQ: "Nasdaq 100",
  IWM: "Russell 2000", GDX: "Gold miners", GLD: "Gold", Gold: "Gold", Silver: "Silver",
};
const word = (leg: string) => WORD[leg] ?? leg;

export interface RotationLine {
  /** The leg that leads the line: "Tech". */
  lead: string;
  /** What it is measured against, and its five-day change against each. */
  parts: { vs: string; chg: number }[];
}

/**
 * The five-day ratios as lines, one a leading leg, in the order the report lists them:
 * "Tech −4.3% vs Utilities · −1.9% vs S&P 500". A ratio with no change is left out. Pure.
 */
export function rotationLines(ratios: readonly BriefRatio[]): RotationLine[] {
  const out: RotationLine[] = [];
  for (const r of ratios) {
    const [a, b] = r.id.split("/");
    if (!a || !b || r.chg_5d == null) continue;
    const line = out.find((l) => l.lead === word(a));
    const part = { vs: word(b), chg: r.chg_5d };
    if (line) line.parts.push(part);
    else out.push({ lead: word(a), parts: [part] });
  }
  return out;
}

/**
 * The one-word read of the equity ratios, or null: "Defensives leading" when tech is
 * losing to utilities and staples are beating the S&P over five days (each beyond the
 * report's own flat band, `dir`), "Growth leading" the other way round. Which sectors
 * lead is context, not a side: rotation does not vote in the bias (bias.py: the
 * participation family counts sectors up against down, in the session only). Pure.
 */
export function rotationRead(ratios: readonly BriefRatio[]): string | null {
  const dirOf = (id: string) => ratios.find((r) => r.id === id)?.dir;
  const tech = dirOf("XLK/XLU");
  const staples = dirOf("XLP/SPY");
  if (tech === "down" && staples === "up") return "Defensives leading";
  if (tech === "up" && staples === "down") return "Growth leading";
  return null;
}
