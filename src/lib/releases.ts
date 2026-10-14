/**
 * One release, one row: the prints an agency publishes together, grouped.
 *
 * SEVEN ROWS FOR ONE NUMBER (owner review, 2026-10-14). The calendar lists each
 * series of a release on its own line, so the 08:30 US CPI arrived as Core CPI
 * m/m, Core CPI y/y, Core CPI Index, CPI y/y, CPI m/m, CPI Index n.s.a. and CPI
 * Index s.a. — seven rows in the Calendar, four in the Market tab's prints and
 * in the Game plan. Grouped, it is one row titled by its lead series with the
 * others beneath it.
 *
 * THIS IS server/newsterminal/releases.py IN THE BROWSER — the family rule, the
 * lead and the folded index levels are argued there, and the two are kept in
 * step by hand (the tests on both sides use the same names). In short:
 *
 * - Same country, same time, same FAMILY is one release. The family is the
 *   name with the series qualifiers taken off (core, m/m, y/y, index, the
 *   seasonal tags, initial / continuing / 4-week avg.) and a country's
 *   adjective dropped, plus a few aliases for releases whose series are named
 *   differently (the jobs report, PCE with income and spending, HICP with CPI).
 *   CPI and jobless claims sharing 08:30 stay two rows.
 * - The lead: highest impact score, a real series before an index level, the
 *   alias family's own headline (payrolls, initial claims), core before
 *   headline for CPI / PPI / PCE — the figure the rate market prices — and
 *   headline first elsewhere, then the monthly change before the annual.
 * - A price index's LEVEL and the unadjusted twins fold away: no one prices
 *   "CPI Index, n.s.a. 336.65". They stay on the group, out of the figures.
 */

export interface Release<T> {
  family: string;
  lead: T;
  /** The release's other series, ranked as the lead was. */
  subs: T[];
  /** Index levels and unadjusted twins — listed, never shown as figures. */
  levels: T[];
}

/** What grouping needs to know about a row, whatever panel it comes from. */
export interface ReleaseFields {
  event: string;
  /** The minute it prints; null never groups. */
  when: number | string | null;
  country: string | null;
  score: number;
  figures: ReadonlyArray<string | null | undefined>;
}

const ADJECTIVE =
  /^(?:german|french|spanish|italian|british|japanese|chinese|canadian|australian|swiss|u\.?s\.?|u\.?k\.?|euro ?zone|ez)\s+/i;
const QUALIFIER =
  /\b(?:core|headline|m\/m|y\/y|q\/q|mom|yoy|qoq|3m\/3m|3m\/y|index|change|monthly|initial|continuing|4-week avg\.?|4-week average|n\.?\s?s\.?\s?a\.?|nsa|s\.?\s?a\.?)(?=\s|$)/gi;

/** Releases that print several differently-named series at once. */
const ALIASES: Record<string, string> = {
  "nonfarm payrolls": "jobs",
  "private nonfarm payrolls": "jobs",
  "manufacturing payrolls": "jobs",
  "government payrolls": "jobs",
  "unemployment rate": "jobs",
  "u6 unemployment rate": "jobs",
  "average hourly earnings": "jobs",
  "average weekly hours": "jobs",
  "participation rate": "jobs",
  employment: "jobs",
  "full employment": "jobs",
  "claimant count": "jobs",
  "average earnings": "jobs",
  "jobless claims": "claims",
  "retail control": "retail sales",
  "retail sales ex gas/autos": "retail sales",
  hicp: "cpi",
  "cpi ex tobacco": "cpi",
  "ppi ex. food/energy/transport": "ppi",
  "pce price": "pce",
  "pce prices": "pce",
  "personal income": "pce",
  "personal spending": "pce",
};

const FAMILY_LEAD: Record<string, RegExp> = {
  jobs: /nonfarm payrolls|employment change/i,
  claims: /\binitial\b/i,
};

const INFLATION = new Set(["cpi", "ppi", "pce", "hicp"]);

/** The name with its qualifiers off, before any alias — "Core CPI y/y" → "cpi". */
function base(event: string): string {
  let s = (event || "").replace(/[,()]/g, " ").trim();
  s = s.replace(ADJECTIVE, "");
  s = s.replace(QUALIFIER, " ");
  return s.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

/** The release an event name belongs to. "Initial Jobless Claims" → "claims". */
export function family(event: string): string {
  const b = base(event);
  return ALIASES[b] ?? b;
}

/**
 * A price index's level or an unadjusted twin. Only a PRICE index, and only
 * when its figures are not percentages: "PCE Price Index m/m 0.3%" is a change;
 * an Empire State index reading is the traded number.
 */
export function isLevel(event: string, figures: ReadonlyArray<string | null | undefined>): boolean {
  const name = event || "";
  if (/\bn\.?\s?s\.?\s?a\b|\bnsa\b|,\s*s\.?\s?a\b/i.test(name)) return true;
  if (!(/\bindex\b/i.test(name) && /\b(?:CPI|PPI|PCE|HICP|RPI|price)\b/i.test(name))) return false;
  return !figures.some((f) => !!f && f.includes("%"));
}

function leadKey(event: string, score: number, fam: string, level: boolean): number[] {
  const want = FAMILY_LEAD[fam];
  const core = /\bcore\b/i.test(event);
  return [
    -score,
    level ? 1 : 0,
    !want || want.test(event) ? 0 : 1,
    INFLATION.has(fam) ? (core ? 0 : 1) : core ? 1 : 0,
    /\b(?:m\/m|q\/q|mom|qoq)\b/i.test(event) ? 0 : /\b(?:y\/y|yoy)\b/i.test(event) ? 1 : 2,
  ];
}

function cmp(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

/** Group rows into releases, in the order each release first appears. */
export function groupReleases<T>(rows: readonly T[], fields: (r: T) => ReleaseFields): Release<T>[] {
  const buckets = new Map<string, { i: number; r: T; f: ReleaseFields }[]>();
  rows.forEach((r, i) => {
    const f = fields(r);
    const k = f.when == null ? `solo:${i}` : `${f.country ?? ""}|${f.when}|${family(f.event)}`;
    const b = buckets.get(k);
    if (b) b.push({ i, r, f });
    else buckets.set(k, [{ i, r, f }]);
  });
  const out: Release<T>[] = [];
  for (const members of buckets.values()) {
    const fam = family(members[0].f.event);
    const ranked = members
      .map((m) => ({ ...m, level: isLevel(m.f.event, m.f.figures) }))
      .sort((a, b) => cmp(leadKey(a.f.event, a.f.score, fam, a.level), leadKey(b.f.event, b.f.score, fam, b.level)) || a.i - b.i);
    // The lead's own name first: "Core y/y · m/m · y/y" under Core PPI m/m, then
    // the ex-food series — interleaved, a bare "y/y" read as the ex-food one.
    const own = base(ranked[0].f.event);
    const rest = ranked.slice(1).sort((a, b) => Number(base(a.f.event) !== own) - Number(base(b.f.event) !== own));
    out.push({
      family: fam,
      lead: ranked[0].r,
      subs: rest.filter((m) => !m.level).map((m) => m.r),
      levels: rest.filter((m) => m.level).map((m) => m.r),
    });
  }
  return out;
}

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

/**
 * A sub-series' name beside its lead: "CPI y/y" under "Core CPI m/m" is "y/y",
 * "Continuing Jobless Claims" under initial claims is "Continuing". A series
 * with a different name from the lead's keeps it ("Average Hourly Earnings
 * m/m" under payrolls; "HICP m/m" under CPI), less a country's adjective.
 */
export function subLabel(event: string, leadEvent: string): string {
  const name = (event || "").replace(ADJECTIVE, "").trim();
  const b = base(event);
  if (!b || b !== base(leadEvent)) return name;
  const words = b.split(" ").map(escape).join("[\\s,]+");
  const left = name
    .replace(new RegExp(`\\b${words}\\b`, "i"), " ")
    .replace(/\s+/g, " ")
    .trim();
  // Under a CORE lead a bare "m/m" read as core's own month — it is the
  // headline's. Said so: "Headline m/m" (2026-10-14, the first CPI morning).
  const core = /\bcore\b/i;
  if (left && core.test(leadEvent) && !core.test(name)) return `Headline ${left}`;
  return left || name;
}
