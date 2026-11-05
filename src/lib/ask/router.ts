/**
 * The router in front of Hermes: how much thinking a question needs before any
 * model is called (owner, 2026-10-30: "is there ways to handle it so the model
 * uses less when it doesn't need to?").
 *
 * THE ROUTER SPENDS THINKING, NEVER REACH (owner, 2026-11-05: "Hermes AI should
 * have the context of every thing shown and displayed in the app"). It used to
 * decide from the question's words whether the tools came along at all, and which
 * desk's. "Who reports today?" matched no word in the list, so it went out with no
 * tools and a prompt that said to tell the reader to ask again; Hermes said it did
 * not have the day's earnings, and answered once challenged, because a follow-up
 * always got the tools. Any word list misses something, so a miss now costs only a
 * little depth. Two decisions are made here, deterministically:
 *
 *   tier   "quick" — no thinking and a shorter answer, for a check. "full" — a
 *          name, a level, a why, a comparison: the thinking budget. Both have
 *          every tool, and a question the glance cannot answer takes one more
 *          round rather than a wrong "I don't have that".
 *   local  a handful of questions never reach a model at all, because the
 *          answer is a field in the glance: the phase, whether a box is
 *          open, a strip quote. Those patterns are anchored and narrow on
 *          purpose — a near miss falls through to the model, which is the
 *          safe failure.
 *
 * Pure, and kept free of imports so `node --experimental-strip-types --test`
 * runs its tests without a bundler (router.test.ts).
 */

export type Tier = "quick" | "full";

export interface Route {
  tier: Tier;
  /** One phrase for the log: what decided it. */
  why: string;
}

/** A word that wants thinking, not just a read of the desk. */
const FULL_WORDS = /\b(why|what moved|lean|leaning|overall|macro|structure|net|summar(y|ise|ize)|conviction|sentiment|outlook|picture|view|take|thoughts|agree|confirm|what('s| is) (moving|driving|behind)|compare|versus|vs\.?|setup|set-up|plan|trade|levels?|retest|break|breakout|should i|worth|short|long|bias|read|brief|game plan|earnings|calendar|scheduled|headlines?|news|wire|chart|bars|gamma|vwap|ladder|which|best|cleanest|review|run-?down|explain|walk me|think|risk|catalyst|print(ed|s)?|report(ed|s|ing)?|beat|beats|miss|missed|misses|flow|skew|expected move|wall|flip|profile|poc|value area|rotation|breadth|fuel|rates?|yield|dollar|dxy|oil|crude|vix curve|term structure)\b/i;
/** A question longer than this is a run-down whatever its words. */
const QUICK_MAX_WORDS = 18;

const words = (q: string) => q.trim().split(/\s+/).filter(Boolean).length;

/** Watchlist tickers the question names, as typed in caps or with a $ — "amd" in prose is a word, "AMD" is a name. */
function tickersIn(q: string, watchlist: string[]): string[] {
  const have = new Set(watchlist.map((s) => s.toUpperCase()));
  const out: string[] = [];
  for (const m of q.matchAll(/\$?([A-Za-z][A-Za-z.\-]{0,5})\b/g)) {
    const raw = m[1];
    const sym = raw.toUpperCase();
    const typedAsName = m[0].startsWith("$") || raw === sym;
    if (typedAsName && have.has(sym) && !out.includes(sym)) out.push(sym);
  }
  return out;
}

export function routeQuestion(question: string, opts: { watchlist: string[]; followUp?: boolean }): Route {
  const q = question.trim();
  const named = tickersIn(q, opts.watchlist);
  // A FOLLOW-UP IS NEVER A GLANCE (owner, 2026-10-30: a "so overall?" turn was
  // answered from the earlier turns' figures, every one of them stale by then).
  // In an ongoing chat a short question leans on what came before, and what
  // came before has to be re-read.
  if (opts.followUp) return { tier: "full", why: "a follow-up" };
  if (named.length) return { tier: "full", why: `names ${named.join(", ")}` };
  if (FULL_WORDS.test(q)) return { tier: "full", why: `asks ${FULL_WORDS.exec(q)?.[0]}` };
  if (words(q) > QUICK_MAX_WORDS) return { tier: "full", why: "long question" };
  return { tier: "quick", why: "a check" };
}

/** What the glance holds that a local answer reads (ask.slim_context). */
export interface GlanceLike {
  as_of_et?: unknown;
  phase?: unknown;
  boxes_open?: unknown;
  strip?: unknown;
}

const STRIP_NAMES: Record<string, string> = {
  nq: "NQ", es: "ES", gc: "GC", gold: "GC", spy: "SPY", qqq: "QQQ", iwm: "IWM", vix: "VIX", vxn: "VXN",
  us10y: "US10Y", "10y": "US10Y", "10 year": "US10Y", "10-year": "US10Y", "10year": "US10Y",
  dxy: "DXY", "dollar index": "DXY", wti: "WTI", crude: "WTI", oil: "WTI", btc: "BTC", bitcoin: "BTC",
};

const PHASE_Q = /^(what|which) (session|phase)( is it| are we in| is this| now)?\s*\??$|^where are we in the (day|session)\s*\??$|^what time is it( in et| et| in new york)?\s*\??$/i;
const OPEN_Q = /^is (asia|london|new york|ny|the pre-?market|pre-?market|frankfurt|the ny session|the cash session)( box)? open( now| yet)?\s*\??$/i;
const QUOTE_Q = /^(what'?s|what is|where'?s|where is|how'?s|how is|price of|quote) (the )?([a-z0-9 &\-]+?)( (trading|at|now|doing|today|tonight|right now))*\s*\??$/i;

function fmt(n: unknown): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n >= 1000 ? n.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(Math.round(n * 100) / 100);
}

function clockLine(g: GlanceLike): string {
  const et = typeof g.as_of_et === "string" ? g.as_of_et : "";
  const m = /T(\d{2}:\d{2})/.exec(et);
  return m ? `${m[1]} ET` : "now";
}

/**
 * An answer without a model, or null. Only for questions the glance answers
 * whole: the phase, a box, a strip quote. The text names its source and the
 * time, so it reads as a read of the data rather than a reply.
 */
export function localAnswer(question: string, g: GlanceLike): string | null {
  const q = question.trim();
  const phase = typeof g.phase === "string" ? g.phase : null;
  const open = Array.isArray(g.boxes_open) ? (g.boxes_open as unknown[]).filter((b): b is string => typeof b === "string") : [];
  if (PHASE_Q.test(q)) {
    if (!phase) return null;
    const boxes = open.length ? ` Open boxes: ${open.join(", ")}.` : " No session box is open.";
    return `${phase}, at ${clockLine(g)}.${boxes}`;
  }
  const o = OPEN_Q.exec(q);
  if (o) {
    const want = o[1].toLowerCase().replace(/^the /, "").replace(/-/, "");
    const key = want.startsWith("pre") ? "pre-market" : want === "ny" || want.startsWith("new york") || want.includes("cash") ? "new york" : want;
    if (key === "frankfurt") return phase ? `${phase === "Frankfurt session" ? "Yes" : "No"}, it is ${phase.toLowerCase()} at ${clockLine(g)}.` : null;
    const is = open.some((b) => b.toLowerCase() === key);
    return `${is ? "Yes" : "No"}. ${phase ?? "The phase is unknown"}, at ${clockLine(g)}${open.length ? `; open: ${open.join(", ")}` : "; no box is open"}.`;
  }
  const m = QUOTE_Q.exec(q);
  if (m) {
    const name = m[3].toLowerCase().trim();
    const key = STRIP_NAMES[name];
    if (!key || !Array.isArray(g.strip)) return null;
    const row = (g.strip as { key?: unknown; last?: unknown; pct?: unknown; feed?: unknown }[]).find((r) => r.key === key);
    if (!row || typeof row.last !== "number") return null;
    const pct = typeof row.pct === "number" ? ` (${row.pct >= 0 ? "+" : ""}${(Math.round(row.pct * 100) / 100).toFixed(2)}%)` : "";
    const feed = typeof row.feed === "string" && row.feed !== "live" ? `, ${row.feed} feed` : "";
    return `${key} ${fmt(row.last)}${pct} at ${clockLine(g)}${feed}.`;
  }
  return null;
}
