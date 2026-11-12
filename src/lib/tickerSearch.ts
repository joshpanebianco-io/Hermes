/**
 * What the ticker search shows as it is typed into, and what it may open.
 *
 * WHY (owner, 2026-11-11: "make it so the search ticker or company search boxes show
 * the stocks when you start typing and also make it so you cant just search for
 * something that doesnt exist"). The box asked the collector for every keystroke and
 * said "Nothing matches. Enter opens it as a ticker anyway" until an answer came, so on
 * a morning when the collector was slow it showed no stocks at all, and Enter opened a
 * slide-out for whatever had been typed. Three things were wrong with what it knew, too:
 *
 *   - THE FUNDS WERE NOT IN IT. The list is the wide scan's, which is stocks: "QQQ",
 *     "GLD" and "XLK" matched nothing, and "SPY" matched Spyre Therapeutics, SpyGlass
 *     and Krispy Kreme. The funds the terminal itself reads are listed here, so they
 *     show without asking anyone.
 *   - ENTER OPENED THE FIRST ROW WHATEVER WAS TYPED, or the text itself when no row
 *     matched. Now a row is opened only when it is a stock on the list or a fund here;
 *     anything else typed as a ticker is one more row, "Check XYZ", and opening it asks
 *     the collector first (lookupVerdict). What does not trade does not open.
 *   - WAITING READ AS "NOTHING MATCHES". Said as what it is now: searching, no match,
 *     or the search not answering.
 *
 * Pure: the dialog (components/ticker/TickerSearch) does the asking.
 */

/** A stock from the collector's list, as /api/scanner/search returns it. */
export interface StockHit {
  sym: string;
  name: string | null;
  cap: number | null;
  sector: string | null;
}

export interface Suggestion {
  sym: string;
  name: string;
  cap: number | null;
  sector: string | null;
  /** A stock on the wide scan's list, or one of the funds below. */
  kind: "stock" | "fund";
}

/**
 * The funds the terminal reads: the three benchmarks and the three the futures are
 * priced beside first (`core`), then the sectors and the themes of the Sectors tab
 * (sources/quotes.py SECTORS and THEMES, by the words that page uses), then the ones
 * the pre-market read knows as funds (sources/premarket.py ETFS).
 */
export const FUNDS: ReadonlyArray<{ sym: string; name: string; core?: true }> = [
  { sym: "SPY", name: "S&P 500", core: true },
  { sym: "QQQ", name: "Nasdaq 100", core: true },
  { sym: "IWM", name: "Russell 2000", core: true },
  { sym: "GLD", name: "Gold", core: true },
  { sym: "SLV", name: "Silver", core: true },
  { sym: "USO", name: "Crude oil", core: true },
  { sym: "DIA", name: "Dow Jones Industrials" },
  { sym: "RSP", name: "S&P 500 equal weight" },
  { sym: "MDY", name: "S&P MidCap 400" },
  { sym: "XLK", name: "Technology sector" },
  { sym: "XLC", name: "Communication sector" },
  { sym: "XLY", name: "Consumer Discretionary sector" },
  { sym: "XLP", name: "Consumer Staples sector" },
  { sym: "XLE", name: "Energy sector" },
  { sym: "XLF", name: "Financials sector" },
  { sym: "XLV", name: "Health Care sector" },
  { sym: "XLI", name: "Industrials sector" },
  { sym: "XLB", name: "Materials sector" },
  { sym: "XLRE", name: "Real Estate sector" },
  { sym: "XLU", name: "Utilities sector" },
  { sym: "SMH", name: "Semiconductors" },
  { sym: "SOXX", name: "Semiconductors (iShares)" },
  { sym: "DRAM", name: "Memory" },
  { sym: "IGV", name: "Software" },
  { sym: "CIBR", name: "Cybersecurity" },
  { sym: "SKYY", name: "Cloud" },
  { sym: "QTUM", name: "Quantum" },
  { sym: "BOTZ", name: "Robotics & AI" },
  { sym: "ARKK", name: "Innovation" },
  { sym: "WGMI", name: "Bitcoin Miners" },
  { sym: "XBI", name: "Biotech" },
  { sym: "IBB", name: "Biotech (iShares)" },
  { sym: "ITA", name: "Aerospace & Defense" },
  { sym: "NASA", name: "Space" },
  { sym: "KRE", name: "Regional Banks" },
  { sym: "KBE", name: "Banks" },
  { sym: "XHB", name: "Homebuilders" },
  { sym: "ITB", name: "Home Construction" },
  { sym: "XRT", name: "Retail" },
  { sym: "JETS", name: "Airlines" },
  { sym: "PAVE", name: "Infrastructure" },
  { sym: "GRID", name: "Smart Grid" },
  { sym: "TAN", name: "Solar" },
  { sym: "URA", name: "Uranium" },
  { sym: "XOP", name: "Oil & Gas E&P" },
  { sym: "GDX", name: "Gold Miners" },
  { sym: "GDXJ", name: "Junior Gold Miners" },
  { sym: "COPX", name: "Copper Miners" },
  { sym: "XME", name: "Metals & Mining" },
  { sym: "KWEB", name: "China Internet" },
  { sym: "FXI", name: "China Large Cap" },
  { sym: "EEM", name: "Emerging Markets" },
  { sym: "EFA", name: "Developed Markets ex-US" },
  { sym: "UNG", name: "Natural Gas" },
  { sym: "TLT", name: "20Y+ Treasuries" },
  { sym: "IEF", name: "7-10Y Treasuries" },
  { sym: "HYG", name: "High Yield Credit" },
  { sym: "LQD", name: "Investment Grade Credit" },
  { sym: "IBIT", name: "Bitcoin (iShares)" },
  { sym: "ETHA", name: "Ethereum (iShares)" },
  { sym: "BITO", name: "Bitcoin Futures" },
  { sym: "VXX", name: "VIX Short-Term Futures" },
  { sym: "UVXY", name: "1.5x VIX Short-Term Futures" },
  { sym: "TQQQ", name: "3x Nasdaq 100" },
  { sym: "SQQQ", name: "-3x Nasdaq 100" },
  { sym: "SOXL", name: "3x Semiconductors" },
  { sym: "SOXS", name: "-3x Semiconductors" },
];

/** The collector's own rule for a symbol (sources/scanner.py `_SYM`). */
const SYMBOL = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;

/** What was typed, as the ticker it would be; null when it cannot be one ("tesla motors"). */
export function tickerShape(q: string): string | null {
  const s = q.trim().toUpperCase();
  return SYMBOL.test(s) ? s : null;
}

/**
 * How well a row answers what was typed, as the collector ranks its own (universe.search):
 * 0 the symbol itself, 1 a symbol that starts with it, 2 a name that starts with it, 3 a
 * name that holds it. Null is no match.
 */
export function matchRank(q: string, sym: string, name: string | null): 0 | 1 | 2 | 3 | null {
  const s = q.trim().toUpperCase();
  if (!s) return null;
  const n = (name ?? "").toUpperCase();
  if (sym.toUpperCase() === s) return 0;
  if (sym.toUpperCase().startsWith(s)) return 1;
  if (n.startsWith(s)) return 2;
  if (n.includes(s)) return 3;
  return null;
}

/**
 * A fund's rank. Its symbol as a stock's; its name by the start of any word in it, and
 * only from three letters: there are seventy of them and their names are short
 * descriptions, so two letters anywhere in one is noise ("nv" found "Investment Grade
 * Credit", "sp" found "Aerospace & Defense"). Any word counts the same, so "oil" is
 * crude oil before it is oil and gas producers: the core fund leads its rank.
 */
export function fundRank(q: string, sym: string, name: string): 0 | 1 | 2 | null {
  const s = q.trim().toUpperCase();
  if (!s) return null;
  if (sym === s) return 0;
  if (sym.startsWith(s)) return 1;
  if (s.length < 3) return null;
  return name.toUpperCase().split(/[^A-Z0-9]+/).some((w) => w.startsWith(s)) ? 2 : null;
}

/** How many rows the box shows. */
export const LIMIT = 12;
/** Places kept for the funds that are not the six core ones, when stocks would fill the box. */
const FUND_PLACES = 3;

/**
 * The rows for what was typed: the collector's stocks and the funds above, in one order.
 *
 * By how well each answers first (matchRank). Inside one rank: a core fund, then the
 * stocks in the collector's order (largest first), then the other funds. So "SP" leads
 * with SPY and "AR" with Arm, and "XL" still shows the sectors: when stocks alone would
 * fill the box, three places are kept for the other funds that matched.
 */
export function suggest(q: string, stocks: ReadonlyArray<StockHit>, limit: number = LIMIT): Suggestion[] {
  if (!q.trim()) return [];
  type Ranked = Suggestion & { rank: number; group: number; at: number };
  const rows: Ranked[] = [];
  const seen = new Set<string>();
  FUNDS.forEach((f, at) => {
    const rank = fundRank(q, f.sym, f.name);
    if (rank === null) return;
    seen.add(f.sym);
    rows.push({ sym: f.sym, name: f.name, cap: null, sector: null, kind: "fund", rank, group: f.core ? 0 : 2, at });
  });
  stocks.forEach((h, at) => {
    if (seen.has(h.sym)) return;
    seen.add(h.sym);
    // A stock the collector sent is a match by its rule; one this cannot rank sits last.
    const rank = matchRank(q, h.sym, h.name) ?? 3;
    rows.push({ sym: h.sym, name: h.name ?? "", cap: h.cap, sector: h.sector, kind: "stock", rank, group: 1, at });
  });
  rows.sort((a, b) => a.rank - b.rank || a.group - b.group || a.at - b.at);
  let kept = rows;
  if (rows.length > limit) {
    const others = rows.filter((r) => r.group === 2).length;
    const room = limit - Math.min(others, FUND_PLACES);
    let lead = 0;
    kept = rows.filter((r) => r.group === 2 || lead++ < room);
    kept = kept.slice(0, limit);
  }
  return kept.map(({ sym, name, cap, sector, kind }) => ({ sym, name, cap, sector, kind }));
}

/** A US ticker as it is written: one to five letters, and a share class after a dot or a dash ("BRK.B"). */
const US_TICKER = /^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$/;

/**
 * The ticker a "Check XYZ" row would ask about, or null when there is nothing to check.
 *
 * What was typed, when it is written like a US ticker, no row is that symbol already,
 * and it is not the start of a row's name. The last two keep the offer for the case it
 * is for, a real symbol the lists do not hold (a single-stock fund, a small company):
 * "coreweave" and "apple" are a company being typed, with the company on the row above,
 * and offering to check COREWEAVE as a ticker under it was noise.
 */
export function lookupFor(q: string, rows: ReadonlyArray<{ sym: string; name?: string | null }>): string | null {
  const s = q.trim().toUpperCase();
  if (!US_TICKER.test(s)) return null;
  if (rows.some((r) => r.sym === s)) return null;
  if (rows.some((r) => (r.name ?? "").toUpperCase().startsWith(s))) return null;
  return s;
}

export type Verdict =
  /** It trades: open it. */
  | { kind: "found" }
  /** Nothing trades under that symbol: say so, open nothing. */
  | { kind: "missing" }
  /** The question was not answered (the collector is down, Yahoo is refusing): open nothing, say why. */
  | { kind: "unknown"; why: string };

/**
 * What the collector's read of one name (/api/scanner/name/{sym}) says about whether it
 * exists. Only "Yahoo does not know this symbol" and "not a ticker" are a no: a read
 * that failed for any other reason has not answered the question, and a name is not
 * called missing because the collector was busy.
 */
export function lookupVerdict(d: { ok?: boolean; error?: string | null; offline?: { reason: string } | null } | null): Verdict {
  if (!d) return { kind: "unknown", why: "no answer" };
  if (d.offline) return { kind: "unknown", why: d.offline.reason };
  if (d.ok) return { kind: "found" };
  const why = (d.error ?? "").trim();
  if (/does not know this symbol|not a ticker/i.test(why)) return { kind: "missing" };
  return { kind: "unknown", why: why || "no data for this name" };
}
