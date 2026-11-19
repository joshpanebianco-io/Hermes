"use client";

import { memo, useCallback, useEffect, useMemo, useState } from "react";
import type { BriefLadder, CalendarRow, DayLabel, DayType, DayTypeBook, GexAsset, ImpliedBook, Quote, Terminal as TerminalData, WireItem } from "@/types/terminal";
import { Gamma } from "@/components/panels/Gamma";
import { SessionRanges } from "@/components/panels/SessionRanges";
import { VolumeProfile } from "@/components/panels/VolumeProfile";
import { ScanChart } from "@/components/panels/ScanChart";
import { Arrow, BiasStat, StatCard } from "@/components/panels/ScanWide";
import { BiasOpener } from "@/components/vol/DriverBoard";
import { MarketReportView } from "@/components/MarketReport";
import type { ReportController } from "@/lib/useReport";
import { biasOut, closeBias, openBias } from "@/lib/biasDrawer";
import { AssetIcon } from "@/components/ui/AssetIcon";
import { PageLoader } from "@/components/ui/HelmLoader";
import { useSide } from "@/components/state/UiMode";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { liveLine } from "@/lib/bias";
import { wholeScore } from "@/lib/biasScale";
import { cn } from "@/lib/cn";
import { ageStep, dir, inMin, num, pct } from "@/lib/format";
import { CALL_HUE, labelWords, leanLine, leanTitle, nightWords, voteWord } from "@/lib/daytype";
import { countryShort, levelsFrom, type ChartLevels } from "@/lib/futCards";
import { bookStories } from "@/lib/futNews";
import { regimeMeans } from "@/lib/gammaRegime";
import { DAY_TYPED, FUT_NAME, FUT_VIEWS, QUOTE_KEY, SCORED, nextRelease, type FutBook, type FutView } from "@/lib/futures";
import { etDay } from "@/lib/nextPrint";
import { dayState } from "@/lib/outsideDay";
import { groupReleases } from "@/lib/releases";
import { segItem } from "@/lib/seg";
import { useNow } from "@/lib/useNow";

/**
 * Futures — everything about the futures traded, on one page (owner, 2026-11-10:
 * "a seperate futures section that has all info related to futures that we trade
 * - nq, es, gc, sil, cl1").
 *
 * IT REPLACES STRUCTURE'S FUTURES HALF, in Structure's place on the bar, so the
 * header's room is unchanged; the stocks half was the Scanner's
 * Index view until that went on 2026-11-13 (lib/tabs.ts). The page is built the way the Scanner is: a row of views, a row of
 * figures, one framed body.
 *
 *   NQ … CL    one contract: its figures, its chart with the levels drawn, the news
 *              that reaches it, the session ranges, the profile and gamma, all on
 *              that book
 *
 * NO BRIEF VIEW SINCE 2026-11-15 (owner: "i want to remove the market section from stocks
 * and brief section from futures and consolidate it all into one area"): the written
 * report is the Market Report page's, with silver and crude written as well as scored.
 * That page is off the navigation since 2026-11-16 (lib/tabs OFF_NAV; owner: "just utilise
 * the pop up cards when you click on the bias in each assets section"), so a contract's
 * read on a page is its Bias card here and the driver board the card slides out from the
 * right (vol/BiasDrawer, the same afternoon: "comes from the right similar to when you
 * click on a stock").
 *
 * ONE BOOK A VIEW. The panels used to pick their own book each, so the ladder could
 * be on NQ beside gamma on ES; in a book's view all of them are that book.
 *
 * THERE IS NO OVERVIEW (owner, 2026-11-14: "do you think the overview tab is necessary
 * in futures?", then "lets remove it completely"). It was the first view: the five side
 * by side, each a cut-down copy of its own view's figures row, over the calendar and the
 * news again, and a click between the page and the chart it was opened for. With it went
 * the only place the Session type card, the vol curve (panels/Volatility), "The book"
 * board and the Sessions panel were drawn; the data behind each is still served, and
 * Hermes still reads it. The page opens on NQ.
 *
 * SILVER AND CRUDE ARE SCORED SINCE 2026-11-15 (owner: "implement the silver and oil
 * bias calculation and weightings and rules too"; server bias.py says what each answers
 * to). Their Bias card is the same card the other three have. The trend-or-range record
 * is still NQ, ES and gold only, and their Session type card says so.
 */

const SOURCES = ["quotes", "ranges", "profiles", "gex"];
const NONE: never[] = [];
// Shrinkable only side by side: stacked, a column that shrinks spills into the next one.
const COL = "qt-col flex min-w-0 flex-col gap-2 xl:min-h-0 xl:overflow-y-auto";

const MRanges = memo(SessionRanges);
const MProfile = memo(VolumeProfile);
const MGamma = memo(Gamma);

export function FuturesBoard({
  data,
  view,
  onView,
  report,
}: {
  data: TerminalData;
  view: FutView;
  onView: (v: FutView) => void;
  /** The written report's state, the Terminal's, so a report being written survives a change of page. */
  report: ReportController;
}) {
  const st = data.status ?? {};
  const ready = Boolean(data.offline) || SOURCES.every((k) => st[k] !== undefined);
  // The Sidebar interface lists the views itself and says the session in its header.
  const side = useSide();
  // A contract's bias slid out (vol/BiasDrawer) would sit over the report: the report puts it away.
  useEffect(() => {
    if (view === "report") closeBias();
  }, [view]);
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {!side && <Masthead view={view} onView={onView} phase={data.clock?.phase.label ?? null} />}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
        {view === "report" ? (
          // The written report (MarketReportView), after CL since 2026-11-16: it reads the
          // collector's report store, not the desk's sources, so it does not wait on them.
          <MarketReportView data={data} report={report} desk="futures" />
        ) : !ready ? (
          <PageLoader label="Loading the desk" size={64} />
        ) : (
          <BookView key={view} book={view} data={data} />
        )}
      </div>
    </main>
  );
}

/* -------------------------------------------------------------------------- */

function Masthead({ view, onView, phase }: { view: FutView; onView: (v: FutView) => void; phase: string | null }) {
  return (
    <div className="qt-mast flex min-h-[44px] shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 qt:px-4">
      {/* `seg-tabs`: the same tabs as the Stocks tab's views (globals.css). */}
      <span className="seg seg-tabs shrink-0" role="tablist" aria-label="Futures views">
        {FUT_VIEWS.map((v) => (
          <button key={v.key} type="button" role="tab" aria-selected={view === v.key} title={v.title} onClick={() => onView(v.key)} {...segItem(view === v.key)}>
            <AssetIcon id={v.key} size={13} className="block shrink-0" />
            {v.label}
          </button>
        ))}
      </span>
      {/* No company search here (owner, 2026-11-11: "remove the company search fromt he
          futures section"): it finds stocks, and this tab is the futures books. Ctrl+K
          still opens it from any tab; the box is on the Scanner and Sectors bands. */}
      <div className="ml-auto flex shrink-0 items-center gap-3">
        {phase && (
          <span className="fig text-[11px] whitespace-nowrap text-ink-3">
            <span aria-hidden className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full bg-desk-policy align-middle" />
            {phase}
          </span>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* What each card and figure reads                                             */
/* -------------------------------------------------------------------------- */

interface Read {
  q: Quote | null;
  last: number | null;
  dp: number;
  ladder: BriefLadder | null;
  gex: GexAsset | null;
  flip: number | null;
  implied: ImpliedBook | null;
}

function read(data: TerminalData, book: FutBook): Read {
  const q = (data.quotes ?? NONE).find((x: Quote) => x.key === QUOTE_KEY[book]) ?? null;
  const ladder = data.ladders?.[book] ?? null;
  const g = data.gex?.assets?.[book] ?? null;
  const gex = g?.ok ? g : null;
  const implied = data.volterm?.books?.find((x) => x.key === book) ?? null;
  const last = q?.last ?? ladder?.last ?? null;
  const dp = ladder?.dp ?? implied?.dp ?? 2;
  return {
    q,
    last,
    dp,
    ladder,
    gex,
    flip: gex?.levels.find((l) => l.key === "flip")?.price ?? null,
    implied,
  };
}

function gammaWord(r: Read): { word: string; hue: string; line: string } {
  if (!r.gex) return { word: "—", hue: "text-ink-3", line: "No gamma levels from GEXYGEN right now" };
  const pos = r.gex.regime === "POS";
  const line =
    r.flip != null && r.last != null
      ? `${num(Math.abs(r.last - r.flip), r.dp)} ${r.last >= r.flip ? "above" : "below"} the flip ${num(r.flip, r.dp)}`
      : "flip not drawn";
  // In ink, never green or pink: the regime is not a side (lib/gammaRegime).
  return { word: pos ? "Positive γ" : "Negative γ", hue: "text-ink", line: `${regimeMeans(r.gex.regime)} · ${line}` };
}

/**
 * When a release is, as the card's figure: a countdown inside a day ("in 5h 30m"), the
 * day and the hour past that ("Mon 12:00", New York's), where the countdown would only
 * say "in 1d" for anything from 24 hours to 48.
 */
function whenWord(r: CalendarRow, now: number | null): { value: string; soon: boolean } {
  if (now == null || r.ts == null) return { value: "—", soon: false };
  const min = (r.ts - now / 1000) / 60;
  if (min < 24 * 60 || !r.et) return { value: `in ${inMin(min)}`, soon: true };
  return { value: `${etDay(r.ts, now)}${r.et}`, soon: false };
}

/* ---- the two cards that were swapped in on 2026-11-15 (lib/futCards has the why) ---- */

const sameLevels = (a: ChartLevels | null, b: ChartLevels | null) =>
  a === b || (a != null && b != null && a.pdh === b.pdh && a.pdl === b.pdl && a.pmh === b.pmh && a.pml === b.pml && a.pm_done === b.pm_done);

/** "Trend day up", "Range day": what New York was, once it has closed. */
const dayKind = (l: DayLabel) => (l.type === "trend" ? `Trend day${l.dir ? ` ${l.dir}` : ""}` : `${l.type[0].toUpperCase()}${l.type.slice(1)} day`);

/**
 * Session type: will New York trend or range (daytype.py), the call with the count that
 * carries it; after the close, what the day was. Its click opens every condition that
 * holds today with its count over the record, as the Overview's card did until that
 * view went on 2026-11-14 and took the read off every page. Counts, never percentages,
 * and never a side: the call is in ink.
 */
function sessionCard(st: DayTypeBook | null) {
  if (!st) return null;
  const { lean, label } = st;
  if (label) {
    const rest = labelWords(label).split(" · ").slice(1).join(" · ");
    return { value: dayKind(label), hue: "text-ink", label: "Session type · today was", sub: rest || nightWords(lean), title: `Today: ${labelWords(label)}\n${leanTitle(lean)}` };
  }
  // A call prints the count that carries it; no lean prints what it has to go on.
  return { value: lean.word, hue: CALL_HUE[lean.call], label: "Session type", sub: leanLine(lean), title: `${nightWords(lean)}\n${leanTitle(lean)}` };
}

/** Every condition that holds today, with its count over the record, and the base rate. */
function SessionPanel({ book, st, rec }: { book: FutBook; st: DayTypeBook; rec: DayType["record"][string] | undefined }) {
  const { lean, label } = st;
  return (
    <div className="w-[min(520px,calc(100vw-24px))] px-4 py-3 text-ink">
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">Session type</span>
        <span className="fig text-[16px] leading-none">{book}</span>
        <span className={cn("text-[13px] font-semibold", CALL_HUE[lean.call])}>{label ? `Today: ${labelWords(label)}` : lean.word}</span>
      </p>
      <p className="fig mt-1.5 text-[11px] text-ink-3">{nightWords(lean)}</p>
      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">{lean.why}</p>
      <ul className="mt-2.5 space-y-1 border-t border-ring/40 pt-2 text-[11.5px]">
        {lean.holds.map((h) => (
          <li key={h.condition} className="flex items-baseline gap-2">
            <span className={cn("min-w-0 flex-1", h.vote ? "text-ink" : "text-ink-2")}>
              {h.condition}
              {h.shown && <span className="fig text-ink-3"> · {h.shown}</span>}
            </span>
            <span className="fig shrink-0 text-ink-2">
              {h.trend} trend in {h.n} · {h.range} range
            </span>
            <span className="qt-cap w-[80px] shrink-0 text-right text-[9.5px] text-ink-3">{voteWord(h.vote)}</span>
          </li>
        ))}
        {lean.holds.length === 0 && <li className="text-ink-3">No condition in the record holds today.</li>}
      </ul>
      <p className="fig mt-2 border-t border-ring/40 pt-2 text-[10.5px] leading-[1.45] text-ink-3">
        every session: {lean.base.trend} trend days in {lean.base.n}, {lean.base.range} range
        {rec ? ` · ${rec.backfill} from the backfill, ${rec.live} live` : ""}
      </p>
      <p className="mt-1 text-[11px] leading-[1.45] text-ink-3">
        A condition votes only with fifty sessions behind it and a rate well off every session&apos;s; a trend rate under half of
        every session&apos;s votes against a trend call, and the two together read Mixed record. Counts over the record, not
        probabilities.
      </p>
    </div>
  );
}

/**
 * Levels: the day's state against the chart's four, in the Stocks chips' words
 * (lib/outsideDay dayState), and under it the levels that make it so. An outside day and
 * a break through the previous day's level wear the way they went, green up and pink
 * down: that is the contract's own move. Inside is ink.
 */
function levelsCard(lv: ChartLevels | null, last: number | null, day: { high: number | null; low: number | null } | null, dp: number) {
  const st = dayState(last, lv, day);
  if (!st || !lv || lv.pdh == null || lv.pdl == null) return { value: "—", hue: "text-ink-3", sub: "No levels on the chart yet", title: "The chart's PDH, PDL, PMH and PML, once the day has them" };
  const p = (v: number) => num(v, dp);
  const span = `between PDL ${p(lv.pdl)} and PDH ${p(lv.pdh)}`;
  let value: React.ReactNode;
  let hue = "text-ink";
  let sub: string;
  if (st.kind === "outside" || st.kind === "through") {
    const up = st.dir === "up";
    hue = up ? "text-call-fig" : "text-put-fig";
    const day1 = up ? `above PDH ${p(lv.pdh)}` : `below PDL ${p(lv.pdl)}`;
    const pm = up ? lv.pmh : lv.pml;
    if (st.kind === "outside") {
      value = (
        <>
          Outside Day <Arrow up={up} />
        </>
      );
      // Before 09:30 the previous day's level alone decides (lib/outsideDay).
      sub = !lv.pm_done ? `${day1} · pre-market still forming` : pm != null ? `${day1} and ${up ? "PMH" : "PML"} ${p(pm)}` : day1;
    } else {
      value = (
        <>
          {up ? "Through PDH" : "Through PDL"} <Arrow up={up} />
        </>
      );
      sub = pm != null ? `${day1} · ${up ? "under PMH" : "over PML"} ${p(pm)}` : `${day1} · no pre-market range`;
    }
  } else if (st.kind === "inside") {
    value = "Inside Day";
    sub = span;
  } else if (st.kind === "back") {
    value = "Back Inside";
    sub = st.over && st.under ? `${span} · traded through both` : st.over ? `under PDH ${p(lv.pdh)} · traded above it earlier` : `over PDL ${p(lv.pdl)} · traded below it earlier`;
  } else {
    value = "Inside the range";
    sub = span;
  }
  const title = [
    ...levelsFrom(lv, last).map((l) => `${l.key} ${p(l.price)}  ${l.dist >= 0 ? "+" : "−"}${p(Math.abs(l.dist))}`),
    `The chart's own levels, measured from the last print${last != null ? ` ${p(last)}` : ""}.`,
    "Outside Day: above both the previous day's high and the pre-market high, or below both lows. Through: beyond the previous day's level alone. Inside Day: the whole day so far inside the previous day's range. Back Inside: between them again after trading beyond one.",
  ].join("\n");
  return { value, hue, sub, title };
}

/**
 * The wire's stories that reach a book (lib/futNews): the Fed, US data and yields for
 * the indices and the metals, oil and the Gulf for crude, nothing from another
 * country's central bank. It stands where the ladder stood (owner, 2026-11-10:
 * "instead of Levels section maybe have a news feed with important things that affect
 * that, eg if nq then things that have high impact on nq"); the ladder's rows are drawn
 * on the chart, and Hermes still reads the ladder itself. Two lines a story: the
 * headline, then why it is here, who filed it and how long ago.
 */
function FuturesNews({ wire, now, book }: { wire: WireItem[]; now: number | null; book: FutBook }) {
  const rows = useMemo(() => bookStories(wire, book), [wire, book]);
  return (
    <Module title={`${book} news`} sub={`what reaches ${FUT_NAME[book]} · high and medium`} bodyClassName="px-0 py-0">
      {rows.length === 0 ? (
        <p className="px-3 py-4 text-[12px] text-ink-3">{`No high or medium story reaches ${FUT_NAME[book]} right now.`}</p>
      ) : (
        <ul className="py-1">
          {rows.map(({ item: w, tags }) => (
            <li key={w.url}>
              <a href={w.url} target="_blank" rel="noreferrer noopener" className="hit flex flex-col gap-[3px] px-3 py-[6px]" title={w.summary || w.title}>
                <span className="flex items-start gap-2">
                  <span aria-hidden className={cn("mt-[5px] h-[6px] w-[6px] shrink-0 rounded-[1px]", w.impact === "high" ? "bg-put-fig" : "bg-flip-fig")} />
                  <span className="line-clamp-2 min-w-0 flex-1 text-[12px] leading-[1.3] text-ink">{w.title}</span>
                </span>
                <span className="flex items-center gap-2 pl-[14px]">
                  <span className="qt-cap min-w-0 truncate text-[9.5px] text-ink-3">{tags.join(" · ")}</span>
                  <span className="fig ml-auto shrink-0 text-[10.5px] text-ink-3">
                    {w.publisher} · {now != null && w.ts != null ? inMin((now / 1000 - w.ts) / 60) : "—"}
                  </span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </Module>
  );
}

/* -------------------------------------------------------------------------- */
/* One book                                                                    */
/* -------------------------------------------------------------------------- */

function BookView({ book, data }: { book: FutBook; data: TerminalData }) {
  const now = useNow(30_000);
  const st = data.status ?? {};
  const age = (k: string) => ageStep((data.age_min ?? {})[k]) ?? undefined;
  const r = read(data, book);
  const drv = SCORED.has(book) ? data.drivers?.books?.[book] : undefined;
  // The bias slid out for one contract follows the page to the next: a view is keyed by
  // its book, so this runs as one opens. Left shut when it was shut.
  useEffect(() => {
    const out = biasOut();
    if (out && out !== book) openBias(book);
  }, [book]);
  const gw = gammaWord(r);
  // One row a release, so 08:30 names the release's lead series (lib/releases).
  const leads = useMemo(
    () =>
      groupReleases(data.calendar ?? NONE, (x: CalendarRow) => ({
        event: x.event,
        when: x.ts,
        country: x.country,
        score: x.score,
        figures: [x.actual_raw, x.consensus_raw, x.previous_raw],
      })).map((x) => x.lead),
    [data.calendar],
  );
  const next = now == null ? null : nextRelease(leads, book, now / 1000);
  const when = next ? whenWord(next, now) : null;
  // The chart's own four levels, handed up each time it reads its bars: the card and the
  // lines beside it are one set of prices. Held as it was while nothing has changed.
  const [chartLevels, setChartLevels] = useState<ChartLevels | null>(null);
  const onLevels = useCallback((l: ChartLevels | null) => {
    const got = l ? { pdh: l.pdh, pdl: l.pdl, pmh: l.pmh, pml: l.pml, pm_done: l.pm_done } : null;
    setChartLevels((was) => (sameLevels(was, got) ? was : got));
  }, []);
  // The day's own range so far: a future's quote runs its high and low from the 18:00 reopen.
  const lv = levelsCard(chartLevels, r.last, r.q ? { high: r.q.high, low: r.q.low } : null, r.dp);
  const dt = data.daytype?.books?.[book] ?? null;
  const sess = sessionCard(dt);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="qt-stats flex shrink-0 flex-wrap border-b border-ring">
        <div className="qt-stat flex min-w-[190px] flex-1 items-center gap-3 border-r border-ring px-4 py-[7px]">
          <AssetIcon id={book} size={30} className="block shrink-0 text-ink-2" />
          <div className="min-w-0">
            <p className="flex items-baseline gap-2 whitespace-nowrap">
              <Tick value={num(r.last, r.dp)} className="fig text-[16px] leading-none text-ink" />
              <Tick value={pct(r.q?.pct)} className={cn("fig text-[12px]", dir(r.q?.pct))} />
            </p>
            <p className="qt-cap mt-[5px] text-[9.5px] leading-none text-ink-2">{book}</p>
            <p className="mt-[3px] truncate text-[11px] leading-[1.2] text-ink-3">{FUT_NAME[book]}</p>
          </div>
        </div>
        {drv ? (
          // From the right since 2026-11-16, as a stock's chart is (vol/BiasDrawer); a popover until then.
          <BiasOpener book={book} className="qt-stat flex min-w-[190px] flex-1 items-center gap-3 rounded-none border-r border-ring px-4 py-[7px] text-left">
            {/* A SCALE WHERE THE COUNT WAS (owner, 2026-11-15: "instead of bias saying 6 of 14
                reads or whatever, why dont we jus have a scale instead"). The contents are
                the Stocks tape card's too (ScanWide BiasStat), so the two cannot differ.
                The count is on the scale's hover and in the board this card opens. */}
            <BiasStat what="Bias" side={drv.bias} score={wholeScore(drv)} grade={drv.grade} scaleTitle={liveLine(drv)} />
          </BiasOpener>
        ) : (
          <StatCard glyph="tape" value="—" hue="text-ink-3" label="Bias" sub="Not scored yet" />
        )}
        <StatCard glyph="pulse" value={gw.word} hue={gw.hue} label="Gamma" sub={gw.line} title="The regime says how far a move runs, not which way: positive is not bullish, negative is not bearish" />
        {/* SESSION TYPE AND LEVELS, WHERE DAY RANGE AND NEAREST LEVELS STOOD (owner,
            2026-11-15: "is there anything mor euseful we can replace day range and nearest
            levels with?", then "yes do it"). Each of those was a second copy of something on
            this page: the range used is the Session ranges card's Fuel line, the distance
            to a level is on the chart. These two are on no other card (lib/futCards). */}
        {sess && dt ? (
          <StatCard
            glyph="session"
            tint="move"
            value={sess.value}
            hue={sess.hue}
            label={sess.label}
            sub={sess.sub}
            title={sess.title}
            pop={{ label: `${book} session type: every condition that holds today`, panel: <SessionPanel book={book} st={dt} rec={data.daytype?.record?.[book]} /> }}
          />
        ) : (
          <StatCard glyph="session" value="—" hue="text-ink-3" label="Session type" sub={DAY_TYPED.has(book) ? "Not read yet" : "No record kept yet for silver and crude"} />
        )}
        <StatCard glyph="levels" value={lv.value} hue={lv.hue} label="Levels" sub={lv.sub} title={lv.title} />
        <StatCard
          glyph="clock"
          value={when ? when.value : "—"}
          hue={next && next.ts != null && now != null && next.ts - now / 1000 <= 1800 ? "text-flip-fig" : "text-ink"}
          label="Next release"
          // The country first: "GDP Price Index y/y" with none on it was Japan's. The hour
          // rides behind a countdown; past a day the figure is the day and the hour itself.
          sub={next ? [countryShort(next.country), next.event, when?.soon && next.et ? `${next.et} ET` : null].filter(Boolean).join(" · ") : "No US release scored 4 or more ahead"}
          title={next ? `${next.country} · ${next.event}${next.et ? ` · ${next.date} ${next.et} ET` : ""}\nThe next US release scored 4 or more that reaches ${FUT_NAME[book]}, or one named for it.` : undefined}
        />
      </div>
      {/*
        The chart sits on the right, where the Scanner's slide-out opens (owner,
        2026-11-10: "the charts should be on the right like the scanner does"), so
        the eye reads the figures first and finds the picture in the same place on
        both pages. Stacked on a narrow window it comes first, as the slide-out's does.
      */}
      <div className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.9fr)] xl:overflow-hidden">
        <div className={COL}>
          <FuturesNews wire={data.wire ?? NONE} now={now} book={book} />
        </div>
        <div className={COL}>
          <MRanges assets={data.ranges?.assets ?? {}} ladders={data.ladders} only={book} ageMin={age("ranges")} error={st.ranges?.ok === false ? st.ranges.error : null} />
          <MProfile data={data.profiles} ladders={data.ladders} only={book} ageMin={age("profiles")} error={st.profiles?.ok === false ? st.profiles.error : null} />
          <MGamma
            assets={data.gex?.assets ?? {}}
            enabled={data.gex?.enabled ?? false}
            only={book}
            ageMin={age("gex")}
            error={st.gex?.ok === false ? st.gex.error : null}
            implied={data.volterm?.books}
            expiry={data.expiry}
          />
        </div>
        <section aria-label={`${book} chart`} className="qt-card order-first flex min-h-[460px] min-w-0 flex-col overflow-hidden rounded-[6px] border border-ring xl:order-none xl:min-h-0">
          {/* Live from the tracking ETF between 04:00 and 17:00 ET (server futfill.py, 2026-11-14):
              CME's own bars run ten minutes behind. */}
          <ScanChart key={book} sym={book} state={0} barsUrl={`/api/futures/bars/${book}`} tickUrl={`/api/futures/tick/${book}`} store="fut" onLevels={onLevels} />
        </section>
      </div>
    </div>
  );
}
