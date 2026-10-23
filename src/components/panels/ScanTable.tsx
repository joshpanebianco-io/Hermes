"use client";

import type { RefObject } from "react";
import type { OptContract, OptionsCtx, ScanRow, Side } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { HelmInline } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { levelGlyph, setupLabel, sideHue } from "@/components/panels/ScanDetail";
import { compact, dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { useOptionsPrefs } from "@/lib/optionsPrefs";

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
 * THE TICKER STAYS PUT. Rank and ticker are pinned to the left edge, so on a
 * narrow screen the table scrolls sideways under them rather than losing which
 * row is which.
 */

export type ColSet = "ranked" | "options";
export type SortKey = "score" | "rs" | "rvol" | "chg" | "ext" | "vol" | "trend" | "ivrv" | "em";
type Bench = "SPY" | "QQQ";

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
  onStep,
  tbody,
  budget,
}: {
  rows: ScanRow[];
  cols: ColSet;
  bench: Bench;
  sort: SortKey;
  onSort: (k: SortKey) => void;
  now: number | null;
  selected: string | null;
  onPick: (sym: string) => void;
  onStep: (sym: string, delta: number) => void;
  tbody: RefObject<HTMLTableSectionElement | null>;
  budget: number | null;
}) {
  const th = { cur: sort, onSort };
  return (
    <table className={cn("w-full border-separate border-spacing-0 text-left", cols === "ranked" ? "min-w-[1360px]" : "min-w-[1320px]")}>
      <thead className="sticky top-0 z-20">
        <tr>
          <Th pin={0} className="w-[34px] text-right">
            #
          </Th>
          <Th pin={34} className="w-[132px]">
            Ticker
          </Th>
          {cols === "ranked" ? (
            <>
              <Th k="score" {...th} className="w-[88px]">
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
              <Th k="ivrv" {...th} right title="Implied volatility against 20-day realised: whether premium is cheap, fair or rich">
                Options
              </Th>
              <Th>Catalysts</Th>
            </>
          ) : (
            <>
              <Th k="score" {...th} className="w-[88px]">
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
      <tbody ref={tbody}>
        {rows.map((r, i) => (
          <Row
            key={r.sym}
            r={r}
            rank={i + 1}
            cols={cols}
            bench={bench}
            now={now}
            on={selected === r.sym}
            budget={budget}
            onPick={() => onPick(r.sym)}
            onStep={(d) => onStep(r.sym, d)}
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
        "qt-cap border-b border-ring bg-bg px-2 py-2 align-bottom text-[10.5px] font-semibold whitespace-nowrap text-ink-3",
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

const TD = "border-b border-ring/60 px-2 py-2";

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
  now,
  on,
  budget,
  onPick,
  onStep,
}: {
  r: ScanRow;
  rank: number;
  cols: ColSet;
  bench: Bench;
  now: number | null;
  on: boolean;
  budget: number | null;
  onPick: () => void;
  onStep: (delta: number) => void;
}) {
  const side = r.score.side;
  // Pinned cells need their own ground, or the scrolled columns show through.
  const pinBg = on ? "bg-surface-2" : "bg-bg group-hover:bg-surface";
  const lead = (
    <>
      <td className={cn(TD, "fig sticky left-0 z-10 w-[34px] text-right text-[11px] text-ink-3", pinBg)}>{rank}</td>
      <td className={cn(TD, "sticky z-10 w-[132px]", pinBg)} style={{ left: 34 }}>
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          <span className={cn("w-[10px] text-[11px]", side ? sideHue(side) : "text-ink-3")}>
            {side === "long" ? "▲" : side === "short" ? "▼" : "·"}
          </span>
          <TickerLogo sym={r.sym} size={16} />
          <span className="text-[13px] font-semibold text-ink" title={r.name ?? undefined}>
            {r.sym}
          </span>
          {r.sector && <span className="qt-cap text-[9.5px] text-ink-3">{r.sector}</span>}
        </div>
      </td>
    </>
  );
  const handlers = {
    "data-sym": r.sym,
    tabIndex: 0,
    onClick: onPick,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onPick();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        onStep(e.key === "ArrowDown" ? 1 : -1);
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
        <td colSpan={18} className={cn(TD, "text-[11.5px] text-ink-3")}>
          {r.error ?? "no data yet"}
        </td>
      </tr>
    );
  }

  if (cols === "options") return <OptionsRow r={r} lead={lead} handlers={handlers} budget={budget} />;

  const rs = r.rs[bench];
  const entry = r.setup.entry;
  const last = lastSignal(r, now);
  const o = r.options;
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
            title={`Pre-market volume${r.premkt.pct_adv != null ? ` — ${r.premkt.pct_adv.toFixed(1)}% of the 20-day average day` : ""} (Nasdaq, about fifteen minutes delayed)`}
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
      <td className={cn(TD, "text-right whitespace-nowrap")}>
        {o && o.ok && o.iv30 != null ? (
          <span className="fig text-[11.5px]" title={`IV30 ${o.iv30.toFixed(1)}% vs RV20 ${o.rv20?.toFixed(1) ?? "—"}%`}>
            <span className="text-ink-2">{o.iv30.toFixed(0)}%</span>
            {o.premium && <span className={cn("qt-cap ml-1.5 text-[9.5px]", premiumHue(o.premium))}>{o.premium}</span>}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={TD}>
        <Catalysts r={r} />
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

function Dash({ title }: { title?: string }) {
  return (
    <span className="text-ink-3" title={title}>
      —
    </span>
  );
}

function Catalysts({ r }: { r: ScanRow }) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-0.5 whitespace-nowrap">
      {r.flags.slice(0, 3).map((f) => (
        <span
          key={`${f.kind}-${f.text}`}
          className={cn("qt-cap text-[9.5px]", f.tone === "warn" ? "text-flip-fig" : f.tone === "good" ? "text-call-fig" : "text-ink-3")}
          title={f.text}
        >
          {flagShort(f.kind, f.text)}
        </span>
      ))}
      {r.news.length > 0 && !r.flags.some((f) => f.kind === "news") && (
        <span className="qt-cap text-[9.5px] text-ink-3" title={r.news[0].title}>
          {r.news.length} news
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
      return `Earn ${text.replace(/^reports?\s*/i, "").split(/[·—,]/)[0].trim()}`.slice(0, 18);
    }
    case "filing":
      return text.split(/\s/)[0] || "Filing";
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
  const close = rec.avg_close_r != null ? `${rec.avg_close_r >= 0 ? "+" : ""}${rec.avg_close_r.toFixed(1)} R` : "—";
  return `\nSignals like this ((${rec.kind}) ${rec.side}s scored ${rec.band}): ${win} reached +1R, ${close} at the close, ${rec.n} signals over ${rec.sessions ?? "—"} sessions${rec.small ? " — small sample" : ""}`;
}

function ScoreBar({ v, record }: { v: number; record?: ScanRow["record"] }) {
  return (
    <div className="flex items-center gap-2" title={`${v} of 100 — a heuristic rank, not a probability${recordTip(record)}`}>
      <span className={cn("fig w-[22px] text-right text-[12.5px]", v >= 65 ? "text-ink" : v >= 40 ? "text-ink-2" : "text-ink-3")}>{v}</span>
      <span className="relative h-[4px] w-[48px] bg-[var(--qt-track,var(--ring))]">
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
      return r.rvol;
    case "chg":
      return r.chg_pct;
    case "ext":
      return r.ext_pct;
    case "vol":
      return r.volume;
    case "trend":
      return r.trend;
    case "ivrv":
      return r.options?.iv_rv ?? null;
    case "em":
      return r.options?.em.find((e) => e.key === "front")?.pct ?? null;
  }
}
