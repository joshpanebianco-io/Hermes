"use client";

import { memo, useMemo, useState } from "react";
import type { BriefLadder, CalendarRow, DayType, GexAsset, ImpliedBook, Quote, Terminal as TerminalData, WireItem } from "@/types/terminal";
import { Board } from "@/components/panels/Board";
import { Gamma } from "@/components/panels/Gamma";
import { Report } from "@/components/panels/Report";
import { Sessions } from "@/components/panels/Sessions";
import { SessionRanges } from "@/components/panels/SessionRanges";
import { Volatility } from "@/components/panels/Volatility";
import { VolumeProfile } from "@/components/panels/VolumeProfile";
import { ScanChart } from "@/components/panels/ScanChart";
import { Glyph, StatCard } from "@/components/panels/ScanWide";
import { DriverPopover, biasWord, gradeTone, voteTone } from "@/components/vol/DriverBoard";
import { AssetIcon } from "@/components/ui/AssetIcon";
import { PageLoader } from "@/components/ui/HelmLoader";
import { useSide } from "@/components/state/UiMode";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { liveLine, scoreText } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { CALL_HUE, labelWords, leanTitle, nightWords } from "@/lib/daytype";
import { ageStep, dir, inMin, num, pct } from "@/lib/format";
import { bookStories } from "@/lib/futNews";
import { regimeMeans } from "@/lib/gammaRegime";
import { FUT_BOOKS, FUT_NAME, FUT_VIEWS, QUOTE_KEY, SCORED, booksOf, isFutBook, isFuture, type FutBook, type FutView } from "@/lib/futures";
import { placedName } from "@/lib/releases";
import { segItem } from "@/lib/seg";
import type { ReportController } from "@/lib/useReport";
import { useNow } from "@/lib/useNow";

/**
 * Futures — everything about the futures traded, on one page (owner, 2026-11-10:
 * "a seperate futures section that has all info related to futures that we trade
 * - nq, es, gc, sil, cl1").
 *
 * IT REPLACES STRUCTURE'S FUTURES HALF, in Structure's place on the bar, so the
 * header's room is unchanged; the stocks half is the Scanner's
 * Index view. The page is built the way the Scanner is: a row of views, a row of
 * figures, one framed body.
 *
 *   Overview   the five side by side: price, bias, gamma, the implied day, the
 *              nearest level each way, the next release that reaches it; under
 *              them what moves them today, the news, the vol curve, the book
 *   NQ … CL    one contract: its figures, its chart with the levels drawn, the news
 *              that reaches it, the session ranges, the profile and gamma, all on
 *              that book
 *   Brief      the written pre-session brief (the Analysis tab carried it too until 2026-11-11)
 *
 * ONE BOOK A VIEW. The panels used to pick their own book each, so the ladder could
 * be on NQ beside gamma on ES; in a book's view all of them are that book.
 *
 * SILVER AND CRUDE ARE NOT SCORED YET. They have the levels, ranges, profile, gamma
 * and implied day; the driver board's bias and the written brief are NQ, ES and GC
 * until their weights are worked out, and their cards say so rather than show a gap.
 */

const SOURCES = ["quotes", "ranges", "profiles", "gex"];
const NONE: never[] = [];
// Shrinkable only side by side: stacked, a column that shrinks spills into the next one.
const COL = "qt-col flex min-w-0 flex-col gap-2 xl:min-h-0 xl:overflow-y-auto";

const MRanges = memo(SessionRanges);
const MProfile = memo(VolumeProfile);
const MGamma = memo(Gamma);
const MVol = memo(Volatility);
const MBoard = memo(Board);

export function FuturesBoard({
  data,
  view,
  onView,
  report,
}: {
  data: TerminalData;
  view: FutView;
  onView: (v: FutView) => void;
  report: ReportController;
}) {
  const st = data.status ?? {};
  const ready = Boolean(data.offline) || SOURCES.every((k) => st[k] !== undefined);
  // The Sidebar interface lists the views itself and says the session in its header.
  const side = useSide();
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {!side && <Masthead view={view} onView={onView} phase={data.clock?.phase.label ?? null} />}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
        {!ready ? (
          <PageLoader label="Loading the desk" size={64} />
        ) : view === "overview" ? (
          <Overview data={data} onPick={onView} />
        ) : view === "brief" ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <Report {...report} />
          </div>
        ) : isFutBook(view) ? (
          <BookView key={view} book={view} data={data} />
        ) : null}
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
            {isFutBook(v.key) && <AssetIcon id={v.key} size={13} className="block shrink-0" />}
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
  up: { price: number; label: string } | null;
  down: { price: number; label: string } | null;
}

function read(data: TerminalData, book: FutBook): Read {
  const q = (data.quotes ?? NONE).find((x: Quote) => x.key === QUOTE_KEY[book]) ?? null;
  const ladder = data.ladders?.[book] ?? null;
  const g = data.gex?.assets?.[book] ?? null;
  const gex = g?.ok ? g : null;
  const implied = data.volterm?.books?.find((x) => x.key === book) ?? null;
  const last = q?.last ?? ladder?.last ?? null;
  const dp = ladder?.dp ?? implied?.dp ?? 2;
  const rows = (ladder?.rows ?? []).filter((r) => r.kind !== "last" && r.kind !== "em");
  const above = last == null ? [] : rows.filter((r) => r.price > last).sort((a, b) => a.price - b.price);
  const below = last == null ? [] : rows.filter((r) => r.price < last).sort((a, b) => b.price - a.price);
  return {
    q,
    last,
    dp,
    ladder,
    gex,
    flip: gex?.levels.find((l) => l.key === "flip")?.price ?? null,
    implied,
    up: above[0] ? { price: above[0].price, label: above[0].label } : null,
    down: below[0] ? { price: below[0].price, label: below[0].label } : null,
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

function upcoming(calendar: CalendarRow[], now: number | null): CalendarRow[] {
  if (now == null) return [];
  return calendar
    .filter((r) => !r.released && r.ts != null && r.ts > now / 1000 - 60 && r.score >= 3)
    .sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0) || b.score - a.score);
}

/**
 * One row a release: CPI prints as seven figures at 08:30, and seven rows saying the
 * same minute pushed everything else off the card. The heaviest names the row, and
 * the rest are a count, as the Calendar groups them.
 */
function oneEach(rows: CalendarRow[]): Array<{ row: CalendarRow; more: number }> {
  const out: Array<{ row: CalendarRow; more: number }> = [];
  for (const r of rows) {
    const same = out.find((x) => x.row.ts === r.ts && x.row.country === r.country);
    if (same) same.more += 1;
    else out.push({ row: r, more: 0 });
  }
  return out;
}

const untilWord = (r: CalendarRow, now: number | null) => (now == null || r.ts == null ? "" : `in ${inMin((r.ts - now / 1000) / 60)}`);

/* -------------------------------------------------------------------------- */
/* Overview                                                                    */
/* -------------------------------------------------------------------------- */

function Overview({ data, onPick }: { data: TerminalData; onPick: (v: FutView) => void }) {
  const now = useNow(30_000);
  const st = data.status ?? {};
  const age = (k: string) => ageStep((data.age_min ?? {})[k]) ?? undefined;
  const next = useMemo(() => upcoming(data.calendar ?? NONE, now), [data.calendar, now]);
  // The book is the contracts alone: the feed's group also holds each one's ETF (QQQ,
  // SPY, GLD, IWM), and those are the stocks pages' (lib/futures.isFuture).
  const contracts = useMemo(() => (data.quotes ?? NONE).filter(isFuture), [data.quotes]);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {/* `qt-books`: under Luminous, where the five sit in one row, they are columns of one
          card and the band over the page is its top (globals.css). */}
      <div className="qt-tiles qt-books grid shrink-0 grid-cols-1 gap-px border-b border-ring bg-ring sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        {FUT_BOOKS.map((b) => (
          <BookCard key={b} book={b} data={data} next={next.find((r) => booksOf(r).includes(b)) ?? null} now={now} onPick={() => onPick(b)} />
        ))}
      </div>
      <div className="qt-board grid grid-cols-1 gap-2 p-2 xl:grid-cols-3">
        <div className="qt-col flex min-w-0 flex-col gap-2">
          <MovesToday rows={oneEach(next.filter((r) => booksOf(r).length > 0)).slice(0, 10)} now={now} />
          <FuturesNews wire={data.wire ?? NONE} now={now} />
        </div>
        <div className="qt-col flex min-w-0 flex-col gap-2">
          <SessionType dt={data.daytype} />
          <MVol vol={data.volterm} ageMin={age("quotes")} implied putcall={data.putcall} />
        </div>
        <div className="qt-col flex min-w-0 flex-col gap-2">
          <MBoard title="The book" quotes={contracts} groups={["core"]} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
          {data.clock && <Sessions clock={data.clock} />}
        </div>
      </div>
    </div>
  );
}

/** The books the record is kept for (daytype.BOOKS); silver and crude have none yet. */
const DAY_BOOKS: FutBook[] = ["NQ", "ES", "GC"];

/**
 * Session type — will New York trend or range (daytype.py). One row a book: the
 * call, the night so far and yesterday's shape, and under it the conditions that
 * carry the call with their counts; a click opens every condition that holds today
 * with its count over the record, and the base rate. After the close the row says
 * what the day was. Counts, never probabilities — the server's own words.
 */
function SessionType({ dt }: { dt: DayType | undefined }) {
  const [open, setOpen] = useState<string | null>(null);
  const rec = dt?.record?.NQ;
  const sub = rec?.n ? `will New York trend or range · ${rec.n.toLocaleString()} sessions since ${rec.from ?? "?"}` : "will New York trend or range";
  return (
    <Module title="Session type" sub={sub} bodyClassName="px-0 py-0" error={dt?.error ?? null}>
      <ul>
        {DAY_BOOKS.map((b) => {
          const e = dt?.books?.[b] ?? null;
          const isOpen = open === b;
          const r = dt?.record?.[b];
          return (
            <li key={b} className="border-b border-ring/60 last:border-b-0">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : b)}
                aria-expanded={isOpen}
                title={e ? leanTitle(e.lean) : "The ranges or the daily bars have not arrived for this book"}
                className="hit flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-surface"
              >
                <AssetIcon id={b} size={18} className="mt-px shrink-0 text-ink-2" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="text-[13px] font-semibold text-ink">{b}</span>
                    {e ? (
                      <span className={cn("min-w-0 truncate text-[12.5px] font-semibold", CALL_HUE[e.lean.call])}>{e.label ? `Today: ${labelWords(e.label)}` : e.lean.word}</span>
                    ) : (
                      <span className="text-[12.5px] text-ink-3">Not read yet</span>
                    )}
                    {e && <span className="fig ml-auto shrink-0 text-[10.5px] text-ink-3">{nightWords(e.lean)}</span>}
                  </span>
                  {e && <span className="mt-0.5 block truncate text-[11.5px] text-ink-2">{e.lean.why}</span>}
                </span>
              </button>
              {isOpen && e && (
                <div className="border-t border-ring/40 px-3 py-2 text-[11.5px]">
                  <ul className="space-y-0.5">
                    {e.lean.holds.map((h) => (
                      <li key={h.condition} className="flex items-baseline gap-2">
                        <span className={cn("min-w-0 flex-1", h.vote ? "text-ink" : "text-ink-2")}>
                          {h.condition}
                          {h.shown && <span className="fig text-ink-3"> · {h.shown}</span>}
                        </span>
                        <span className="fig shrink-0 text-ink-2">
                          {h.trend} trend in {h.n} · {h.range} range
                        </span>
                        <span className="qt-cap w-[64px] shrink-0 text-right text-[9.5px] text-ink-3">{h.vote ? `votes ${h.vote}` : ""}</span>
                      </li>
                    ))}
                    {e.lean.holds.length === 0 && <li className="text-ink-3">No condition in the record holds today.</li>}
                  </ul>
                  <p className="fig mt-1.5 border-t border-ring/40 pt-1.5 text-[10.5px] text-ink-3">
                    every session: {e.lean.base.trend} trend days in {e.lean.base.n}, {e.lean.base.range} range
                    {r ? ` · ${r.backfill} from the backfill, ${r.live} live` : ""} · counts, not probabilities
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Module>
  );
}

function Line({ label, children, hue, title }: { label: string; children: React.ReactNode; hue?: string; title?: string }) {
  return (
    <p className="flex items-baseline gap-2 text-[12px] leading-[1.35]" title={title}>
      <span className="qt-cap w-[52px] shrink-0 text-[9.5px] text-ink-3">{label}</span>
      <span className={cn("min-w-0 truncate", hue ?? "text-ink-2")}>{children}</span>
    </p>
  );
}

/** One contract on the overview: the whole read in a card, a click opens its view. */
function BookCard({ book, data, next, now, onPick }: { book: FutBook; data: TerminalData; next: CalendarRow | null; now: number | null; onPick: () => void }) {
  const r = read(data, book);
  const drv = SCORED.has(book) ? data.drivers?.books?.[book] : undefined;
  const gw = gammaWord(r);
  const imp = r.implied;
  const st = data.daytype?.books?.[book] ?? null;
  return (
    <button type="button" onClick={onPick} title={`Open ${FUT_NAME[book]}`} className="hit flex min-w-0 flex-col gap-1.5 bg-bg px-4 py-3 text-left hover:bg-surface">
      <p className="flex items-center gap-2">
        <AssetIcon id={book} size={20} className="block shrink-0 text-ink-2" />
        <span className="text-[15px] leading-none font-semibold text-ink">{book}</span>
        <span className="min-w-0 truncate text-[11.5px] text-ink-3">{FUT_NAME[book]}</span>
      </p>
      <p className="flex items-baseline gap-2">
        <Tick value={num(r.last, r.dp)} className="fig text-[19px] leading-none text-ink" />
        <Tick value={pct(r.q?.pct)} className={cn("fig text-[12.5px]", dir(r.q?.pct))} />
      </p>
      <div className="mt-0.5 flex flex-col gap-[3px]">
        <Line label="Bias" hue={drv ? voteTone(drv.bias) : "text-ink-3"} title={drv ? liveLine(drv) : "Silver and crude have no driver-board score yet"}>
          {drv ? (
            <>
              {biasWord(drv.bias)} <span className="fig">{scoreText(drv.score)}</span> <span className={cn("qt-cap text-[9.5px]", gradeTone(drv))}>{drv.grade}</span>
            </>
          ) : (
            "Not scored yet"
          )}
        </Line>
        <Line label="Gamma" hue={gw.hue} title={gw.line}>
          {gw.word}
          {r.gex && r.flip != null && r.last != null && <span className="fig text-ink-3"> · {r.last >= r.flip ? "above" : "below"} flip</span>}
        </Line>
        <Line label="Implied" title={imp ? `${imp.vol_key} ${num(imp.vol, 1)} · the one-sigma day` : undefined}>
          {imp?.sigma != null ? (
            <span className="fig">
              ±{num(imp.sigma, r.dp)}
              {imp.used != null && (
                <span className={imp.fuel === "stretched" ? "text-flip-fig" : "text-ink-3"}> · {Math.round(imp.used * 100)}% used</span>
              )}
            </span>
          ) : (
            "—"
          )}
        </Line>
        <Line label="Session" hue={st ? CALL_HUE[st.lean.call] : "text-ink-3"} title={st ? leanTitle(st.lean) : "No session-type record for this book yet"}>
          {st ? (
            <>
              {st.label ? `Today: ${labelWords(st.label)}` : st.lean.word}
              {!st.label && st.lean.night.atr != null && (
                <span className="fig text-ink-3">
                  {" "}
                  · night {st.lean.night.atr.toFixed(2)} ATR{st.lean.night.done === false ? " so far" : ""}
                </span>
              )}
            </>
          ) : (
            "No record yet"
          )}
        </Line>
        <Line label="Above" hue="text-call-fig">
          {r.up ? (
            <span className="fig">
              {num(r.up.price, r.dp)} <span className="text-ink-3">{r.up.label}</span>
            </span>
          ) : (
            "—"
          )}
        </Line>
        <Line label="Below" hue="text-put-fig">
          {r.down ? (
            <span className="fig">
              {num(r.down.price, r.dp)} <span className="text-ink-3">{r.down.label}</span>
            </span>
          ) : (
            "—"
          )}
        </Line>
        <Line label="Next" hue={next ? "text-ink-2" : "text-ink-3"}>
          {next ? (
            <>
              <span className="fig text-ink">{untilWord(next, now)}</span> {placedName(next.event, next.country)}
            </>
          ) : (
            "Nothing scheduled"
          )}
        </Line>
      </div>
    </button>
  );
}

function MovesToday({ rows, now }: { rows: Array<{ row: CalendarRow; more: number }>; now: number | null }) {
  return (
    <Module title="What moves them" sub="releases scored 3+, and the books each reaches" bodyClassName="px-0 py-0">
      {rows.length === 0 ? (
        <p className="px-3 py-4 text-[12px] text-ink-3">Nothing scheduled that reaches these books.</p>
      ) : (
        <ul className="py-1">
          {rows.map(({ row: r, more }, i) => (
            <li key={`${r.event}-${r.ts}-${i}`} className="flex items-center gap-2 px-3 py-[5px]">
              <span className="fig w-[124px] shrink-0 text-[11px] whitespace-nowrap text-ink-3">
                {r.et ?? "—"} <span className="text-ink-4">{untilWord(r, now)}</span>
              </span>
              <span className="min-w-0 flex-1 truncate text-[12px] text-ink">
                {placedName(r.event, r.country)}
                {more > 0 && <span className="fig text-ink-3"> +{more}</span>}
              </span>
              <span className="flex shrink-0 items-center gap-1">
                {booksOf(r).map((b) => (
                  <span key={b} title={FUT_NAME[b]}>
                    <AssetIcon id={b} size={14} className="block text-ink-3" />
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Module>
  );
}

/**
 * The wire's stories that reach a book, or on the Overview any of them (lib/futNews):
 * the Fed, US data and yields for the indices and the metals, oil and the Gulf for
 * crude, nothing from another country's central bank. In a book's view it stands
 * where the ladder stood (owner, 2026-11-10: "instead of Levels section maybe have a
 * news feed with important things that affect that, eg if nq then things that have
 * high impact on nq"); the ladder's rows are drawn on the chart, and Hermes still
 * reads the ladder itself. Two lines a story: the headline, then why it is here,
 * who filed it and how long ago, and on the Overview the books it reaches.
 */
function FuturesNews({ wire, now, book }: { wire: WireItem[]; now: number | null; book?: FutBook }) {
  const rows = useMemo(() => bookStories(wire, book), [wire, book]);
  return (
    <Module
      title={book ? `${book} news` : "Futures news"}
      sub={book ? `what reaches ${FUT_NAME[book]} · high and medium` : "what reaches the books · high and medium"}
      bodyClassName="px-0 py-0"
    >
      {rows.length === 0 ? (
        <p className="px-3 py-4 text-[12px] text-ink-3">{book ? `No high or medium story reaches ${FUT_NAME[book]} right now.` : "No high or medium story reaches these books."}</p>
      ) : (
        <ul className="py-1">
          {rows.map(({ item: w, tags, books }) => (
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
                  {!book && (
                    <span className="flex shrink-0 items-center gap-1">
                      {books.map((b) => (
                        <span key={b} title={FUT_NAME[b]}>
                          <AssetIcon id={b} size={13} className="block text-ink-3" />
                        </span>
                      ))}
                    </span>
                  )}
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
  const gw = gammaWord(r);
  const imp = r.implied;
  const next = upcoming(data.calendar ?? NONE, now).find((x) => booksOf(x).includes(book)) ?? null;
  const fuelHue = imp?.fuel === "stretched" ? "text-flip-fig" : imp?.fuel === "room" ? "text-call-fig" : "text-ink";
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
          <DriverPopover book={drv} className="qt-stat flex min-w-[190px] flex-1 items-center gap-3 rounded-none border-r border-ring px-4 py-[7px] text-left">
            <span className={cn("flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[5px] border border-ring-2 bg-surface-2", voteTone(drv.bias))}>
              <Glyph name="tape" />
            </span>
            <span className="flex min-w-0 flex-col">
              <span className={cn("fig text-[16px] leading-none whitespace-nowrap", voteTone(drv.bias))}>
                {biasWord(drv.bias)} {scoreText(drv.score)}
              </span>
              <span className="qt-cap mt-[5px] text-[9.5px] leading-none text-ink-2">Bias · {drv.grade}</span>
              <span className="mt-[3px] truncate text-[11px] leading-[1.2] text-ink-3">{liveLine(drv)}</span>
            </span>
          </DriverPopover>
        ) : (
          <StatCard glyph="tape" value="—" hue="text-ink-3" label="Bias" sub="Not scored yet for silver and crude" />
        )}
        <StatCard glyph="pulse" value={gw.word} hue={gw.hue} label="Gamma" sub={gw.line} title="The regime says how far a move runs, not which way: positive is not bullish, negative is not bearish" />
        <StatCard
          glyph="arrow"
          tint="move"
          value={imp?.sigma != null ? `±${num(imp.sigma, r.dp)}` : "—"}
          label="Implied day"
          sub={imp?.lo != null && imp.hi != null ? `${num(imp.lo, r.dp)} – ${num(imp.hi, r.dp)}` : undefined}
          title={imp ? `The one-sigma day from ${imp.vol_key}` : undefined}
        />
        <StatCard
          glyph="bolt"
          value={imp?.used != null ? `${Math.round(imp.used * 100)}%` : "—"}
          hue={fuelHue}
          label="Range used"
          sub={imp?.fuel ? `${imp.fuel} · of the implied day` : undefined}
        />
        <StatCard
          glyph="star"
          tint="news"
          value={imp?.vol != null ? `${imp.vol_key} ${num(imp.vol, 1)}` : "—"}
          hue="text-desk-markets"
          label="Implied vol"
          sub={imp?.iv_rv != null ? `IV/RV ${num(imp.iv_rv, 2)}${imp.premium ? ` · ${imp.premium}` : ""}` : undefined}
        />
        <StatCard
          glyph="clock"
          value={next ? untilWord(next, now) : "—"}
          hue={next && next.ts != null && now != null && next.ts - now / 1000 <= 1800 ? "text-flip-fig" : "text-ink"}
          label="Next release"
          sub={next ? next.event : "Nothing scheduled that reaches it"}
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
          <MRanges assets={data.ranges?.assets ?? {}} ladders={data.ladders} expiry={data.expiry} only={book} ageMin={age("ranges")} error={st.ranges?.ok === false ? st.ranges.error : null} />
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
          <ScanChart key={book} sym={book} state={0} barsUrl={`/api/futures/bars/${book}`} live={false} store="fut" />
        </section>
      </div>
    </div>
  );
}
