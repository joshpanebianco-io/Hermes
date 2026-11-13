"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { setAskFocus } from "@/lib/ask/open";
import type { CalendarRow } from "@/types/terminal";
import type { DashInPlay, DashInPlayRow, DashRow, DashStory, DashboardPayload } from "@/types/dashboard";
import { BreadthBars } from "@/components/panels/Breadth";
import { setupLabel } from "@/components/panels/ScanDetail";
import { CARD, CatalystCell, Chips, Spark, TD, TH, Tag, TrackButton, ageWord, dayName, rowProps } from "@/components/panels/ScanWide";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { SectorGlyph } from "@/components/ui/SectorGlyph";
import { scoreText } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { dir, inMin, num, pct } from "@/lib/format";
import { heatMax, heatStyle } from "@/lib/heat";
import { etDay, useNextPrint } from "@/lib/nextPrint";
import type { ScanView, Tab } from "@/lib/tabs";
import { openTicker, useTicker } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";
import { oneOf, persist, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

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
  { key: "news", label: "Has news" },
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
}: {
  calendar: CalendarRow[];
  onOpen: (t: Tab) => void;
  onScan: (v: ScanView) => void;
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
  const [data, setData] = useState<DashboardPayload | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/dashboard", { cache: "no-store" });
      const d = (await r.json()) as DashboardPayload;
      if (mine === seq.current) setData(d);
    } catch {
      /* the last read stays on screen */
    }
  }, []);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);

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
      <div className="grid shrink-0 gap-3 lum:gap-[var(--lum-gap)] lg:grid-cols-2 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
        <ReadCard d={data} later={later} now={now} prices={prices} />
        <PlanCard d={data} onWire={() => onOpen("terminal")} toScanner={toScanner} />
        <BreadthCard d={data} />
      </div>
      <div className="grid gap-3 lum:gap-[var(--lum-gap)] xl:min-h-[320px] xl:flex-1 xl:grid-cols-[minmax(0,5fr)_minmax(0,3.7fr)_minmax(0,3.6fr)] xl:grid-rows-[minmax(0,1fr)]">
        {/* The table, on the whole list: the Stocks tab's charts are a choice of their own. */}
        <TopSetups rows={data.top} onAll={() => toScanner("today", { "today.side": "all" })} />
        <InPlay d={data.inplay} onAll={() => toScanner("extended")} />
        <StockNews stories={data.stories} live={data.news_live} />
      </div>
      <Rotation d={data} onHeat={() => toSectors()} onSector={(k) => toSectors({ "sec.mode": "cards", "sec.sel": k })} />
    </main>
  );
}

/* -------------------------------------------------------------------------- */
/* The pieces                                                                  */
/* -------------------------------------------------------------------------- */

function Head({ title, sub, right }: { title: React.ReactNode; sub?: string; right?: React.ReactNode }) {
  return (
    <div className="flex shrink-0 items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-[11.5px] text-ink-3">{sub}</p>}
      </div>
      {right}
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

function ReadCard({ d, later, now, prices }: { d: DashboardPayload; later: CalendarRow | null; now: number | null; prices?: React.ReactNode }) {
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
  return (
    <section className={cn(CARD, "flex flex-col gap-2.5")}>
      <Head title={d.read.title} sub={`Levels for ${dayName(d.trading_day)}`} />
      {/* SPY, QQQ, IWM and VIX: what the sentences under them are about, ruled off as
          the card's own figures. The edges run to the card's (its 16px of padding). */}
      {prices && (
        <div aria-label="Prices" className="-mx-4 border-y border-ring/60 px-4 py-2.5">
          {prices}
        </div>
      )}
      <div className="space-y-1.5 text-[13px] leading-[1.45] text-ink-2">
        {d.read.lines.map((l) => (
          <p key={l}>{l}</p>
        ))}
      </div>
      <p className="fig text-[11px] text-ink-3">{d.read.foot}</p>
      <dl className="mt-auto space-y-1 border-t border-ring/60 pt-2 text-[12px]">
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Reports</dt>
          <dd className="min-w-0 text-ink-2">{reports || "None on the calendar"}</dd>
        </div>
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Next</dt>
          <dd className="min-w-0 text-ink-2">{next}</dd>
        </div>
      </dl>
    </section>
  );
}

function PlanCard({ d, onWire, toScanner }: { d: DashboardPayload; onWire: () => void; toScanner: (view: ScanView, also?: Record<string, unknown>) => void }) {
  const b = d.plan.bias;
  const hue = b.side === "long" ? "text-call-fig" : b.side === "short" ? "text-put-fig" : "text-ink-3";
  const tip = b.live != null && b.total != null ? `${b.live} of ${b.total} reads live${b.cap != null ? ` · plans capped at ${b.cap}` : ""}` : undefined;
  return (
    <section className={cn(CARD, "flex flex-col gap-3")}>
      <Head
        title="Today's game plan"
        sub="Playbook for the session"
        right={
          <span className="flex shrink-0 items-center gap-4">
            {/* The written plan, name by name: the Analysis tab's stocks half until
                2026-11-11, now the Scanner's last view and one click from here. */}
            <Go onClick={() => toScanner("plan")}>Written plan</Go>
            <Go onClick={onWire}>Open the wire</Go>
          </span>
        }
      />
      {/* Two short columns, so the card is as tall as the read beside it and not taller.
          The counts' column is as wide as its longest line, which then never wraps; the
          sectors and themes take the rest and wrap as they need to. */}
      <div className="grid flex-1 content-start gap-x-8 gap-y-2.5 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="space-y-2.5">
          <Field label="Market bias">
            <span title={tip} className={cn("inline-flex items-baseline gap-1.5 rounded-[3px] border border-ring-2 px-2 py-0.5 text-[13px] font-semibold", hue)}>
              {b.side === "long" ? "▲ Long" : b.side === "short" ? "▼ Short" : "– No lean"}
              {b.thin && b.live != null && b.total != null ? (
                // A thin read: the count, where a bare "+100" would read as the tape agreeing.
                <span className="fig text-[11.5px] font-normal text-ink-3">
                  {b.live} of {b.total} reads
                </span>
              ) : (
                b.score != null && <span className="fig">{scoreText(b.score)}</span>
              )}
              {b.grade && b.grade !== "none" && <span className="qt-cap text-[10px] font-normal text-ink-3">{b.grade}</span>}
            </span>
          </Field>
          {/* No session type here (owner, 2026-11-12: "get the NQ specific stuff out of
              dashboard since we have a specific futures tab"): will New York trend or
              range is a read on NQ and ES, and it is the Futures overview's card. */}
          <Field label="Focus sectors">
            <FocusLine rows={d.plan.focus} none="No sector ahead of SPY" />
          </Field>
          <Field label="Focus themes">
            <FocusLine rows={d.plan.themes} none="No theme ahead of SPY" />
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
    </section>
  );
}

/**
 * Breadth: advancers against decliners across every US stock at $2bn+, by the size of
 * the move. A card of its own since 2026-11-12; it was the right half of the plan's.
 */
function BreadthCard({ d }: { d: DashboardPayload }) {
  return (
    <section className={cn(CARD, "flex flex-col gap-3 lg:col-span-2 2xl:col-span-1")}>
      <Head
        title="Breadth"
        sub="Advancers against decliners, by the size of the move"
        right={d.breadth ? <span className="fig shrink-0 text-[11px] whitespace-nowrap text-ink-3">{d.breadth.names.toLocaleString()} stocks at $2bn+</span> : undefined}
      />
      {/* Centred in whatever height the row gives it: the bars are a fixed 92px tall. */}
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        {d.breadth ? <BreadthBars data={d.breadth} /> : <p className="py-6 text-center text-[11.5px] text-ink-3">The wide read has not landed yet.</p>}
      </div>
    </section>
  );
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

function TopSetups({ rows, onAll }: { rows: DashRow[]; onAll: () => void }) {
  const [chip, setChip] = usePersisted<TopChip>("dash.top", "all", oneOf("all", "long", "short", "news"));
  const ticker = useTicker();
  const shown = rows.filter(TOP_TEST[chip]);
  const counts = { all: rows.length, long: rows.filter(TOP_TEST.long).length, short: rows.filter(TOP_TEST.short).length, news: rows.filter(TOP_TEST.news).length };
  return (
    // `@container`: on a card under 700px (a 1920 screen with the Sidebar interface's
    // sidebar open) the table was wider than the card and the score, the one figure the
    // card is ranked by, was cut off its right edge. The small chart gives way there.
    <section className={cn(CARD, "@container flex min-h-[260px] min-w-0 flex-col gap-2.5 xl:min-h-0")}>
      <Head title="Top setups" sub="The scanner's own rank" right={<Go onClick={onAll}>Open the Today list</Go>} />
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
                <th scope="col" className={cn(TH, "text-right")}>Score</th>
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
                  <td className={TD}><CatalystCell c={r.catalyst} width={360} /></td>
                  <td className={cn(TD, "@max-[700px]:hidden")}><Spark pts={r.spark} w={72} h={24} /></td>
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

/**
 * In play — the pool's rank across the whole market, where My list stood (owner,
 * 2026-11-10: "lets remove 'my list' and replace it with something else that's
 * useful"). The pinned list was the same names every day; this is who is moving on
 * volume and news right now, why (sources/pool.in_play's own words), and what the
 * engine has done about it: taken at a mark, pinned, on the list, or one Track away.
 * Before the bell it reads the pre-market; after it, the day's move and volume.
 */
function InPlay({ d, onAll }: { d: DashInPlay | null; onAll: () => void }) {
  const ticker = useTicker();
  const rows = d?.rows ?? [];
  const sub = d
    ? [
        d.qualified != null ? `${d.qualified} qualify` : null,
        d.promoted ? `${d.promoted} promoted${d.marks_done.length ? ` at ${d.marks_done[d.marks_done.length - 1]}` : ""}` : null,
        d.next_mark ? `next mark ${d.next_mark} ET` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "the pool's rank across the market";
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2.5 xl:min-h-0")}>
      <Head title="In play" sub={sub} right={<Go onClick={onAll}>View Extended hours</Go>} />
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-ink-3">{d ? "Nothing over the pool's bar right now." : "The pool has not been read yet — it reads from 04:00 ET."}</p>
        ) : (
          <table className="w-full border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-10">
              <tr>
                <th scope="col" className={TH}>Ticker</th>
                <th
                  scope="col"
                  className={cn(TH, "text-right")}
                  title="The pool's in-play score: the gap in the name's own ATRs, pre-market volume against an average day, a report, a fresh story, a level already taken, a Day 2 or 3. Nothing under 4 is promoted."
                >
                  In play
                </th>
                <th scope="col" className={TH}>Why</th>
                <th scope="col" className={TH} title="What the engine has done with the name today">Engine</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={TD}>
                    <div className="flex items-center gap-2">
                      <TickerLogo sym={r.sym} size={18} />
                      <div className="min-w-0 leading-[1.2]">
                        <p className="text-[12.5px] font-semibold text-ink" title={r.name ?? undefined}>{r.sym}</p>
                        <p className="fig text-[10.5px] text-ink-3">{r.last != null ? num(r.last, 2) : "—"}</p>
                      </div>
                    </div>
                  </td>
                  <td className={cn(TD, "text-right whitespace-nowrap")}>
                    <span className="fig text-[12.5px] text-ink">{r.score.toFixed(1)}</span>
                    <span aria-hidden className="ml-2 inline-block h-[4px] w-[36px] rounded-[1px] bg-ring align-middle">
                      <span className="block h-full rounded-[1px] bg-ink-3" style={{ width: `${Math.max(4, Math.min(100, (r.score / (d?.score_max ?? 32)) * 100))}%` }} />
                    </span>
                  </td>
                  <td className={cn(TD, "max-w-[260px] text-[11px] leading-snug text-ink-2")}>{r.reason}</td>
                  <td className={cn(TD, "whitespace-nowrap")}>
                    <Engine v={r.verdict} sym={r.sym} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

/** The engine's verdict on an In play row, as the wide tables' tags say it; Track where it is one click away. */
function Engine({ v, sym }: { v: DashInPlayRow["verdict"]; sym: string }) {
  if (!v) return <span className="text-ink-4">—</span>;
  if (v.state === "promoted") return <Tag tone="warn" title={`On today's list from the pool at ${v.mark} ET — the engine scores it at the open`}>Pool {v.mark}</Tag>;
  if (v.state === "pinned") return <Tag tone="flat" title="Pinned: always on the list">Pinned</Tag>;
  if (v.state === "hand" || v.state === "tracked") return <Tag tone="flat" title="On today's list">On the list</Tag>;
  if (v.state === "inplay")
    return (
      <span onClick={(e) => e.stopPropagation()}>
        <TrackButton sym={sym} tracked={false} />
      </span>
    );
  return <span className="text-ink-4" title="Under the pool's bar">—</span>;
}

function StockNews({ stories, live }: { stories: DashStory[]; live: boolean }) {
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
      <Head title="Sector rotation" sub="Where money is moving, and the stocks pushing each sector" right={<Go onClick={onHeat}>View heat map</Go>} />
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
