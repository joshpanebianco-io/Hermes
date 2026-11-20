"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { setAskFocus } from "@/lib/ask/open";
import type { CalendarRow, ExpiryState, Terminal as TerminalData } from "@/types/terminal";
import { expiryLine, expiryTitle, nextExpiries } from "@/lib/expiryWords";
import { DASH_BOOKS, futuresBrief, nextEvent, sessionStrip, weightsWord } from "@/lib/futDash";
import { DAY_TYPED, FUT_NAME, QUOTE_KEY, type FutView } from "@/lib/futures";
import { CALL_HUE } from "@/lib/daytype";
import { wholeScore } from "@/lib/biasScale";
import type { DashImpact, DashRow, DashStory, DashboardPayload } from "@/types/dashboard";
import { BreadthBars } from "@/components/panels/Breadth";
import { setupLabel } from "@/components/panels/ScanDetail";
import { CARD, CatalystCell, Chips, Spark, TD, TH, ageWord, dayName, rowProps } from "@/components/panels/ScanWide";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import { AgeChip } from "@/components/ui/Module";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { SectorGlyph } from "@/components/ui/SectorGlyph";
import { scoreText } from "@/lib/bias";
import { BiasScale } from "@/components/ui/BiasScale";
import { cn } from "@/lib/cn";
import { dir, inMin, num, pct } from "@/lib/format";
import { heatMax, heatStyle } from "@/lib/heat";
import { keepRead, lastRead } from "@/lib/lastRead";
import { etDay, useNextPrint } from "@/lib/nextPrint";
import type { ScanView, Tab } from "@/lib/tabs";
import { openTicker, useTicker } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";
import { oneOf, persist, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";
import { useRefresh } from "@/lib/refresh";

/**
 * The Dashboard: the session on one page.
 *
 * WHY (owner, 2026-11-09: "can we also have a dashboard section like the shown in some
 * of the screen shots", then "can we follow the layout a bit closer"). Three rows, as
 * in those screenshots: the read beside the game plan; the top setups, the list and
 * the news; the eleven sectors. Macro stays as it was.
 *
 * NOTHING HERE IS NEW INFORMATION, and every part opens where it came from. The read is
 * a fixed rule over the tape count, the VIX band and breadth (server dashboard.py), and
 * the top setups are the scanner's own rank, because this terminal has nobody picking
 * names by hand.
 */

const POLL_SEC = 30;
const LIVE_POLL_SEC = 10;

const WHEN_WORD = { pre: "before the open", after: "after the close", unspecified: "time not set" } as const;

type TopChip = "all" | "long" | "short" | "news";

const TOP_CHIPS: ReadonlyArray<{ key: TopChip; label: string }> = [
  { key: "all", label: "All" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "news", label: "Has News" },
];
const TOP_TEST: Record<TopChip, (r: DashRow) => boolean> = {
  all: () => true,
  long: (r) => r.score.side === "long",
  short: (r) => r.score.side === "short",
  news: (r) => r.catalyst != null,
};

export function Dashboard({
  calendar,
  onOpen,
  onScan,
  prices = null,
  futures = null,
  expiry = null,
}: {
  calendar: CalendarRow[];
  /** The options expiry calendar, from the Terminal's poll (server expiry.py), for the game plan's Expiry line. */
  expiry?: ExpiryState | null;
  onOpen: (t: Tab) => void;
  onScan: (v: ScanView) => void;
  /** The Futures card's data, the Terminal's poll, and where a row opens (FuturesCard). */
  futures?: { data: TerminalData; onBook: (v: FutView) => void } | null;
  /**
   * The row of prices across the top (owner, 2026-11-10: move the header's figures to
   * "there appropriate places"). Built by the Terminal, which holds the quotes. Since
   * 2026-11-12 it is SPY, QQQ, IWM and VIX alone: the futures are the Futures tab's and
   * the macro figures Macro's (lib/quoteTiles.DASH_GROUPS).
   */
  prices?: React.ReactNode;
}) {
  const now = useNow(30_000);
  const later = useNextPrint(calendar, now);
  // A return to the page opens on what it last showed, until its first poll lands (lib/lastRead).
  const [data, setData] = useState<DashboardPayload | null>(() => lastRead<DashboardPayload>("dashboard"));
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/dashboard", { cache: "no-store" });
      const d = (await r.json()) as DashboardPayload;
      if (mine === seq.current) setData(keepRead("dashboard", d));
    } catch {
      /* the last read stays on screen */
    }
  }, []);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);
  // The header's refresh button reads this page again too (lib/refresh).
  useRefresh(load);

  const live = data?.session === "rth";
  useEffect(() => {
    void load();
    const id = setInterval(load, (live ? LIVE_POLL_SEC : POLL_SEC) * 1000);
    return () => clearInterval(id);
  }, [load, live]);

  // The Scanner reads its filters, and the Sectors tab its card, from storage as they mount.
  const toScanner = useCallback(
    (view: ScanView, also: Record<string, unknown> = {}) => {
      for (const [k, v] of Object.entries(also)) persist(k, v);
      onScan(view);
    },
    [onScan],
  );
  const toSectors = useCallback(
    (also: Record<string, unknown> = {}) => {
      for (const [k, v] of Object.entries(also)) persist(k, v);
      onOpen("sectors");
    },
    [onOpen],
  );

  // Hermes reads the name open in the slide-out: "explain this setup" means it.
  const ticker = useTicker();
  useEffect(() => {
    setAskFocus(ticker);
    return () => setAskFocus(null);
  }, [ticker]);

  /*
   * WAITING IS A CARD WHERE THE PAGE WILL BE (owner, 2026-11-11: "when dashboard loads it
   * should have have card in the middle, right now it's empty and jsut have the header
   * and footer cards and looks weird"): one card with the helm in the middle, or the
   * reason there is nothing to show. The prices are inside the read's card since
   * 2026-11-12, so they arrive with it.
   */
  if (!data || !data.ok || data.offline) {
    return (
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lum:gap-[var(--lum-gap)] lum:p-[var(--lum-gap)]">
        {!data ? (
          <PageLoader label="Reading the session" className={CARD} />
        ) : (
          <PageNote className={CARD}>
            {data.offline ? `${data.offline.reason}.` : "The scanner has not built yet: the first pass takes about a minute and a half after a start."}
          </PageNote>
        )}
      </main>
    );
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lum:gap-[var(--lum-gap)] lum:p-[var(--lum-gap)]">
      {/*
        * THE FIRST ROW IS THREE CARDS: the read, the plan, breadth (owner, 2026-11-12:
        * the "card with the indicies and vix spots looks weird and out of place, breadth
        * advancers vs decliners may need to be it's own card"). The four prices were a
        * thin card of their own across the whole page, four figures a screen-width apart;
        * they are the head of the read now, which is the card that talks about them.
        * Breadth was the right half of the plan, a chart sharing a card with a list of
        * words. Two columns with breadth under them on a narrower window.
        */}
      {/* FOUR SINCE 2026-11-16: the Futures card is the fourth (owner: "a futures card
          whcih also says what session it is", "like a bias kind of card and quick brief
          sumamry"). Four across from 2200px (the owner's main screen), two by two under it. */}
      {/* THREE AGAIN SINCE 2026-11-16 (owner: "the pre market card is a bit redundant or
          could be merged into the today game plan one", then "do waht you recommend
          best"): the read card's prices, its VIX sentence, its counts and its calendar
          are the game plan's head and foot; its sentence on the leaders and breadth was
          the plan's focus lines and the Breadth card again. */}
      {/* Three across from 1280px, as the row under it is: the owner's 1920 screens had
          the four-card rule's two-by-two, which left Futures alone beside a hole. Under
          1280 the game plan and Breadth share a row and Futures takes the next whole. */}
      {/* Earlier the same day the game plan was made wider than Breadth (1.55 : 0.9 : 1.2) so
          its sectors and themes sat on one line; the even columns below replaced that. Breadth
          fills its card's height instead of floating. */}
      {/* THREE EVEN COLUMNS ON BOTH ROWS (owner, 2026-11-19: "restructure the widths and space
          so that it looks more even", the flip mock at 2560 approved: "the dashboard mock is
          good"). 841px a card at 2560, 629 at 1920; it was 1071 | 622 | 829. */}
      <div className="grid shrink-0 gap-3 lum:gap-[var(--lum-gap)] lg:grid-cols-2 xl:grid-cols-[repeat(3,minmax(0,1fr))]">
        <PlanCard d={data} later={later} now={now} prices={prices} expiry={expiry} onWire={() => onOpen("terminal")} toScanner={toScanner} />
        <BreadthCard d={data} />
        {futures && <FuturesCard {...futures} />}
      </div>
      {/* Row two's history, all 2026-11-19: the Market report card went (it repeated the
          plan's bias); Top setups took two thirds and the owner found it "so wide, it's
          uneven"; it went under the plan alone with Stock news, then Live signals, between;
          then High impact news replaced Live signals and both rows went even. */}
      {/* HIGH IMPACT NEWS IN LIVE SIGNALS' PLACE (owner, 2026-11-19: "replace the live signals
          card on dashboard with a High Impact News card ... important headlines, geopolitcs,
          IPO's earnigns ofr the day"). The signals still alert, and each Scanner row shows
          its last one. */}
      <div className="grid gap-3 lum:gap-[var(--lum-gap)] xl:min-h-[320px] xl:flex-1 xl:grid-cols-[repeat(3,minmax(0,1fr))] xl:grid-rows-[minmax(0,1fr)]">
        {/* The table, on the whole list: the Stocks tab's charts are a choice of their own. */}
        <TopSetups rows={data.top} age={data.ages?.top} onAll={() => toScanner("today", { "today.side": "all" })} />
        <HighImpact d={data.impact} age={data.ages?.impact} onWire={() => onOpen("terminal")} />
        <StockNews stories={data.stories} live={data.news_live} age={data.ages?.stories} />
      </div>
      <Rotation d={data} onHeat={() => toSectors()} onSector={(k) => toSectors({ "sec.mode": "cards", "sec.sel": k })} />
    </main>
  );
}

/* -------------------------------------------------------------------------- */
/* The pieces                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * A card's head. `age` is how long ago its figures were read, in minutes (owner, 2026-11-20:
 * "have the cards show how recently they were updated eg "4m ago" or "4m""): Macro's chip,
 * at the far right as a module has it, "now" under a minute, amber past ten, red past sixty.
 */
function Head({ title, sub, right, age }: { title: React.ReactNode; sub?: string; right?: React.ReactNode; age?: number | null }) {
  const aged = age != null && Number.isFinite(age);
  return (
    <div className="flex shrink-0 items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-[11.5px] text-ink-3">{sub}</p>}
      </div>
      {aged ? (
        <span className="flex shrink-0 items-center gap-3">
          {right}
          <AgeChip m={age} />
        </span>
      ) : (
        right
      )}
    </div>
  );
}

function Go({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="hit shrink-0 text-[11.5px] whitespace-nowrap text-ink-2 hover:text-ink">
      {children} →
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="qt-cap mb-1 text-[10px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}

/**
 * The futures at a glance (owner, 2026-11-16, of two mocks: prices, bias and session
 * type, the top row's fourth card, with "a quick brief summary"): the session strip,
 * two sentences the engine writes from the driver board (lib/futDash), then a row a
 * contract with its price, its bias on the scale and, for NQ, ES and gold, whether New
 * York is set up to trend or range. A row opens that contract on the Futures tab. All of
 * it is the Terminal's poll, so it moves with the Futures tab, not with this page's.
 */
function FuturesCard({ data, onBook }: { data: TerminalData; onBook: (v: FutView) => void }) {
  const books = data.drivers?.books ?? {};
  const boxes = data.clock?.boxes ?? [];
  const strip = data.clock ? sessionStrip(boxes, data.clock.et_time) : [];
  const ev = nextEvent(boxes);
  const leans = Object.fromEntries(DASH_BOOKS.map((k) => [k, data.daytype?.books?.[k]?.lean ?? null]));
  const brief = futuresBrief(books, leans, (b) => wholeScore(b) ?? b.score);
  const anyBook = DASH_BOOKS.map((k) => books[k]).find(Boolean);
  const phase = data.clock?.phase.label;
  return (
    <section className={cn(CARD, "flex flex-col gap-2.5 lg:col-span-2 xl:col-span-1")}>
      <Head
        title="Futures"
        sub={[phase, ev ? `${ev.label} ${ev.next} in ${inMin(ev.min)}` : null].filter(Boolean).join(" · ") || undefined}
        right={<Go onClick={() => onBook("report")}>Market report</Go>}
        // The prices' read, the Terminal poll's (the CME's own ten minutes are the foot's).
        age={data.age_min?.quotes}
      />
      {/* The four boxes of the futures day: done, trading now, still to come. */}
      <div className="-mx-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-ring/60 px-4 py-2 text-[11.5px]">
        {strip.map((b) => (
          <span key={b.key} className={cn("flex items-center gap-1.5 whitespace-nowrap", b.state === "now" ? "font-semibold text-ink" : b.state === "done" ? "text-ink-3" : "text-ink-2")}>
            {b.state === "now" ? (
              <span aria-hidden className="h-[7px] w-[7px] rounded-full bg-desk-policy" />
            ) : b.state === "done" ? (
              <span aria-hidden className="text-[10px]">✓</span>
            ) : null}
            {b.label}
            <span className="fig font-normal text-ink-3">{b.state === "now" ? `to ${b.at}` : b.state === "next" ? b.at : ""}</span>
          </span>
        ))}
      </div>
      <div className="space-y-1 text-[13px] leading-[1.45] text-ink-2">
        {brief.map((s) => (
          <p key={s}>{s}</p>
        ))}
      </div>
      <div className="-mx-1.5">
        {/* Captions (owner, 2026-11-16: "why are the nq and es both the same amount of bias
            points but nq says no lean and es says trend say mor eposisble"): the last column
            is the session-type record (will New York trend or range), not a second bias. */}
        <div aria-hidden className="qt-cap grid grid-cols-[34px_minmax(0,1fr)_minmax(0,1fr)_64px_minmax(0,1.1fr)] gap-x-2.5 px-1.5 pb-0.5 text-[9.5px] text-ink-3">
          <span />
          <span>Price</span>
          <span className="col-span-2">Bias · which way</span>
          <span className="truncate" title="Session type: will New York trend or range">Session type · trend or range</span>
        </div>
        {DASH_BOOKS.map((k) => {
          const b = books[k];
          const q = (data.quotes ?? []).find((x) => x.key === QUOTE_KEY[k]);
          const s = b ? (wholeScore(b) ?? b.score) : null;
          const tone = b?.bias === "long" ? "text-call-fig" : b?.bias === "short" ? "text-put-fig" : "text-ink-3";
          const lean = leans[k];
          return (
            <button
              key={k}
              type="button"
              onClick={() => onBook(k)}
              title={`Open ${k} · ${FUT_NAME[k]} on the Futures tab`}
              className="hit grid w-full grid-cols-[34px_minmax(0,1fr)_minmax(0,1fr)_64px_minmax(0,1.1fr)] items-center gap-x-2.5 rounded-[4px] px-1.5 py-[5px] text-left text-[12px]"
            >
              <span className="fig font-semibold text-ink">{k}</span>
              <span className="fig truncate text-ink">
                {num(q?.last)} <span className={cn("ml-1", dir(q?.pct))}>{pct(q?.pct)}</span>
              </span>
              <span className={cn("fig truncate", tone)}>
                {b ? (b.bias === "long" ? "▲ Long" : b.bias === "short" ? "▼ Short" : "No lean") : "—"}
                {s != null && ` ${scoreText(s)}`}
              </span>
              <BiasScale score={s} side={b?.bias ?? null} className="w-[64px]" />
              <span className={cn("truncate text-[11.5px]", lean ? CALL_HUE[lean.call as keyof typeof CALL_HUE] : "text-ink-3")} title={DAY_TYPED.has(k) ? "Will New York trend or range: the record's counts for a day like this one" : "No trend-or-range record is kept for this contract"}>
                {DAY_TYPED.has(k) ? (lean?.word ?? "Not read yet") : "—"}
              </span>
            </button>
          );
        })}
      </div>
      <p className="fig mt-auto text-[11px] text-ink-3">
        Bias weighed for {weightsWord(anyBook?.weight_label)} · CME prices about 10 min behind · click a row for its contract
      </p>
    </section>
  );
}

/**
 * The game plan, with the read folded in (2026-11-16): the four prices and the read's
 * sentence on the tape and the VIX at its head, the bias, the focus and the setups in
 * the middle, and the read's counts, the session's reports and the next release at its
 * foot. The read's second sentence (who leads, and breadth) was the focus lines and the
 * Breadth card again, so it is not printed.
 */
function PlanCard({
  d,
  later,
  now,
  prices,
  expiry,
  onWire,
  toScanner,
}: {
  d: DashboardPayload;
  later: CalendarRow | null;
  now: number | null;
  prices?: React.ReactNode;
  expiry?: ExpiryState | null;
  onWire: () => void;
  toScanner: (view: ScanView, also?: Record<string, unknown>) => void;
}) {
  const by = (w: "pre" | "after" | "unspecified") => d.read.reports.filter((r) => r.when === w).map((r) => r.sym);
  const reports = (["pre", "after", "unspecified"] as const)
    .filter((w) => by(w).length)
    .map((w) => `${by(w).join(", ")} ${WHEN_WORD[w]}`)
    .join(" · ");
  const ev = d.plan.event;
  const next = ev
    ? `${ev.title} · ${ev.et} ET · ${ev.in_min < 0 ? "just printed" : `in ${inMin(ev.in_min)}`}`
    : later && later.ts !== null && now !== null
      ? `${etDay(later.ts, now)}${later.event}${later.et ? ` · ${later.et} ET` : ""} · in ${inMin((later.ts - now / 1000) / 60)}`
      : d.plan.calendar_ok === false
        ? "Calendar feed down — the next release is unknown"
        : "None scheduled";
  const expiryText = expiryLine(expiry);
  const b = d.plan.bias;
  const hue = b.side === "long" ? "text-call-fig" : b.side === "short" ? "text-put-fig" : "text-ink-3";
  const tip = b.live != null && b.total != null ? `${b.live} of ${b.total} reads live${b.cap != null ? ` · plans capped at ${b.cap}` : ""}` : undefined;
  return (
    <section className={cn(CARD, "flex flex-col gap-3")}>
      <Head
        title="Today's RTH game plan"
        sub={`${d.read.title} · levels for ${dayName(d.trading_day)}`}
        age={d.ages?.plan}
        right={
          <span className="flex shrink-0 items-center gap-4">
            {/* The written note for this desk: the Stocks tab's Market Report view since
                2026-11-16 (SPY, QQQ and IWM for New York); the page it opened that morning
                left the bar, then became a view on each desk. */}
            <Go onClick={() => toScanner("report")}>Market report</Go>
            <Go onClick={onWire}>Open the wire</Go>
          </span>
        }
      />
      {/* SPY, QQQ, IWM and VIX, ruled off as the card's own figures; the edges run to the
          card's (its 16px of padding). Outside the session a fund shows its pre-market or
          after-hours trade (lib/quoteExt). */}
      {prices && (
        <div aria-label="Prices" className="-mx-4 border-y border-ring/60 px-4 py-2.5">
          {prices}
        </div>
      )}
      {/* The read's first sentence: the tape's lean and what the VIX band says to do. */}
      {d.read.lines[0] && <p className="text-[13px] leading-[1.45] text-ink-2">{d.read.lines[0]}</p>}
      {/* Two short columns. The counts' column is as wide as its longest line, which then
          never wraps; the sectors and themes take the rest and wrap as they need to. */}
      <div className="grid flex-1 content-start gap-x-8 gap-y-2.5 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="space-y-2.5">
          <Field label="Market bias">
            <span title={tip} className={cn("inline-flex items-baseline gap-1.5 rounded-[3px] border border-ring-2 px-2 py-0.5 text-[13px] font-semibold", hue)}>
              {b.side === "long" ? "▲ Long" : b.side === "short" ? "▼ Short" : "– No lean"}
              {/* The scale the Stocks tape card and the Futures bias cards draw (ui/BiasScale).
                  The score is over the whole weight (2026-11-15), so a read on two inputs of
                  eleven sits near the middle with its figure: no ring and no "thin". The
                  count is on the hover. */}
              {b.score != null && <BiasScale score={b.score} side={b.side} className="w-[104px] self-center" />}
              {b.score != null && <span className="fig">{scoreText(b.score)}</span>}
              {b.grade && b.grade !== "none" && <span className="qt-cap text-[10px] font-normal text-ink-3">{b.grade}</span>}
            </span>
          </Field>
          {/* No session type here (owner, 2026-11-12: "get the NQ specific stuff out of
              dashboard since we have a specific futures tab"): will New York trend or
              range is a read on NQ and ES, and it is the Futures overview's card. */}
          {/* Before the bell these are the funds' pre-market moves against SPY's (server
              dashboard.pre_market_rows, 2026-11-16), as the Sectors cards are. */}
          <Field label={d.sectors_basis === "pre" ? "Focus sectors · pre-market" : "Focus sectors"}>
            <FocusLine rows={d.plan.focus} none={d.sectors_basis === "pre" ? "No sector ahead of SPY in the pre-market" : "No sector ahead of SPY"} />
          </Field>
          <Field label={d.sectors_basis === "pre" ? "Focus themes · pre-market" : "Focus themes"}>
            <FocusLine rows={d.plan.themes} none={d.sectors_basis === "pre" ? "No theme ahead of SPY in the pre-market" : "No theme ahead of SPY"} />
          </Field>
        </div>
        <div>
          <Field label="Best setups today">
            <ul className="space-y-0.5">
              {d.plan.setups.map((s) => (
                <li key={s.key}>
                  <button
                    type="button"
                    // Breakouts' own default filters, the ones this count was made with.
                    onClick={() => toScanner(s.view, s.chip ? { "brk.chip": s.chip, "brk.cap": 2e9, "brk.vol": 5e5, "brk.rvol": 2, "brk.sector": "", "brk.theme": "" } : {})}
                    className="hit flex items-baseline gap-2 text-left text-[12.5px] text-ink-2 hover:text-ink"
                  >
                    <span aria-hidden className="text-ink-3">✓</span>
                    {s.word}
                    <span className="fig text-ink">{s.n ?? "—"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Field>
        </div>
      </div>
      <dl className="mt-auto space-y-1 border-t border-ring/60 pt-2 text-[12px]">
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Today</dt>
          <dd className="fig min-w-0 text-[11.5px] text-ink-2">{d.read.foot}</dd>
        </div>
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Reports</dt>
          <dd className="min-w-0 text-ink-2">{reports || "None on the calendar"}</dd>
        </div>
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Next</dt>
          <dd className="min-w-0 text-ink-2">{next}</dd>
        </div>
        {/* THE OPTIONS EXPIRIES (owner, 2026-11-20: "do we also mention when it's opex week?
            or what day is opex etc?"): the next OpEx and the quarter's triple witching, from
            the collector's table (lib/expiryWords). Bright on the day and in OpEx week. */}
        {expiryText && (
          <div className="flex gap-3" title={expiryTitle(nextExpiries(expiry).slice(0, 2))}>
            <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Expiry</dt>
            <dd className={cn("min-w-0", expiry?.opex_week ? "text-ink" : "text-ink-2")}>{expiryText}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}

/**
 * Breadth: advancers against decliners across every US stock at $2bn+, by the size of
 * the move. A card of its own since 2026-11-12; it was the right half of the plan's.
 */
function BreadthCard({ d }: { d: DashboardPayload }) {
  const [box, h] = useBoxHeight<HTMLDivElement>();
  return (
    <section className={cn(CARD, "flex flex-col gap-3 lg:col-span-2 2xl:col-span-1")}>
      <Head
        title="Breadth"
        sub="Advancers against decliners, by the size of the move"
        age={d.ages?.breadth}
        right={
          d.breadth ? (
            // Before the bell the count is the names that have traded pre-market, of all at
            // $2bn+: "414 stocks" alone read as if the scan had shrunk (owner, 2026-11-13).
            <span className="fig shrink-0 text-[11px] whitespace-nowrap text-ink-3">
              {d.breadth.basis === "pre" && d.breadth.of
                ? `${d.breadth.names.toLocaleString()} of ${d.breadth.of.toLocaleString()} at $2bn+ traded pre-market`
                : `${d.breadth.names.toLocaleString()} stocks at $2bn+`}
            </span>
          ) : undefined
        }
      />
      {/* THE BARS FILL WHAT HEIGHT THE ROW GIVES THEM (2026-11-19): they were a fixed 92px
          centred in a card the game plan makes 400 tall, a small chart floating in the
          middle. The chart is laid over the space, so it takes the row's height and never
          sets it: the game plan and Futures do. */}
      <div ref={box} className="relative min-h-[140px] min-w-0 flex-1">
        <div className="absolute inset-0 flex flex-col justify-end">
          {d.breadth ? (
            <BreadthBars data={d.breadth} barHeight={Math.min(240, Math.max(92, h - BREADTH_FOOT))} />
          ) : (
            <p className="py-6 text-center text-[11.5px] text-ink-3">The wide read has not landed yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

/** Below the bars: their labels, the split line and the two counts (Breadth.BreadthBars). */
const BREADTH_FOOT = 48;

/** An element's height, kept as it changes. */
function useBoxHeight<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [h, setH] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setH(Math.round(e.contentRect.height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, h];
}

function FocusLine({ rows, none }: { rows: DashboardPayload["plan"]["focus"]; none: string }) {
  if (!rows.length) return <p className="text-[12.5px] text-ink-3">{none}</p>;
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-0.5 text-[12.5px] text-ink-2">
      {rows.map((f) => (
        <span key={f.key} className="whitespace-nowrap" title={`${f.key}: ${pct(f.rs)} against SPY`}>
          {f.label} <span className={cn("fig", dir(f.pct))}>{pct(f.pct)}</span>
        </span>
      ))}
    </p>
  );
}

type Place = "above" | "below" | "inside" | null;

function pdPlace(r: DashRow): Place {
  const { pdh, pdl } = r.levels;
  if (r.last == null || pdh == null || pdl == null) return null;
  return r.last > pdh ? "above" : r.last < pdl ? "below" : "inside";
}

function pmPlace(r: DashRow): Place {
  const { pmh, pml } = r.levels;
  if (r.last == null || pmh == null || pml == null) return null;
  return r.last > pmh ? "above" : r.last < pml ? "below" : "inside";
}

const PLACE_WORD: Record<NonNullable<Place>, string> = { above: "above its high", below: "below its low", inside: "inside" };

function Dot({ at, range }: { at: Place; range: string }) {
  const say = at ? `${range}: ${PLACE_WORD[at]}` : `${range}: no range yet`;
  return <span title={say} aria-label={say} className={cn("inline-block h-[7px] w-[7px] rounded-full", at === "above" ? "bg-call-fig" : at === "below" ? "bg-put-fig" : at === "inside" ? "bg-ink-4" : "border border-ring-2")} />;
}

function Name({ r }: { r: DashRow }) {
  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <TickerLogo sym={r.sym} size={16} />
      <div className="leading-[1.25]">
        <p className="text-[12.5px] font-semibold text-ink">{r.sym}</p>
        <p className="fig text-[10.5px] text-ink-3">{num(r.last)}</p>
      </div>
    </div>
  );
}

function TopSetups({ rows, age, onAll }: { rows: DashRow[]; age?: number | null; onAll: () => void }) {
  const [chip, setChip] = usePersisted<TopChip>("dash.top", "all", oneOf("all", "long", "short", "news"));
  const ticker = useTicker();
  const shown = rows.filter(TOP_TEST[chip]);
  const counts = { all: rows.length, long: rows.filter(TOP_TEST.long).length, short: rows.filter(TOP_TEST.short).length, news: rows.filter(TOP_TEST.news).length };
  // Before the bell the list ranks how in play a name is, 0 to 100, as the Scanner's Score does.
  const inPlay = rows.some((r) => r.score.kind === "inplay");
  return (
    // `@container`: on a card under 700px (a 1920 screen with the Sidebar interface's
    // sidebar open) the table was wider than the card and the score, the one figure the
    // card is ranked by, was cut off its right edge. The small chart gives way there.
    // The Scanner list's first ten, in its order (server dashboard.build `listed`, 2026-11-19):
    // overnight that is the evening's movers and the names in play, not the MAG 7 the
    // engine holds until the pool's 06:00 mark. From 1536px it is the game plan's track.
    <section className={cn(CARD, "@container flex min-h-[260px] min-w-0 flex-col gap-2.5 xl:min-h-0")}>
      <Head title="Top setups" sub={inPlay ? "The Scanner's top ten · in play until the open" : "The Scanner's top ten"} right={<Go onClick={onAll}>Open the Scanner</Go>} age={age} />
      <div className="shrink-0">
        <Chips items={TOP_CHIPS} on={chip} set={setChip} counts={counts} />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {shown.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-ink-3">Nothing scored here right now.</p>
        ) : (
          <table className="w-full border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-10">
              <tr>
                <th scope="col" className={TH}>Ticker</th>
                <th scope="col" className={TH}>Side</th>
                <th scope="col" className={cn(TH, "text-center")} title="Against the previous day's range">PD</th>
                <th scope="col" className={cn(TH, "text-center")} title="Against the pre-market range">PM</th>
                <th scope="col" className={TH}>Setup</th>
                <th scope="col" className={TH}>Most important story</th>
                <th scope="col" className={cn(TH, "@max-[700px]:hidden")}>Chart</th>
                <th scope="col" className={cn(TH, "text-right")} title={inPlay ? "In play, 0–100: the Scanner's read until 09:30 ET, then the setup score" : "The setup score, 0–100"}>
                  Score
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={TD}><Name r={r} /></td>
                  <td className={TD}>
                    <span className={cn("rounded-[3px] border border-ring px-1.5 py-px text-[11px] whitespace-nowrap", r.score.side === "long" ? "text-call-fig" : r.score.side === "short" ? "text-put-fig" : "text-ink-3")}>
                      {r.score.side === "long" ? "▲ Long" : r.score.side === "short" ? "▼ Short" : "None"}
                    </span>
                  </td>
                  <td className={cn(TD, "text-center")}><Dot at={pdPlace(r)} range="Previous day" /></td>
                  <td className={cn(TD, "text-center")}><Dot at={pmPlace(r)} range="Pre-market" /></td>
                  <td className={cn(TD, "text-[12px] whitespace-nowrap text-ink-2")}>{setupLabel(r, true)}</td>
                  {/* The card is the game plan's width from 1536px (2026-11-19): a story
                      wraps to two lines at most rather than pushing the chart away. */}
                  <td className={TD}><CatalystCell c={r.catalyst} width={420} /></td>
                  <td className={cn(TD, "@max-[700px]:hidden")}><Spark pts={r.spark} base={r.spark_ref} w={72} h={24} /></td>
                  <td className={cn(TD, "fig text-right text-[12.5px] text-ink")}>{r.score.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

/*
 * HIGH IMPACT NEWS (owner, 2026-11-19: "a High Impact News card or something named similar, tha
 * tlists things like important headlines, geopolitcs, IPO's earnigns ofr the day etc"; the mock
 * on the real page approved: "the dashboard mock is good"). What can move the whole market
 * today, composed by the server (impact.py) from the collector's own data, no model:
 *  - TODAY, in time order, one line each: the US prints that matter with the figure against
 *    what was expected, the Fed's speakers, the big reports before and after, an IPO the
 *    headlines are full of, the night's big foreign print;
 *  - HEADLINES: the wire's high-impact stories of the last twelve hours, then geopolitics,
 *    energy and policy of the last six, one a story, newest first.
 * Stock news beside it is the names' own stories; this card is the market's.
 */
function HighImpact({ d, age, onWire }: { d: DashImpact | undefined; age?: number | null; onWire: () => void }) {
  const today = d?.today ?? [];
  const heads = d?.heads ?? [];
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2 xl:min-h-0")}>
      <Head
        title={
          <span className="flex items-center gap-2">
            High impact news
            {d?.live && (
              <span className="qt-cap flex items-center gap-1 text-[9.5px] font-normal text-ink-3">
                <span aria-hidden className="h-[5px] w-[5px] rounded-full bg-call" />
                live
              </span>
            )}
          </span>
        }
        sub="What can move the whole market today: the day's prints, reports and listings, then the headlines"
        right={<Go onClick={onWire}>Open the wire</Go>}
        age={age}
      />
      {d == null ? (
        <p className="py-8 text-center text-[12px] text-ink-3">Reading the wire and the calendar…</p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto pr-1">
          <p className="qt-cap mt-1 mb-0.5 text-[10px] text-ink-3">Today</p>
          {today.length === 0 ? (
            <p className="py-2 text-[12px] text-ink-3">Nothing scheduled in the US today.</p>
          ) : (
            <ul>
              {today.map((r) => (
                <li
                  key={`${r.t}-${r.kind}-${r.line}`}
                  className="grid grid-cols-[52px_70px_minmax(0,1fr)] items-baseline gap-x-2 border-b border-ring/60 py-[5px] last:border-b-0"
                >
                  <span className="fig text-[11.5px] text-ink-3">{r.t}</span>
                  <span className={cn("text-[11.5px] font-semibold", r.done ? "text-ink" : "text-ink-2")}>{r.kind}</span>
                  {r.url ? (
                    <a href={r.url} target="_blank" rel="noreferrer noopener" title={r.line} className="hit truncate text-[12px] text-ink-2 hover:text-ink">
                      {r.line}
                    </a>
                  ) : (
                    <span title={r.line} className={cn("truncate text-[12px]", r.done ? "text-ink-2" : "text-ink-3")}>
                      {r.line}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="qt-cap mt-3 mb-0.5 text-[10px] text-ink-3">Headlines</p>
          {heads.length === 0 ? (
            <p className="py-2 text-[12px] text-ink-3">No high-impact headlines in the last twelve hours.</p>
          ) : (
            <ul>
              {heads.map((h) => (
                <li key={`${h.t}-${h.title}`} className="border-b border-ring/60 py-2 last:border-b-0">
                  <p className="text-[11.5px]">
                    <span className={cn("font-semibold", h.high ? "text-ink" : "text-ink-2")}>{h.kind}</span>
                    {h.high && <span className="text-ink-3"> · high impact</span>}
                  </p>
                  {h.url ? (
                    <a href={h.url} target="_blank" rel="noreferrer noopener" className="hit mt-0.5 line-clamp-2 text-[12px] leading-[1.35] text-ink-2 hover:text-ink">
                      {h.title}
                    </a>
                  ) : (
                    <p className="mt-0.5 line-clamp-2 text-[12px] leading-[1.35] text-ink-2">{h.title}</p>
                  )}
                  <p className="fig mt-0.5 text-[10.5px] text-ink-3">
                    {ageWord(h.age_min)} ago{h.publisher ? ` · ${h.publisher}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function StockNews({ stories, live, age }: { stories: DashStory[]; live: boolean; age?: number | null }) {
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2 xl:min-h-0")}>
      <Head
        title={
          <span className="flex items-center gap-2">
            Stock news
            {live && (
              <span className="qt-cap flex items-center gap-1 text-[9.5px] font-normal text-ink-3">
                <span aria-hidden className="h-[5px] w-[5px] rounded-full bg-call" />
                live
              </span>
            )}
          </span>
        }
        sub="Major stories, newest first"
        age={age}
      />
      <ul className="min-h-0 flex-1 overflow-auto pr-1">
        {stories.length === 0 && <li className="py-8 text-center text-[12px] text-ink-3">No major stories in the last thirty hours.</li>}
        {stories.map((s) => (
          <li key={`${s.syms.join()}-${s.title}`} className="border-b border-ring/60 py-2 last:border-b-0">
            <p className="text-[11.5px]">
              {s.syms.map((x, i) => (
                <span key={x}>
                  {i > 0 && <span className="text-ink-3">, </span>}
                  <button type="button" onClick={() => openTicker(x)} className="hit fig font-semibold text-ink">
                    {x}
                  </button>
                </span>
              ))}
              <span className="text-ink-3"> · {s.tag}</span>
            </p>
            <a href={s.url} target="_blank" rel="noreferrer noopener" className="hit mt-0.5 line-clamp-2 text-[12px] leading-[1.35] text-ink-2 hover:text-ink">
              {s.title}
            </a>
            <p className="fig mt-0.5 text-[10.5px] text-ink-3">
              {ageWord(s.age_min)} ago · {s.provider}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Rotation({ d, onHeat, onSector }: { d: DashboardPayload; onHeat: () => void; onSector: (key: string) => void }) {
  const max = heatMax(d.rotation.map((s) => s.day_pct));
  return (
    <section className={cn(CARD, "shrink-0")}>
      <Head
        title="Sector rotation"
        sub={
          d.sectors_basis === "pre"
            ? "Where money is moving before the bell: each fund's pre-market move, and the stocks pushing each sector"
            : "Where money is moving, and the stocks pushing each sector"
        }
        right={<Go onClick={onHeat}>View heat map</Go>}
        age={d.ages?.rotation}
      />
      <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 min-[106.25rem]:grid-cols-11">
        {d.rotation.map((s) => (
          <button key={s.key} type="button" onClick={() => onSector(s.key)} title={`Open ${s.label} on the heat map`} style={heatStyle(s.day_pct, max)} className="hit min-w-0 rounded-[4px] border border-ring px-2.5 py-2 text-left">
            <p className="flex min-w-0 items-center gap-1.5 text-[12px] font-semibold text-ink">
              <SectorGlyph fund={s.key} size={13} className="block shrink-0 text-ink-3" />
              <span className="truncate">{s.label}</span>
            </p>
            <p className="flex items-baseline justify-between gap-1">
              <span className="fig text-[10.5px] text-ink-3">{s.key}</span>
              <span className={cn("fig text-[12px]", dir(s.day_pct))}>{pct(s.day_pct)}</span>
            </p>
            <p className="qt-cap mt-1.5 text-[9px] text-ink-3">Leaders</p>
            <p className="fig truncate text-[11px] text-ink-2">{s.leaders.length ? s.leaders.join(" · ") : "—"}</p>
          </button>
        ))}
      </div>
    </section>
  );
}
