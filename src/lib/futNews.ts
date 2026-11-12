/**
 * Which futures book a wire story reaches, by what the headline is about (owner,
 * 2026-11-10: "instead of Levels section maybe have a news feed with important
 * things that affect that, eg if nq then things that have high impact on nq").
 *
 * A RULE A DESK WOULD SAY OUT LOUD, not a measurement, read like `booksOf` for the
 * calendar: the Fed, US data and yields reach the indices and the metals; the dollar
 * the metals and crude; tariffs and the fiscal fights the indices and gold; the
 * megacaps, AI and chips the Nasdaq; Wall Street the S&P; gold and silver their own;
 * oil, OPEC, the Gulf and tankers crude; a war or an attack gold and crude.
 *
 * ANOTHER COUNTRY'S CENTRAL BANK OR DATA REACHES NONE OF THEM. Read against the
 * live wire the morning it was built, the rule put the ECB, four Bank of England
 * stories, Hungary's inflation, Norway's and the China fix under no book, and
 * "Fed Hike Odds Hit 84%" under four. A US word (US, the Fed, Treasuries, Trump,
 * Congress) is what makes an inflation, jobs or yields headline American.
 */

import type { WireItem } from "@/types/terminal";
import type { FutBook } from "./futures";

// FUT_BOOKS' order, written out: the test runner strips types but resolves no
// extensionless sibling import, and the page's tsconfig allows no `.ts` one.
const BOOKS: readonly FutBook[] = ["NQ", "ES", "GC", "SIL", "CL"];

export interface StoryRead {
  /** The books the story reaches, in FUT_BOOKS order. */
  books: FutBook[];
  /** Why, as the card prints them: "Fed", "Oil", "Middle East". */
  tags: string[];
}

export interface BookStory extends StoryRead {
  item: WireItem;
}

const US_CAPS = /\bU\.?S\.?\b|\bUS-/;
const US_WORDS = /\bamerica\w*|\bfed\b|fomc|powell|federal reserve|treasur\w*|wall street|white house|trump|congress|senate|washington|nonfarm|payrolls/i;
const FOREIGN =
  /\becb\b|\bboe\b|bank of england|\bboj\b|bank of japan|\bpboc\b|\brba\b|\bsnb\b|norges|riksbank|\bboc\b|\brbnz\b|banxico|lagarde|bailey|\bueda\b|hungary|norway|sweden|india|turkey|brazil|mexico|canada|australia|japan|china|\buk\b|britain|eurozone|euro area|\beu\b/i;

interface Theme {
  tag: string;
  re: RegExp;
  books: readonly FutBook[];
  /** A theme that is American only with a US word, or with no foreign one. */
  us?: boolean;
}

const RATES: readonly FutBook[] = ["NQ", "ES", "GC", "SIL"];
const THEMES: readonly Theme[] = [
  { tag: "Fed", re: /\bfed\b|fomc|powell|federal reserve|rate (?:hike|cut)s?\b|hike odds|cut odds|fed funds/i, books: RATES, us: true },
  {
    tag: "US data",
    re: /\bcpi\b|\bppi\b|\bpce\b|inflation|payrolls|jobs report|jobless|unemployment|retail sales|\bgdp\b|\bism\b|consumer (?:sentiment|confidence)|nonfarm/i,
    books: RATES,
    us: true,
  },
  { tag: "Yields", re: /treasur\w*|\byields?\b|bond (?:sell-?off|rout|rally)|10-year|2-year|30-year/i, books: RATES, us: true },
  { tag: "Dollar", re: /\bdollar\b|greenback|\bdxy\b/i, books: ["GC", "SIL", "CL"] },
  { tag: "Tariffs", re: /tariffs?|trade war|trade deal|trade talks|export (?:curb|control|ban)s?/i, books: ["NQ", "ES", "GC"] },
  { tag: "Fiscal", re: /shutdown|debt ceiling|stimulus|budget deal|spending bill/i, books: ["NQ", "ES", "GC"], us: true },
  { tag: "Megacaps", re: /nvidia|\bapple\b|microsoft|amazon|\bmeta\b|alphabet|google|tesla|broadcom|netflix|\bamd\b/i, books: ["NQ", "ES"] },
  { tag: "Tech", re: /\bai\b|\bchips?\b|chipmaker|semiconductor|nasdaq|tech (?:stocks|sell-?off|rally|rebound|surge|slide)/i, books: ["NQ"] },
  { tag: "Stocks", re: /s&p|wall street|stock market|\bstocks\b|dow jones|\bdow\b|equities|\bmarkets wrap\b/i, books: ["NQ", "ES"] },
  { tag: "Gold", re: /\bgold\b|bullion|precious metals?/i, books: ["GC", "SIL"] },
  { tag: "Silver", re: /\bsilver\b/i, books: ["SIL"] },
  {
    tag: "Oil",
    re: /\boil\b|crude|opec|brent|\bwti\b|barrels?|refiner\w*|gasoline|pipeline|tankers?|hormuz|\blng\b|natural gas|oil sanctions|sanctions on (?:russia|iran)/i,
    books: ["CL"],
  },
  { tag: "Middle East", re: /\biran\b|israel|houthi|saudi|hormuz|\bgulf\b|\biraq\b|lebanon|hezbollah|hamas|\bgaza\b|yemen/i, books: ["GC", "CL"] },
  { tag: "Russia", re: /russia|ukraine|kremlin|putin|moscow/i, books: ["GC", "CL"] },
  { tag: "War", re: /\battacks?\b|missiles?|\bwar\b|strikes? on|ceasefire|\bdrones?\b|airstrike/i, books: ["GC", "CL"] },
];

/** The books a headline reaches and why. Pure. */
export function storyRead(title: string): StoryRead {
  const t = title ?? "";
  const american = US_CAPS.test(t) || US_WORDS.test(t);
  const foreign = FOREIGN.test(t);
  const hit = new Set<FutBook>();
  const tags: string[] = [];
  for (const th of THEMES) {
    if (!th.re.test(t)) continue;
    if (th.us && !american && foreign) continue;
    if (th.us && th.tag !== "Fed" && !american) continue;
    for (const b of th.books) hit.add(b);
    tags.push(th.tag);
  }
  return { books: BOOKS.filter((b) => hit.has(b)), tags };
}

/**
 * The wire's high and medium stories that reach `book`, or any book when none is
 * given, newest first, each with its read. Pure.
 */
export function bookStories(wire: readonly WireItem[], book?: FutBook, limit = 14): BookStory[] {
  const out: BookStory[] = [];
  const sorted = [...wire].filter((w) => w.impact === "high" || w.impact === "medium").sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
  for (const item of sorted) {
    if (out.length >= limit) break;
    const read = storyRead(item.title);
    if (read.books.length === 0 || (book && !read.books.includes(book))) continue;
    out.push({ item, ...read });
  }
  return out;
}
