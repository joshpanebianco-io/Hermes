"use client";

import type { OptContract, OptionsCtx, ScanRow, ScanSession, Side } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { HelmInline } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { levelGlyph, setupLabel, sideHue } from "@/components/panels/ScanDetail";
import {
  CatalystCell,
  Head,
  RangeCell,
  RvolBar,
  ScoreBar as ScoreTier,
  Spark,
  TickerCell,
  VolPct,
  gapOf,
  pctText,
  rowTags,
} from "@/components/panels/ScanWide";
import { compact, dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { useOptionsPrefs } from "@/lib/optionsPrefs";
import { togglePin } from "@/lib/ticker";

/**
 * The scanner's table, in two column sets.
 *
 * RANKED CARRIES EVERY COLUMN THE PINE'S SCANNER DOES (owner instruction,
 * 2026-10-13: "make sure it includes what the tradingview script scanner
 * includes too") — Price, Volume, % Change, Pre/Post %, RS vs SPY, PDH /
 * PDL / PMH / PML Break and Trend, under the script's own names, the break
 * columns drawn as its ten-segment bars — with the engine's score, setup and
 * entry in front of them, because those are what rank the list.
 *
 * OPTIONS is the same names read as the options trader reads them: implied
 * against realised volatility, the move the straddle prices, skew, liquidity,
 * an earnings date inside the expiry, and the suggested contract with what it
 * puts at risk.
 *
 * OVERVIEW IS THE ONE IT OPENS ON (owner, 2026-11-09: "i like how it is a bit more
 * streamlined"), in the screenshots' order since 2026-11-10: the name with its tags,
 * the story, the move, the two ranges in words, the day's line, the volume, then the
 * setup and the score the list is ranked on. Ranked keeps every column the Pine has.
 *
 * IMPLIED AGAINST REALISED IS ON THE OPTIONS COLUMNS ALONE (owner, 2026-11-11: "is iv
 * vs realised column worth having as a column?"). Overview closed on it and Ranked
 * carried it as "Options". Measured that morning it read the market's last month and
 * the report date, not the name: 30 of 40 rows said "cheap", SPY, QQQ and IWM among
 * them, where three weeks before most said "rich"; and it sets a 30-day figure against
 * a contract that runs zero to two days. Only the two cells went. The figure is
 * computed as before, still settles long against spread when R cannot
 * (optcalc.structure_pick), and shows on the Options columns and in the slide-out.
 *
 * THE TICKER STAYS PUT. Rank and ticker are pinned to the left edge, so on a
 * narrow screen the table scrolls sideways under them rather than losing which
 * row is which.
 */

export type ColSet = "overview" | "ranked" | "options";
export type SortKey = "score" | "rs" | "rvol" | "chg" | "gap" | "ext" | "vol" | "trend" | "ivrv" | "em";
type Bench = "SPY" | "QQQ";
type Session = ScanSession;

/* -------------------------------------------------------------------------- */

export function ScanTable({
  rows,
  cols,
  bench,
  sort,
  onSort,
  now,
  selected,
  onPick,
  budget,
  pinned,
  onPinned,
  session,
}: {
  rows: ScanRow[];
  cols: ColSet;
  bench: Bench;
  /** The scanner's session, for what a column means before the bell and after it. */
  session: Session;
  sort: SortKey;
  onSort: (k: SortKey) => void;
  now: number | null;
  selected: string | null;
  onPick: (sym: string) => void;
  budget: number | null;
  /** The owner's list, for each row's star. */
  pinned: ReadonlySet<string>;
  onPinned: () => void;
}) {
  const th = { cur: sort, onSort };
  // Before the bell (and overnight) the regular change is the last session's own, and no
  // time-of-day volume exists yet: two columns say what they hold instead.
  const before = session === "pre" || session === "closed";
  return (
    <table className="w-full min-w-[1340px] border-separate border-spacing-0 text-left">
      {/* One row of column names. A band of group names sat over it (News, Move, Levels,
          Chart, Volume, Setup, Options, each with a coloured rule) until the owner asked
          for it to go on 2026-11-11; every column still says what it is. */}
      <thead className="sticky top-0 z-20">
        <tr>
          {cols === "overview" ? (
            <>
              <Th pin={0} className="w-[250px]">
                <Head label="Ticker" hint="symbol · price" />
              </Th>
              <Th title="The most important story of the last day, not the newest">
                <Head label="News" hint="most important first" />
              </Th>
              <Th
                k="rs"
                {...th}
                right
                title={`Relative strength vs ${bench}: the move since the previous close in this name's own daily ATRs, less ${bench}'s in its own. Up to a quarter of the score, and what the Pine's scanner sorts by.`}
              >
                <Head label="RS" hint={`vs ${bench}`} right />
              </Th>
              <Th
                k="rvol"
                {...th}
                title={
                  before
                    ? "No time-of-day figure exists before the bell, so this is the pre-market's volume as a share of an average day: the figure the pre-open rank reads, from 0.25% to 4%. Relative volume starts at the open."
                    : "Regular-session volume to now against the same time of day on the ten prior sessions"
                }
              >
                <Head label="RVol" hint={before ? "pre-mkt · % of ADV" : "vs usual"} />
              </Th>
              <Th
                k="chg"
                {...th}
                right
                title={
                  before
                    ? "The last regular session's change, as the Pine prints it before the open; under it, where the pre-market or the after-hours stands against that session's close"
                    : "The regular session against the previous close; after the bell, the after-hours move under it"
                }
              >
                <Head label="Chg" hint={before ? "last session" : "vs prev close"} right />
              </Th>
              <Th k="gap" {...th} right title={GAP_TIP}>
                <Head label="Gap" hint="open vs prev close" right />
              </Th>
              <Th>
                <Head label="PM range" hint="locks at 09:30" />
              </Th>
              <Th>
                <Head label="PD range" hint="vs PDH / PDL" />
              </Th>
              <Th>
                <Head label="Spark" hint="today" />
              </Th>
              <Th k="vol" {...th} title="Today's volume, and its share of an average day">
                <Head label="Volume" hint="vs ADV" />
              </Th>
              <Th title="Where the trade is right now, the entry, and today's latest signal">
                <Head label="Setup" hint="entry · latest signal" />
              </Th>
              <Th k="score" {...th} className="w-[104px]">
                <Head label="Score" hint="setup, 0–100" />
              </Th>
            </>
          ) : cols === "ranked" ? (
            <>
              <Th pin={0} className="w-[34px] text-right">
                #
              </Th>
              <Th pin={34} className="w-[142px]">
                Ticker
              </Th>
              <Th k="score" {...th} className="w-[72px]">
                Score
              </Th>
              <Th title="Where the trade is right now: the level to retest, or VWAP / the 8 EMA when price has run too far from it — and today's latest signal">
                Setup
              </Th>
              <Th right title="The entry reference, and how far price is from it in ten-minute ATRs">
                Entry
              </Th>
              <Th right>Price</Th>
              <Th k="vol" {...th} right title="Today's volume, regular session and post-market. Yahoo's pre-market bars carry none, so it reads — before the open.">
                Volume
              </Th>
              <Th k="chg" {...th} right title="Regular session vs the previous close — before the open, still the previous session's move (as the Pine prints it)">
                % Change
              </Th>
              <Th k="gap" {...th} right title={GAP_TIP}>
                Gap
              </Th>
              <Th k="ext" {...th} right title="Pre-market vs the previous close, or post-market vs today's close">
                <Two a="Pre/Post" b="%" />
              </Th>
              <Th k="rs" {...th} right title={`Relative strength vs ${bench}: today's move in this name's daily ATRs, minus ${bench}'s in its own`}>
                <Two a="RS vs" b={bench} />
              </Th>
              <Th k="rvol" {...th} right title="Regular-session volume to now against the same time of day on the prior sessions. Starts at the open.">
                RVol
              </Th>
              <Th center title="How far price has travelled from the previous-day low toward the high; a filled square once broken">
                <Two a="PDH" b="Break" />
              </Th>
              <Th center title="How far price has travelled from the previous-day high toward the low">
                <Two a="PDL" b="Break" />
              </Th>
              <Th center title="Toward the pre-market high — dots while the pre-market range is still forming">
                <Two a="PMH" b="Break" />
              </Th>
              <Th center title="Toward the pre-market low">
                <Two a="PML" b="Break" />
              </Th>
              <Th k="trend" {...th} center title="▲ above PDH and PMH · ▼ below PDL and PML · ⚠ inside the levels — the Pine's trend column">
                Trend
              </Th>
              <Th center title="▲ above · ▼ below the 200 EMA on ten-minute bars — the side filter: longs above it, shorts below, a retest into it tends to fail">
                200
              </Th>
              <Th>Catalysts</Th>
            </>
          ) : (
            <>
              <Th pin={0} className="w-[34px] text-right">
                #
              </Th>
              <Th pin={34} className="w-[142px]">
                Ticker
              </Th>
              <Th k="score" {...th} className="w-[72px]">
                Score
              </Th>
              <Th right>Price</Th>
              <Th right title="Cboe's 30-day implied volatility">
                IV30
              </Th>
              <Th right title="Annualised close-to-close volatility over the last 20 sessions">
                RV20
              </Th>
              <Th k="ivrv" {...th} right title="IV30 ÷ RV20 — under 0.90 premium is cheap, over 1.25 rich">
                IV / RV
              </Th>
              <Th right title="Where IV30 sits in its own logged range — builds as the days are logged">
                IV rank
              </Th>
              <Th k="em" {...th} right title="The move the front expiry's at-the-money straddle prices, from the mid">
                Exp. move
              </Th>
              <Th right title="The same from the nearest expiry with two trading days or more to run">
                Weekly
              </Th>
              <Th right title="25-delta put IV minus 25-delta call IV on the weekly — how much more downside protection costs than upside">
                Skew
              </Th>
              <Th title="At-the-money spread as a share of the mid, with open interest">Liquidity</Th>
              <Th title="Today's put volume over call volume across the expiries read, and which way it leans">Flow</Th>
              <Th title="The suggested contract for the setup's side: the strike nearest 0.60 delta">Contract</Th>
              <Th right title="Premium at risk per contract to the stock-level stop: the stop distance × delta × 100 — in the session, off the contract's estimate at the live stock price">
                Risk / ct
              </Th>
              {budget != null && (
                <Th right title={`How many contracts $${budget} of premium risk buys`}>
                  Size
                </Th>
              )}
            </>
          )}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <Row
            key={r.sym}
            r={r}
            rank={i + 1}
            cols={cols}
            bench={bench}
            session={session}
            now={now}
            on={selected === r.sym}
            budget={budget}
            pinned={pinned.has(r.sym)}
            onPinned={onPinned}
            onPick={() => onPick(r.sym)}
          />
        ))}
      </tbody>
    </table>
  );
}

/* -------------------------------------------------------------------------- */

function Th({
  children,
  className,
  title,
  k,
  cur,
  onSort,
  right,
  center,
  pin,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
  k?: SortKey;
  cur?: SortKey;
  onSort?: (k: SortKey) => void;
  right?: boolean;
  center?: boolean;
  /** Pinned to the left edge at this offset (px). */
  pin?: number;
}) {
  const on = k != null && k === cur;
  return (
    <th
      scope="col"
      title={title}
      aria-sort={on ? "descending" : undefined}
      className={cn(
        "qt-cap border-b border-ring bg-bg px-1.5 py-2 align-bottom text-[10.5px] font-semibold whitespace-nowrap text-ink-3",
        right && "text-right",
        center && "text-center",
        pin != null && "sticky z-30",
        className,
      )}
      style={pin != null ? { left: pin } : undefined}
    >
      {k && onSort ? (
        <button
          type="button"
          onClick={() => onSort(k)}
          className={cn("qt-cap text-[10.5px] hover:text-ink-2", on ? "text-ink" : "text-ink-3")}
        >
          {children}
          {on ? " ↓" : ""}
        </button>
      ) : (
        children
      )}
    </th>
  );
}

const TD = "border-b border-ring/60 px-1.5 py-2";

/**
 * A header on two lines — the Pine's own title kept whole ("PDH Break"), at
 * the width of the ten-segment bar under it rather than of the words. On one
 * line the four break columns alone were 80px wider than their bars, and at
 * 1920 that pushed Catalysts out of the pane.
 */
function Two({ a, b }: { a: string; b: string }) {
  return (
    <span className="inline-flex flex-col leading-[1.2]">
      <span>{a}</span>
      <span>{b}</span>
    </span>
  );
}

function Row({
  r,
  rank,
  cols,
  bench,
  session,
  now,
  on,
  budget,
  pinned,
  onPinned,
  onPick,
}: {
  r: ScanRow;
  rank: number;
  cols: ColSet;
  bench: Bench;
  session: Session;
  now: number | null;
  on: boolean;
  budget: number | null;
  pinned: boolean;
  onPinned: () => void;
  onPick: () => void;
}) {
  const side = r.score.side;
  // Pinned cells need their own ground, or the scrolled columns show through.
  const pinBg = on ? "bg-surface-2" : "bg-bg group-hover:bg-surface";
  const lead = (
    <>
      <td className={cn(TD, "fig sticky left-0 z-10 w-[34px] text-right text-[11px] text-ink-3", pinBg)}>{rank}</td>
      <td className={cn(TD, "sticky z-10 w-[142px]", pinBg)} style={{ left: 34 }}>
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          <button
            type="button"
            aria-pressed={pinned}
            title={pinned ? "Pinned: always on the list. Click to unpin." : "Pin: keep this name on the list for good"}
            onClick={(e) => {
              e.stopPropagation();
              void togglePin(r.sym).then(onPinned);
            }}
            className="text-[12px] leading-none text-ink-3 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            {pinned ? "★" : "☆"}
          </button>
          <span className={cn("w-[10px] text-[11px]", side ? sideHue(side) : "text-ink-3")}>
            {side === "long" ? "▲" : side === "short" ? "▼" : "·"}
          </span>
          <TickerLogo sym={r.sym} size={16} />
          <span className="text-[13px] font-semibold text-ink" title={r.name ?? undefined}>
            {r.sym}
          </span>
          {r.sector && <span className="qt-cap text-[9.5px] text-ink-3">{r.sector}</span>}
          {r.promoted && (
            <span
              className="qt-cap text-[9.5px] text-flip-fig"
              title={`From the pool at ${r.promoted.mark} ET — ${r.promoted.reason}`}
            >
              pool
            </span>
          )}
          {(r.stage ?? 0) >= 2 && (
            <span className="qt-cap text-[9.5px] text-ink-2" title={`Day ${r.stage} of a multi-day move`}>
              day {r.stage}
            </span>
          )}
        </div>
      </td>
    </>
  );
  const handlers = {
    "data-sym": r.sym,
    tabIndex: 0,
    onClick: onPick,
    onKeyDown: (e: React.KeyboardEvent) => {
      // Enter on a row that has the focus opens it. The arrows walking the list went
      // with the other keyboard controls (owner, 2026-11-11).
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onPick();
      }
    },
    "aria-selected": on,
    className: cn(
      "group hit cursor-pointer outline-none focus-visible:bg-surface-2 focus-visible:shadow-[inset_2px_0_0_var(--ink-2)]",
      on && "bg-surface-2",
    ),
  } as const;

  if (!r.ok) {
    return (
      <tr {...handlers}>
        {lead}
        <td colSpan={19} className={cn(TD, "text-[11.5px] text-ink-3")}>
          {r.error ?? "no data yet"}
        </td>
      </tr>
    );
  }

  if (cols === "options") return <OptionsRow r={r} lead={lead} handlers={handlers} budget={budget} />;
  if (cols === "overview") return <OverviewRow r={r} bench={bench} session={session} pinBg={pinBg} pinned={pinned} onPinned={onPinned} handlers={handlers} now={now} />;

  const rs = r.rs[bench];
  const entry = r.setup.entry;
  const last = lastSignal(r, now);
  return (
    <tr {...handlers}>
      {lead}
      <td className={TD}>
        <ScoreBar v={r.score.total} record={r.record} />
      </td>
      <td className={cn(TD, "text-[12px] whitespace-nowrap")}>
        <span className={setupHue(r)}>{setupLabel(r)}</span>
        {last && (
          <span
            className={cn("fig ml-2 text-[11px]", last.fresh ? cn("font-semibold", sideHue(last.side)) : "text-ink-3")}
            title={last.fresh ? "Fired in the last 30 minutes" : "Today's latest signal"}
          >
            {last.text}
          </span>
        )}
      </td>
      <td className={cn(TD, "text-right whitespace-nowrap")}>
        {entry ? (
          <span className="fig text-[12px] text-ink-2" title={`${entry.kind} ${num(entry.price)} · price ${entry.dist_atr.toFixed(2)} ATR from it`}>
            <span className="qt-cap mr-1 text-[9.5px] text-ink-3">{entry.kind === "EMA8" ? "8 EMA" : entry.kind}</span>
            {num(entry.price)}
            <span className="ml-1.5 text-[10.5px] text-ink-3">
              {entry.dist_atr >= 0 ? "+" : ""}
              {entry.dist_atr.toFixed(1)}
            </span>
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "text-right")}>
        <Tick value={num(r.last)} className="fig text-[12.5px] text-ink" />
      </td>
      <td className={cn(TD, "text-right whitespace-nowrap")}>
        {r.volume != null ? (
          <span className="fig text-[12px] text-ink-2">{compact(r.volume)}</span>
        ) : r.premkt?.volume != null ? (
          // Before the open: Nasdaq's pre-market tally, against a normal day.
          <span
            className="fig text-[12px] text-ink-2"
            title={`Pre-market volume${r.premkt.pct_adv != null ? ` — ${r.premkt.pct_adv.toFixed(1)}% of the thirty-session average day` : ""} (Nasdaq, about fifteen minutes delayed)`}
          >
            <span className="qt-cap mr-1 text-[9px] text-ink-3">PM</span>
            {compact(r.premkt.volume)}
            {r.premkt.pct_adv != null && (
              <span className={cn("ml-1 text-[10.5px]", r.premkt.pct_adv >= 5 ? "text-ink" : "text-ink-3")}>
                {r.premkt.pct_adv.toFixed(1)}%
              </span>
            )}
          </span>
        ) : (
          <Dash title="No volume before the open yet" />
        )}
      </td>
      <td className={cn(TD, "text-right")}>
        <Tick value={pct(r.chg_pct)} className={cn("fig text-[12px]", dir(r.chg_pct))} />
      </td>
      <td className={cn(TD, "text-right")}>
        <GapCell r={r} />
      </td>
      <td className={cn(TD, "text-right")}>
        {r.ext_pct != null ? <Tick value={pct(r.ext_pct)} className={cn("fig text-[12px]", dir(r.ext_pct))} /> : <Dash />}
      </td>
      <td className={cn(TD, "text-right")}>
        <Tick
          value={rs == null ? "—" : `${rs >= 0 ? "+" : ""}${rs.toFixed(2)}`}
          className={cn("fig text-[12px]", rs == null ? "text-ink-3" : rs >= 0.05 ? "up" : rs <= -0.05 ? "down" : "text-ink-2")}
        />
      </td>
      <td className={cn(TD, "text-right")}>
        <span className={cn("fig text-[12px]", r.rvol == null ? "text-ink-3" : r.rvol >= 1.5 ? "text-ink" : r.rvol >= 1 ? "text-ink-2" : "text-ink-3")}>
          {r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}
        </span>
      </td>
      <td className={cn(TD, "text-center")}>
        <Break r={r} k="pdh" />
      </td>
      <td className={cn(TD, "text-center")}>
        <Break r={r} k="pdl" />
      </td>
      <td className={cn(TD, "text-center")}>
        <Break r={r} k="pmh" />
      </td>
      <td className={cn(TD, "text-center")}>
        <Break r={r} k="pml" />
      </td>
      <td className={cn(TD, "text-center")}>
        <Trend t={r.trend} />
      </td>
      <td className={cn(TD, "text-center")}>
        <Trend200 r={r} />
      </td>
      <td className={TD}>
        <Catalysts r={r} />
      </td>
    </tr>
  );
}

/* -------------------------------------------------------------------------- */
/* The clean column set                                                       */
/* -------------------------------------------------------------------------- */

function OverviewRow({
  r,
  bench,
  session,
  pinBg,
  pinned,
  onPinned,
  handlers,
  now,
}: {
  r: ScanRow;
  bench: Bench;
  session: Session;
  pinBg: string;
  pinned: boolean;
  onPinned: () => void;
  handlers: Record<string, unknown>;
  now: number | null;
}) {
  const L = r.levels;
  const rs = r.rs[bench];
  const last = lastSignal(r, now);
  const entry = r.setup.entry;
  const pmState = L.pmh == null || L.pml == null ? null : !L.pm_done ? "forming" : r.last == null ? "inside" : r.last > L.pmh ? "above" : r.last < L.pml ? "below" : "inside";
  const pdState = r.last == null || L.pdh == null || L.pdl == null ? "inside" : r.last > L.pdh ? "above" : r.last < L.pdl ? "below" : "inside";
  const vol = r.volume ?? r.premkt?.volume ?? null;
  const adv = vol != null && r.adv ? (vol / r.adv) * 100 : null;
  const inside = L.day_hi != null && L.day_lo != null && L.pdh != null && L.pdl != null && L.day_hi <= L.pdh && L.day_lo >= L.pdl;
  const side = r.score.side;
  return (
    <tr {...(handlers as React.HTMLAttributes<HTMLTableRowElement>)}>
      <td className={cn(TD, "sticky left-0 z-10 w-[250px]", pinBg)}>
        <TickerCell
          sym={r.sym}
          name={r.name}
          price={r.last != null ? `$${num(r.last)}` : null}
          sub={r.sector}
          tags={rowTags({
            pd: pdState,
            pm: pmState,
            inside,
            news: r.catalyst != null,
            stage: r.stage,
            pool: r.promoted ? `From the pool at ${r.promoted.mark} ET — ${r.promoted.reason}` : null,
          })}
          pinned={pinned}
          onPinned={onPinned}
        />
      </td>
      <td className={TD}>
        {r.catalyst ? (
          <CatalystCell c={r.catalyst} width={380} />
        ) : r.flags[0] ? (
          <span className="block max-w-[380px] truncate text-[11.5px] text-ink-3" title={r.flags.map((f) => f.text).join("\n")}>
            {r.flags[0].text}
          </span>
        ) : (
          <span className="text-[12px] text-ink-3">—</span>
        )}
      </td>
      <td className={cn(TD, "text-right")}>
        <Tick
          value={rs == null ? "—" : `${rs >= 0 ? "+" : ""}${rs.toFixed(2)}`}
          className={cn("fig text-[12.5px]", rs == null ? "text-ink-3" : rs >= 0.05 ? "up" : rs <= -0.05 ? "down" : "text-ink-2")}
        />
      </td>
      <td className={TD}>
        <RvolCell r={r} />
      </td>
      <td className={cn(TD, "fig text-right leading-[1.3]")}>
        <Tick value={pct(r.chg_pct)} className={cn("block text-[12px]", dir(r.chg_pct))} />
        {r.ext_pct != null && (
          // Which move the second line is: it read as a bare second percentage.
          <span className="block text-[10.5px] whitespace-nowrap">
            <span className="qt-cap mr-1 text-[9px] text-ink-3">{session === "pre" ? "pre" : "after"}</span>
            <span className={dir(r.ext_pct)}>{pctText(r.ext_pct)}</span>
          </span>
        )}
      </td>
      <td className={cn(TD, "text-right")}>
        <GapCell r={r} />
      </td>
      <td className={TD}>
        <RangeCell state={pmState} hi={L.pmh} lo={L.pml} hiName="PMH" loName="PML" none="Forms from 04:00" />
      </td>
      <td className={TD}>
        <RangeCell state={pdState} hi={L.pdh} lo={L.pdl} hiName="PDH" loName="PDL" />
      </td>
      <td className={TD}>
        <Spark pts={r.spark} w={76} />
      </td>
      <td className={TD}>
        {r.volume == null && vol != null && (
          <span className="qt-cap mr-1 text-[9px] text-ink-3" title="Pre-market volume: the regular session has not traded yet">
            PM
          </span>
        )}
        <VolPct vol={vol} adv={adv} />
      </td>
      <td className={cn(TD, "whitespace-nowrap")}>
        <p className={cn("text-[12px] leading-[1.3]", setupHue(r))}>
          {side && <span className="mr-1 text-[10px]">{side === "long" ? "▲" : "▼"}</span>}
          {setupLabel(r)}
        </p>
        <p className="fig mt-0.5 text-[10.5px] text-ink-3">
          {entry && (
            <span title={`The entry reference, and how far price is from it in ten-minute ATRs (${entry.dist_atr >= 0 ? "+" : ""}${entry.dist_atr.toFixed(2)})`}>
              {entry.kind === "EMA8" ? "8 EMA" : entry.kind} {num(entry.price)}
              <span className="mx-1 text-ink-4">·</span>
              {entryAway(entry.dist_atr)}
            </span>
          )}
          {last && (
            <span className={cn("ml-2", last.fresh && cn("font-semibold", sideHue(last.side)))} title={last.fresh ? "Fired in the last 30 minutes" : "Today's latest signal"}>
              {last.text}
            </span>
          )}
        </p>
      </td>
      <td className={TD}>
        <ScoreTier v={r.score.total} title={`${r.score.total} of 100 — a heuristic rank, not a probability${recordTip(r.record)}`} />
      </td>
    </tr>
  );
}

/* -------------------------------------------------------------------------- */
/* The options column set                                                     */
/* -------------------------------------------------------------------------- */

function OptionsRow({
  r,
  lead,
  handlers,
  budget,
}: {
  r: ScanRow;
  lead: React.ReactNode;
  handlers: Record<string, unknown>;
  budget: number | null;
}) {
  const o = r.options;
  const { zeroDte } = useOptionsPrefs();
  const front = o?.em.find((e) => e.key === "front");
  const weekly = o?.em.find((e) => e.key === "weekly");
  // The contract the expiry rule picks — the same one the Game plan quotes.
  const pick = o ? optionsPick(o, zeroDte) : "weekly";
  // 0DTE off in Settings: no same-day contract, on any name.
  const longs = o?.contracts.filter((x) => x.kind === "long" && (zeroDte || x.dte > 0)) ?? [];
  const c = longs.find((x) => x.key === pick) ?? longs[0];
  const size = budget != null && c?.risk_per_contract ? Math.floor(budget / c.risk_per_contract) : null;
  return (
    <tr {...(handlers as React.HTMLAttributes<HTMLTableRowElement>)}>
      {lead}
      <td className={TD}>
        <ScoreBar v={r.score.total} record={r.record} />
      </td>
      <td className={cn(TD, "text-right")}>
        <Tick value={num(r.last)} className="fig text-[12.5px] text-ink" />
      </td>
      {!o || !o.ok ? (
        <td colSpan={budget != null ? 12 : 11} className={cn(TD, "text-[11.5px] text-ink-3")}>
          {o?.error ?? (
            <span title="Cboe's delayed chains load one name every ten seconds after a start">
              <HelmInline label="Chain loading" />
            </span>
          )}
        </td>
      ) : (
        <>
          <td className={cn(TD, "fig text-right text-[12px] text-ink")}>{o.iv30 != null ? `${o.iv30.toFixed(1)}%` : "—"}</td>
          <td className={cn(TD, "fig text-right text-[12px] text-ink-2")}>{o.rv20 != null ? `${o.rv20.toFixed(1)}%` : "—"}</td>
          <td className={cn(TD, "text-right whitespace-nowrap")}>
            <span className="fig text-[12px] text-ink-2">{o.iv_rv != null ? o.iv_rv.toFixed(2) : "—"}</span>
            {o.premium && <span className={cn("qt-cap ml-1.5 text-[9.5px]", premiumHue(o.premium))}>{o.premium}</span>}
          </td>
          <td className={cn(TD, "fig text-right text-[12px]")}>
            {o.iv_rank != null ? (
              <span className="text-ink-2">{Math.round(o.iv_rank)}</span>
            ) : (
              <span className="text-[11px] text-ink-3" title="IV rank needs twenty logged sessions; it is building">
                {o.iv_days}d
              </span>
            )}
          </td>
          <td className={cn(TD, "text-right whitespace-nowrap")}>
            {front ? <EmCell e={front} /> : <Dash />}
          </td>
          <td className={cn(TD, "text-right whitespace-nowrap")}>
            {weekly ? <EmCell e={weekly} /> : <Dash />}
          </td>
          <td className={cn(TD, "fig text-right text-[12px] text-ink-2")}>
            {o.skew != null ? `${o.skew >= 0 ? "+" : ""}${o.skew.toFixed(1)}` : "—"}
          </td>
          <td className={cn(TD, "whitespace-nowrap")}>
            <Liquidity o={o} />
          </td>
          <td className={cn(TD, "whitespace-nowrap")}>
            <FlowCell f={o.flow ?? null} />
          </td>
          <td className={cn(TD, "whitespace-nowrap")}>
            {c ? (
              <span className="fig text-[11.5px] text-ink-2" title={[c.note, estTitle(c)].filter(Boolean).join("\n")}>
                <span className={c.right === "C" ? "text-call-fig" : "text-put-fig"}>
                  {strike(c.strike)}
                  {c.right}
                </span>{" "}
                {shortDate(c.expiry)} · {Math.abs(c.est_delta ?? c.delta).toFixed(2)}Δ ·{" "}
                <Tick value={`$${(c.est_mid ?? c.mid).toFixed(2)}`} />
                {c.est_mid != null && <span className="qt-cap ml-1 text-[9.5px] text-ink-3">est</span>}
                {o.earnings_in && o.earnings_in <= c.expiry && (
                  <span className="qt-cap ml-1.5 text-[9.5px] text-flip-fig" title={`Earnings before this expiry — IV collapses after the report (${o.earnings_in})`}>
                    earnings
                  </span>
                )}
              </span>
            ) : (
              <Dash title={r.score.side ? "No contract near 0.60 delta" : "No side yet — no contract to suggest"} />
            )}
          </td>
          <td className={cn(TD, "fig text-right text-[12px] text-ink-2")}>
            {c?.risk_per_contract != null ? `$${Math.round(c.risk_per_contract)}` : "—"}
          </td>
          {budget != null && (
            <td className={cn(TD, "fig text-right text-[12px]", size ? "text-ink" : "text-ink-3")}>
              {size != null ? (size > 0 ? `${size}` : "0") : "—"}
            </td>
          )}
        </>
      )}
    </tr>
  );
}

function EmCell({ e }: { e: { dte: number; straddle: number; pct: number; expiry: string } }) {
  return (
    <span className="fig text-[12px]" title={`${e.expiry} straddle ±$${e.straddle.toFixed(2)}`}>
      <span className="text-ink">±{e.pct.toFixed(1)}%</span>
      <span className="ml-1.5 text-[10.5px] text-ink-3">{e.dte === 0 ? "0DTE" : `${e.dte}d`}</span>
    </span>
  );
}

function Liquidity({ o }: { o: NonNullable<ScanRow["options"]> }) {
  const g = o.liquidity.grade;
  return (
    <span className="text-[11.5px]" title={`At-the-money spread ${o.liquidity.spread_pct?.toFixed(1) ?? "—"}% of mid · OI ${compact(o.liquidity.oi)}`}>
      <span className={cn("qt-cap text-[9.5px]", g === "good" ? "text-call-fig" : g === "poor" ? "text-put-fig" : "text-ink-2")}>
        {g ?? "—"}
      </span>
      <span className="fig ml-1.5 text-ink-3">{o.liquidity.spread_pct != null ? `${o.liquidity.spread_pct.toFixed(1)}%` : ""}</span>
    </span>
  );
}

/** Put/call volume and its lean — the busiest strike on the hover. */
function FlowCell({ f }: { f: NonNullable<NonNullable<ScanRow["options"]>["flow"]> | null }) {
  if (!f || f.pc_vol == null) return <Dash title="No volume read yet today" />;
  const top = f.top[0];
  const tip = top
    ? `Busiest: ${strike(top.strike)}${top.right} ${shortDate(top.expiry)} — ${compact(top.volume)} traded on ${compact(top.oi)} open interest`
    : undefined;
  return (
    <span className="text-[11.5px]" title={tip}>
      <span className="fig text-ink-2">P/C {f.pc_vol.toFixed(2)}</span>
      {f.lean && (
        <span className={cn("qt-cap ml-1.5 text-[9.5px]", f.lean === "calls" ? "text-call-fig" : f.lean === "puts" ? "text-put-fig" : "text-ink-3")}>
          {f.lean}
        </span>
      )}
    </span>
  );
}

export function premiumHue(p: "cheap" | "fair" | "rich"): string {
  return p === "rich" ? "text-flip-fig" : p === "cheap" ? "text-call-fig" : "text-ink-3";
}

/* -------------------------------------------------------------------------- */
/* Cells shared with the Pine                                                  */
/* -------------------------------------------------------------------------- */

const PAIR = { pdh: "pdl", pdl: "pdh", pmh: "pml", pml: "pmh" } as const;
const NAME = { pdh: "PDH", pdl: "PDL", pmh: "PMH", pml: "PML" } as const;

/**
 * The Pine's break cell: a ten-segment bar for how far price has come toward
 * the level, a filled square once it is broken (and the other side of that
 * pair left blank, as the script leaves it), dots while the pre-market range
 * is still forming. The last tenth goes amber — the script's "about to break"
 * alert fires at 90%.
 */
function Break({ r, k }: { r: ScanRow; k: "pdh" | "pdl" | "pmh" | "pml" }) {
  const hi = k === "pdh" || k === "pmh";
  const pm = k === "pmh" || k === "pml";
  const price = r.levels[k];
  const p = r.progress[k];
  const tip = `${NAME[k]} ${num(price)}`;
  if (pm && !r.levels.pm_done) {
    return (
      <span title={`${tip} · pre-market still forming`} className="fig text-[11px] text-ink-3">
        {levelGlyph("forming")}
      </span>
    );
  }
  if (r.broken[k]) {
    return (
      <span title={`${tip} · broken`} className="inline-flex justify-center">
        <span className={cn("h-[9px] w-[9px] rounded-[1px]", hi ? "bg-call-fig" : "bg-put-fig")} />
      </span>
    );
  }
  if (r.broken[PAIR[k]]) return <span aria-hidden />;
  if (p == null) return <Dash title={tip} />;
  const n = Math.round(Math.max(0, Math.min(1, p)) * 10);
  const near = p >= 0.9;
  const fill = near ? "bg-flip-fig" : hi ? "bg-call-fig" : "bg-put-fig";
  return (
    <span title={`${tip} · ${Math.round(p * 100)}% of the way there`} className="inline-flex gap-[1px] align-middle">
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={cn("h-[9px] w-[3px]", i < n ? fill : "bg-[var(--qt-track,var(--ring))]", i < n && !near && "opacity-80")} />
      ))}
    </span>
  );
}

/** The Pine's trend column: ▲ above PDH and PMH, ▼ below PDL and PML, ⚠ inside. */
function Trend({ t }: { t: -1 | 0 | 1 }) {
  const tip = t === 1 ? "Bullish — above PDH and PMH" : t === -1 ? "Bearish — below PDL and PML" : "Neutral — inside the levels";
  return (
    <span title={tip} className={cn("text-[12px]", t === 1 ? "text-call-fig" : t === -1 ? "text-put-fig" : "text-flip-fig")}>
      {t === 1 ? "▲" : t === -1 ? "▼" : "⚠"}
    </span>
  );
}

/** The ten-minute 200 EMA's side (structure.py, 2026-10-30): ▲ above, ▼ below, — on it or not held. */
function Trend200({ r }: { r: ScanRow }) {
  const t = r.trend200 ?? 0;
  const line = r.levels.ema200;
  if (line == null) return <Dash title="The 200 EMA needs two days of ten-minute bars" />;
  const slope = r.ema200_slope ? `, ${r.ema200_slope}` : "";
  const tip = t === 1 ? `Above the 200 EMA (${line.toFixed(2)}${slope}) — the long side` : t === -1 ? `Below the 200 EMA (${line.toFixed(2)}${slope}) — the short side` : `On the 200 EMA (${line.toFixed(2)}${slope})`;
  return (
    <span title={tip} className={cn("text-[12px]", t === 1 ? "text-call-fig" : t === -1 ? "text-put-fig" : "text-ink-3")}>
      {t === 1 ? "▲" : t === -1 ? "▼" : "—"}
    </span>
  );
}

const GAP_TIP = "The open against the previous close. Before the open, where the extended session stands against that close.";

function GapCell({ r }: { r: ScanRow }) {
  const g = gapOf(r);
  if (g == null) return <Dash title={GAP_TIP} />;
  return <Tick value={pct(g)} className={cn("fig text-[12px]", dir(g))} />;
}

function Dash({ title }: { title?: string }) {
  return (
    <span className="text-ink-3" title={title}>
      —
    </span>
  );
}

/**
 * The row's catalysts, on one line: the first flag and a count of the rest, which
 * the count's hover and the detail pane list. They wrapped, so a row with three
 * was half as tall again as its neighbours, in a column off the edge of the pane
 * where nobody could see why.
 */
function Catalysts({ r }: { r: ScanRow }) {
  const [first, ...rest] = r.flags;
  // The day's most important story leads when it is a major one (catalysts.py).
  if (r.catalyst?.major) {
    return (
      <div className="flex gap-x-2 whitespace-nowrap">
        <span className="qt-cap text-[9.5px] text-ink" title={`${r.catalyst.title}\n${r.catalyst.provider}`}>
          {r.catalyst.tag}
        </span>
        {r.flags.length > 0 && (
          <span className="qt-cap text-[9.5px] text-ink-3" title={r.flags.map((f) => f.text).join("\n")}>
            +{r.flags.length}
          </span>
        )}
      </div>
    );
  }
  if (!first) {
    return r.news.length > 0 ? (
      <span className="qt-cap text-[9.5px] whitespace-nowrap text-ink-3" title={r.news[0].title}>
        {r.news.length} news
      </span>
    ) : null;
  }
  return (
    <div className="flex gap-x-2 whitespace-nowrap">
      <span
        className={cn("qt-cap text-[9.5px]", first.tone === "warn" ? "text-flip-fig" : first.tone === "good" ? "text-call-fig" : "text-ink-3")}
        title={first.text}
      >
        {flagShort(first.kind, first.text)}
      </span>
      {rest.length > 0 && (
        <span className="qt-cap text-[9.5px] text-ink-3" title={rest.map((f) => f.text).join("\n")}>
          +{rest.length}
        </span>
      )}
    </div>
  );
}

/** A flag's chip text: the kind's short name, plus the first word of detail where it says something. */
function flagShort(kind: ScanRow["flags"][number]["kind"], text: string): string {
  switch (kind) {
    case "earnings": {
      // "Peer TSM reports Thu" → "Peer TSM Thu": a sector peer's report, not the name's own.
      const peer = text.match(/^Peer\s+(\S+)\s+reports?\s+(.*)$/i);
      if (peer) return `Peer ${peer[1]} ${peer[2]}`.slice(0, 18);
      // "Reported after yesterday's close — in play (-31.8% surprise)" → "Earn -31.8%".
      // Stripping "report" from the front of it left "Earn ed after yest".
      if (/^reported\b/i.test(text)) return `Earn ${text.match(/([+-][\d.]+)% surprise/)?.[1] ?? "out"}${/surprise/.test(text) ? "%" : ""}`;
      return `Earn ${text.replace(/^reports?\s*/i, "").split(/[·—,]/)[0].trim()}`.slice(0, 18);
    }
    case "filing":
      return text.split(/\s/)[0].replace(/:$/, "") || "Filing";
    case "event":
      return "Event";
    case "fuel":
      return "Range spent";
    case "extended":
      return "Extended";
    case "gap":
      return "Gap";
    case "halt":
      return "Halt";
    case "frame":
      // "Long into a daily downtrend: …" → "Vs daily": the setup is against the daily trend.
      return "Vs daily";
    case "catalyst":
      // 'Against: Reuters: "Jefferies downgrades …" (2h)' → "Against: Jefferies downgrades".
      return `Against: ${(text.replace(/^Against:\s*/, "").replace(/^[^"]*"/, "").split(/[\s"]+/).slice(0, 2).join(" ")) || "news"}`.slice(0, 22);
    case "short_interest":
      // "Squeeze risk: 22% of the float is short …" → "22% short".
      return `${text.match(/(\d+)%/)?.[1] ?? ""}% short`.trim();
    case "news": {
      // "8 headlines in 24h" → "8 news": the count is the information, and
      // the long word was what pushed the column off a 1920 screen.
      const n = text.match(/\d+/)?.[0];
      return n ? `${n} news` : "News";
    }
  }
}

/** "2.0 ATR below": where the entry sits from price, in ten-minute ATRs. */
function entryAway(dist: number): string {
  const d = Math.abs(dist);
  if (d < 0.05) return "at it";
  // `dist` is price less the entry: positive is price above it, so the entry is below.
  return `${d.toFixed(1)} ATR ${dist > 0 ? "below" : "above"}`;
}

/**
 * RELATIVE VOLUME, OR BEFORE THE BELL THE PRE-MARKET'S SHARE OF AN AVERAGE DAY. Volume
 * by time of day starts at the open, so until then the column was a dash on every row
 * at the hour the list is read to pick names. The share of an average day already
 * traded is what the pre-open rank reads (scanscore.in_play: nothing under 0.25%, all
 * of its points at 4%), and the bar is drawn on that scale.
 */
function RvolCell({ r }: { r: ScanRow }) {
  if (r.rvol != null) return <RvolBar v={r.rvol} />;
  const p = r.premkt?.pct_adv;
  if (p == null) return <span className="text-[12px] text-ink-3" title="No volume read yet">—</span>;
  const hue = p >= 4 ? "text-flip-fig" : p >= 1 ? "text-ink" : "text-ink-2";
  const src = r.premkt?.source === "screener" ? "TradingView's screener, fifteen minutes behind" : "Nasdaq";
  return (
    <div
      className="min-w-[84px]"
      title={`Pre-market volume is ${p.toFixed(2)}% of an average day${r.premkt?.volume != null ? ` (${compact(r.premkt.volume)} shares)` : ""}, from ${src}. The pre-open rank reads it from 0.25% to 4%. Relative volume by time of day starts at the open.`}
    >
      <p className={cn("fig text-[12.5px] leading-none", hue)}>
        {p.toFixed(1)}%<span className="qt-cap ml-1 text-[9px] text-ink-3">pre</span>
      </p>
      <div className="relative mt-[6px] h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", p >= 4 ? "bg-flip-fig" : "bg-ink-3")} style={{ width: `${Math.min(p / 4, 1) * 100}%` }} />
      </div>
    </div>
  );
}

function setupHue(r: ScanRow): string {
  const s = r.setup.state;
  if (s === "retest") return cn("font-semibold", r.setup.side ? sideHue(r.setup.side) : "text-ink");
  if (s === "pullback") return r.setup.side ? sideHue(r.setup.side) : "text-ink-2";
  if (s === "approaching") return "text-flip-fig";
  if (s === "extended") return "text-ink-2";
  if (s === "failed") return "text-ink-3 line-through decoration-ink-3/60";
  return "text-ink-3";
}

/** The score as a figure over a flat bar — neutral ink, because a score is not a side. */
/** The record line's three figures for the score's hover (scanscore.record_for). */
function recordTip(rec: ScanRow["record"]): string {
  if (!rec) return "";
  const win = rec.win_1r != null ? `${Math.round(rec.win_1r * 100)}%` : "—";
  const held = rec.held_r != null ? `${rec.held_r >= 0 ? "+" : ""}${rec.held_r.toFixed(1)} R` : "—";
  return `\nSignals like this ((${rec.kind}) ${rec.side}s scored ${rec.band}): ${win} reached +1R, ${held} held with the stop kept, ${rec.n} signals over ${rec.sessions ?? "—"} sessions${rec.small ? " — small sample" : ""}`;
}

function ScoreBar({ v, record }: { v: number; record?: ScanRow["record"] }) {
  return (
    <div className="flex items-center gap-2" title={`${v} of 100 — a heuristic rank, not a probability${recordTip(record)}`}>
      <span className={cn("fig w-[22px] text-right text-[12.5px]", v >= 65 ? "text-ink" : v >= 40 ? "text-ink-2" : "text-ink-3")}>{v}</span>
      <span className="relative h-[4px] w-[36px] bg-[var(--qt-track,var(--ring))]">
        <span
          className={cn("absolute inset-y-0 left-0", v >= 65 ? "bg-ink" : v >= 40 ? "bg-ink-2" : "bg-ink-3")}
          style={{ width: `${Math.max(0, Math.min(100, v))}%` }}
        />
      </span>
    </div>
  );
}

const ET_NOW = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const minutesOf = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

/**
 * Today's latest fired signal, for the setup cell: "(L)▲ 10:40". Fresh — lit
 * in its side's hue — for thirty minutes after the bar it fired on, which is
 * the window a retest entry is still a retest entry. A pending (E) candle is
 * not a signal yet and is left to the detail pane.
 */
function lastSignal(r: ScanRow, now: number | null): { text: string; side: Side; fresh: boolean } | null {
  const fired = r.signals.filter((s) => s.kind !== "E_SETUP");
  const s = fired[fired.length - 1];
  if (!s) return null;
  const glyph = s.kind === "BO" ? "◆" : `(${s.kind})`;
  const arrow = s.side === "long" ? "▲" : "▼";
  const age = now == null ? null : minutesOf(ET_NOW.format(new Date(now))) - minutesOf(s.at_et);
  return { text: `${glyph}${arrow} ${s.at_et}`, side: s.side, fresh: age != null && age >= 0 && age <= 30 };
}

/** A strike as the chain prints it: 747, 587.5, 242.5 — no trailing zeros. */
export function strike(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)));
}

/**
 * What an "est" price means, for its hover: the delayed quote it was moved
 * from, and the stock prices either side of the move. Null with no estimate.
 */
export function estTitle(c: OptContract): string | null {
  if (c.est_mid == null || c.est_spot == null || c.quote_spot == null) return null;
  return (
    `Estimated at the live stock price $${c.est_spot.toFixed(2)}: Cboe's quote is fifteen minutes old — ` +
    `$${c.mid.toFixed(2)} (${Math.abs(c.delta).toFixed(2)}Δ) with the stock at $${c.quote_spot.toFixed(2)} — ` +
    "moved through its delta and gamma. IV is held where it was."
  );
}

/**
 * The contract the desk trades on this name: the collector's rule (`o.pick` —
 * the same-day front on SPY / QQQ / IWM, the weekly elsewhere), unless 0DTE is
 * off in Settings and the pick is a same-day expiry.
 */
export function optionsPick(o: OptionsCtx, zeroDte: boolean): "front" | "weekly" {
  const pick = o.pick ?? "weekly";
  const sameDay = o.em.find((e) => e.key === "front")?.dte === 0 || o.contracts.some((c) => c.key === "front" && c.dte === 0);
  return pick === "front" && !zeroDte && sameDay ? "weekly" : pick;
}

/** "2026-10-16" → "Oct 16". */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** The sort key's figure for a row; null sinks to the bottom. */
export function sortValue(r: ScanRow, k: SortKey, bench: Bench): number | null {
  switch (k) {
    case "score":
      return r.score.total;
    case "rs":
      return r.rs[bench];
    case "rvol":
      // Before the bell the column shows the pre-market's share of an average day, so
      // it sorts on that. Never both at once: a row has one or the other.
      return r.rvol ?? r.premkt?.pct_adv ?? null;
    case "chg":
      return r.chg_pct;
    case "gap":
      return gapOf(r);
    case "ext":
      return r.ext_pct;
    case "vol":
      return r.volume ?? r.premkt?.volume ?? null;
    case "trend":
      return r.trend;
    case "ivrv":
      return r.options?.iv_rv ?? null;
    case "em":
      return r.options?.em.find((e) => e.key === "front")?.pct ?? null;
  }
}
