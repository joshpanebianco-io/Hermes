"use client";

import type { OptionsCtx, ScanRow } from "@/types/scanner";
import { Popover } from "@/components/ui/Popover";
import { premiumHue, shortDate } from "@/components/panels/ScanTable";
import { PREMIUM_CHEAP, PREMIUM_RICH } from "@/lib/vix";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * What the options figures mean, for the selected name — the click-through
 * behind every figure in the scanner's Options block, built the way the VIX
 * bands and the implied day were: the name on top, then each figure with its
 * own number and what that number says for THIS trade, in the order the
 * decision is made (owner, 2026-10-22: "what they mean for the stocks
 * section").
 *
 * EVERY READ IS CONDITIONAL ON THE NAME'S OWN STATE, never a glossary: rich
 * says "the spread", cheap says "the long", a rank still building says how
 * many sessions it has, a flow that leans against the side says so. The words
 * on the block are the server's (optcalc: PREMIUM_CHEAP / PREMIUM_RICH, the
 * liquidity grades, FLOW_CALLS / FLOW_PUTS); the constants below mirror the
 * ones the reads quote, and this panel only says what the words mean.
 */

/** optcalc.LIQ_GOOD / LIQ_OK — the at-the-money spread as a % of mid. */
const LIQ_GOOD = 3;
const LIQ_OK = 8;
/** optcalc.FLOW_CALLS / FLOW_PUTS — put ÷ call volume. */
const FLOW_CALLS = 0.7;
const FLOW_PUTS = 1.3;
/** Volume over open interest past this reads as mostly fresh positions (the block's own hover). */
const FRESH = 0.5;
/** IV rank against the name's own year: cheap for itself below, dear above. Rules of thumb, this panel's own. */
const RANK_LOW = 20;
const RANK_HIGH = 70;
/** Vol points either side of zero that a 25-delta skew reads as flat. This panel's own. */
const SKEW_FLAT = 1;

export function OptionsFiguresPopover({
  r,
  o,
  pick,
  className,
  children,
}: {
  r: ScanRow;
  o: OptionsCtx;
  pick: "front" | "weekly";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What ${r.sym}'s options figures mean`}
      title="Click for what the figures mean"
      className={className}
      panel={<OptionsFigures r={r} o={o} pick={pick} />}
    >
      {children}
    </Popover>
  );
}

function OptionsFigures({ r, o, pick }: { r: ScanRow; o: OptionsCtx; pick: "front" | "weekly" }) {
  const sym = r.sym;
  const side = r.score.side;
  const front = o.em.find((e) => e.key === "front");
  const weekly = o.em.find((e) => e.key === "weekly");
  const f = o.flow;

  // ---- the reads, each off the name's own state -------------------------
  const premiumRead =
    o.premium === "rich"
      ? `Over ${PREMIUM_RICH.toFixed(2)}: premium is rich against what ${sym} has been doing. The debit spread sells some of it back; a long option pays for more move than has been happening.`
      : o.premium === "cheap"
        ? `Under ${PREMIUM_CHEAP.toFixed(2)}: premium is cheap against what ${sym} has been doing. A long option keeps the convexity.`
        : o.premium === "fair"
          ? `Between ${PREMIUM_CHEAP.toFixed(2)} and ${PREMIUM_RICH.toFixed(2)}: fairly priced. Either structure; let the rank and the skew decide.`
          : "Needs IV30 and twenty daily closes.";

  const rankRead =
    o.iv_rank == null
      ? `Where today's IV sits between ${sym}'s own low and high over the logged year — it needs twenty sessions first. Then: under ${RANK_LOW} is cheap for the name itself, over ${RANK_HIGH} is dear and IV tends to fall from there, against a long.`
      : o.iv_rank < RANK_LOW
        ? `Low for ${sym}'s own year: options are cheap against the name itself, and a long option is the natural way in.`
        : o.iv_rank > RANK_HIGH
          ? `High for ${sym}'s own year: IV tends to fall from here, which works against a long. The spread, and expect premium to come in. With rich IV / RV as well, this is the strongest case for a spread.`
          : `Mid-range for ${sym}'s own year: neither cheap nor dear against itself. IV against realised decides the structure.`;

  const skewRead =
    o.skew == null
      ? "Needs a 25-delta put and call with quotes on the weekly."
      : o.skew > SKEW_FLAT
        ? `Puts bid — the normal state. ${
            side === "short"
              ? "A put bought for the short is the dear side, so the put spread sells some of it back."
              : "The call you buy on a long is the cheap side; a put bought for a short would be the dear one."
          }`
        : o.skew < -SKEW_FLAT
          ? `Negative: calls dearer than puts — upside is being chased. ${
              side === "long" ? "A long call pays up here, and the trade is late." : "A long call would pay up; puts are the cheap side."
            }`
          : "Within a point of zero: calls bid as hard as puts. Neither side is the dear one.";

  const liq = o.liquidity;
  const liqRead =
    liq.grade === "good"
      ? `The at-the-money spread is under ${LIQ_GOOD}% of mid: fills land near mid.`
      : liq.grade === "ok"
        ? `${LIQ_GOOD} to ${LIQ_OK}% of mid: some of the move goes to the fill — work the order.`
        : liq.grade === "poor"
          ? `Over ${LIQ_OK}% of mid: the fill alone can cost a good part of the move. Size for it or leave it.`
          : "No at-the-money pair with quotes on the front expiry.";

  const flowRead = (() => {
    if (!f || f.pc_vol == null) {
      return "Fewer than a hundred contracts traded across the kept chain — a handful of prints is noise, not positioning.";
    }
    const lean =
      f.lean === "calls"
        ? side === "long"
          ? `Call-led (P/C under ${FLOW_CALLS}) with the long: support, never a vote on its own.`
          : side === "short"
            ? `Call-led (P/C under ${FLOW_CALLS}) against the short: a reason for a smaller size or the spread.`
            : `Call-led: P/C under ${FLOW_CALLS}.`
        : f.lean === "puts"
          ? side === "short"
            ? `Put-led (P/C over ${FLOW_PUTS}) with the short: support, never a vote on its own.`
            : side === "long"
              ? `Put-led (P/C over ${FLOW_PUTS}) against the long: a reason for a smaller size or the spread.`
              : `Put-led: P/C over ${FLOW_PUTS}.`
          : `Balanced: P/C between ${FLOW_CALLS} and ${FLOW_PUTS}, no lean to read.`;
    const fresh =
      f.vol_oi != null
        ? ` Vol/OI ${f.vol_oi.toFixed(2)}: ${f.vol_oi > FRESH ? "mostly fresh positions today." : "mostly positions already held."}`
        : "";
    return lean + fresh;
  })();

  const earningsRead = o.earnings_in
    ? `Earnings land before the ${shortDate(o.earnings_in)} expiry. Implied volatility collapses after the report, so a long option bought into it pays for a move it may not keep — the spread, or wait.`
    : "No report inside either expiry read.";

  // ---- the earnings number, the term, the contract's R (2026-10-22) -------
  const em = o.earnings_move ?? null;
  const implied = em?.implied ?? null;
  const avgAbs = em?.avg_abs ?? null;
  const earnMoveRead = (() => {
    if (!em || (!implied && em.realised.length === 0)) return "No report ahead inside the chain's expiries, and no report history yet.";
    if (!implied) {
      return `No report inside the chain's expiries. On its last ${em.realised.length} reports ${sym} moved ${em.realised.map((m) => `${m.pct >= 0 ? "+" : ""}${m.pct.toFixed(1)}%`).join(", ")} close to close — the size of day a report is.`;
    }
    const event = implied.clean_pct ?? implied.pct;
    if (avgAbs == null) {
      return `The straddle covering the ${shortDate(implied.report)} report prices ±${implied.pct.toFixed(1)}% to ${shortDate(implied.expiry)}${implied.clean_pct != null ? `, about ±${implied.clean_pct.toFixed(1)}% for the event alone` : ""}. No report history yet to judge it against.`;
    }
    if (event > avgAbs * 1.2) {
      return `The chain prices ±${event.toFixed(1)}% for the event against ±${avgAbs.toFixed(1)}% the name has averaged on its last reports: dear. A long bought into it needs more than a normal report; the spread sells the dear part, or wait for the crush.`;
    }
    if (event < avgAbs * 0.8) {
      return `The chain prices ±${event.toFixed(1)}% for the event against ±${avgAbs.toFixed(1)}% the name has averaged on its last reports: cheap. The event is under-priced — a long into it, sized for the gap either way.`;
    }
    return `The chain prices ±${event.toFixed(1)}% for the event, about what the name has averaged (±${avgAbs.toFixed(1)}%). Fairly priced: the direction, not the premium, decides.`;
  })();

  const term = o.term ?? [];
  const tFront = term[0] ?? null;
  const tBack = term[term.length - 1] ?? null;
  // Read against the CHEAPEST expiry, not front against back: a term that
  // is dear at both ends (a 1DTE's gamma in front, a report at the back) is
  // not flat, and front-minus-back would call it so.
  const termRead = (() => {
    if (!tFront || !tBack || term.length < 2) return "Needs two expiries with an at-the-money pair.";
    const base = term.reduce((m, t) => (t.iv < m.iv ? t : m), term[0]);
    const frontPrem = tFront.iv - base.iv;
    const backPrem = tBack.iv - base.iv;
    const bits: string[] = [];
    if (frontPrem >= 3) {
      bits.push(`The front (${shortDate(tFront.expiry)}) prices ${frontPrem.toFixed(0)} points over the cheapest expiry (${shortDate(base.expiry)}): the next session is dear — a same-day expiry's gamma, not the term.`);
    }
    if (backPrem >= 3) {
      bits.push(`The back (${shortDate(tBack.expiry)}) prices ${backPrem.toFixed(0)} points over the cheapest: event premium sits there${o.earnings_move?.implied ? " — the report's expiry" : ""}; a long in ${shortDate(base.expiry)} does not pay for it, and does not cover it.`);
    }
    if (bits.length === 0) return "Flat across the term: no event priced in it. The 30-day figure stands for all of it.";
    return bits.join(" ");
  })();

  const st = o.structure ?? null;
  const contractRead = (() => {
    if (!st) return "No contract near 0.60 delta in the expiries read.";
    const tgt = o.targets?.[0];
    if (st.by === "r" && st.long_r != null && st.spread_r != null) {
      return `By R at the first target${tgt ? ` (${tgt.label} ${num(tgt.price)})` : ""}: the long makes ${st.long_r.toFixed(1)} R, the spread ${st.spread_r.toFixed(1)} R, so the ${st.kind}. R is the contract's value at the target less its value at the entry, after half the bid-ask, over what the stop costs — the option's own reward to risk, which the stock's hides.`;
    }
    return `${st.kind === "spread" ? "The spread" : "The long"}, by the premium rule${tgt ? "" : " — no first target to price an R against"}${st.long_r == null && st.spread_r == null && tgt ? " — the target sits beyond what the chain can price" : ""}: rich premium says the spread, cheap or fair says the long.`;
  })();

  const flowOi = (() => {
    if (!f) return "";
    const bits: string[] = [];
    if (f.unusual && f.vol_x != null) bits.push(`Volume ${f.vol_x.toFixed(1)}× its 20-session average: unusual — somebody is positioning today.`);
    if (f.oi_chg_calls != null && f.oi_chg_puts != null) {
      const c = f.oi_chg_calls;
      const p = f.oi_chg_puts;
      const side = Math.abs(c) >= Math.abs(p) ? ["calls", c] as const : ["puts", p] as const;
      bits.push(`Open interest since ${f.oi_prev_day ? shortDate(f.oi_prev_day) : "the previous session"}: calls ${c >= 0 ? "+" : ""}${compact(c)}, puts ${p >= 0 ? "+" : ""}${compact(p)} — ${side[1] >= 0 ? `new ${side[0]} being put on` : `${side[0]} being closed`}.`);
    }
    return bits.length ? " " + bits.join(" ") : "";
  })();

  // One line per expiry: the straddle as the figure, the date and the rule's
  // choice under it — sized so neither wraps in the figure column.
  const emFig = (e: typeof front) => (e ? `±$${e.straddle.toFixed(2)} · ${e.pct.toFixed(1)}%` : undefined);
  const emSub = (e: typeof front) =>
    e ? `to ${shortDate(e.expiry)}${e.dte === 0 ? " · 0DTE" : ""}${e.key === pick ? " · the pick" : ""}` : undefined;

  return (
    <div className="w-[min(620px,calc(100vw-24px))] px-4 py-3 text-ink">
      {/* ---- the name, as the block shows it ---- */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the options figures mean</span>
        <span className="fig text-[19px] leading-none text-ink">{sym}</span>
        {r.last != null && <span className="fig text-[13px] text-ink-2">{num(r.last, 2)}</span>}
        {side && (
          <span className={cn("qt-cap text-[10.5px]", side === "long" ? "text-call-fig" : "text-put-fig")}>{side}</span>
        )}
        <span className="fig ml-auto text-[11px] text-ink-3">
          Cboe{o.age_min != null ? ` · ${Math.round(o.age_min)}m old` : ""} · delayed 15m
        </span>
      </div>

      {/* ---- each figure, in the order the decision is made ---- */}
      <dl className="mt-2.5 grid grid-cols-[200px_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-[11.5px] leading-[1.5]">
        <Row
          k="IV30"
          v={o.iv30 != null ? `${o.iv30.toFixed(1)}%` : "—"}
          read={`The 30-day move the chain prices for ${sym}, annualised. The price of the option you are about to buy, not a forecast.`}
        />
        <Row
          k="RV20"
          v={o.rv20 != null ? `${o.rv20.toFixed(1)}%` : "—"}
          read={`What ${sym} has actually done over twenty sessions, close to close.`}
        />
        <Row
          k="IV / RV"
          v={o.iv_rv != null ? o.iv_rv.toFixed(2) : "—"}
          sub={o.premium ?? undefined}
          tone={o.premium ? premiumHue(o.premium) : undefined}
          read={premiumRead}
        />
        <Row
          k="IV rank"
          v={o.iv_rank != null ? `${Math.round(o.iv_rank)}` : "building"}
          sub={o.iv_rank == null ? `${o.iv_days} of 20 sessions` : o.iv_pct != null ? `pct ${Math.round(o.iv_pct)}` : undefined}
          read={rankRead}
        />
        <Row
          k="Expected move"
          v={emFig(front) ?? emFig(weekly) ?? "—"}
          sub={emSub(front) ?? emSub(weekly)}
          v2={front && weekly && weekly.key !== front.key ? emFig(weekly) : undefined}
          sub2={front && weekly && weekly.key !== front.key ? emSub(weekly) : undefined}
          read="The at-the-money straddle for each expiry: what the market pays for the move to that date, drawn on the chart as the band. A first target inside it is the realistic one; past it needs a catalyst. The band's edge is where a bought straddle breaks even — one option needs about half of it, and the 0.60-delta pick less again, since it is already in the money."
        />
        <Row
          k="Skew"
          v={o.skew != null ? `${o.skew >= 0 ? "+" : ""}${o.skew.toFixed(1)}` : "—"}
          sub="25Δ put − call"
          read={skewRead}
        />
        <Row
          k="Liquidity"
          v={liq.grade ?? "—"}
          sub={
            liq.spread_pct != null
              ? `spread ${liq.spread_pct.toFixed(1)}% · OI ${compact(liq.oi)}`
              : undefined
          }
          tone={liq.grade === "good" ? "text-call-fig" : liq.grade === "poor" ? "text-put-fig" : undefined}
          read={liqRead}
        />
        <Row
          k="Flow today"
          v={f && f.pc_vol != null ? `${f.lean ?? "—"} · P/C ${f.pc_vol.toFixed(2)}` : "—"}
          sub={f && f.pc_vol != null ? `C ${compact(f.call_vol)} · P ${compact(f.put_vol)}` : undefined}
          tone={f?.lean === "calls" ? "text-call-fig" : f?.lean === "puts" ? "text-put-fig" : undefined}
          read={flowRead + flowOi}
        />
        <Row
          k="Earnings"
          v={o.earnings_in ? shortDate(o.earnings_in) : "none inside"}
          tone={o.earnings_in ? "text-flip-fig" : undefined}
          read={earningsRead}
        />
        <Row
          k="Earnings move"
          v={implied ? `±${implied.pct.toFixed(1)}%` : avgAbs != null ? `±${avgAbs.toFixed(1)}% avg` : "—"}
          sub={implied ? `to ${shortDate(implied.expiry)}${implied.clean_pct != null ? ` · event ≈ ±${implied.clean_pct.toFixed(1)}%` : ""}` : em && em.realised.length ? "last reports, realised" : undefined}
          v2={implied && avgAbs != null ? `±${avgAbs.toFixed(1)}% realised` : undefined}
          sub2={implied && em && em.realised.length ? em.realised.map((m) => `${m.pct >= 0 ? "+" : ""}${m.pct.toFixed(1)}`).join(" · ") : undefined}
          read={earnMoveRead}
        />
        <Row
          k="IV by expiry"
          v={tFront ? `${tFront.iv.toFixed(0)}%` : "—"}
          sub={tFront ? `front · ${shortDate(tFront.expiry)}` : undefined}
          v2={tBack && tBack !== tFront ? `${tBack.iv.toFixed(0)}%` : undefined}
          sub2={tBack && tBack !== tFront ? `back · ${shortDate(tBack.expiry)}` : undefined}
          read={termRead}
        />
        <Row
          k="The contract"
          v={st ? (st.kind === "spread" ? "debit spread" : "long option") : "—"}
          sub={st ? (st.by === "r" ? "by R at the target" : "by the premium rule") : undefined}
          v2={st && st.long_r != null && st.spread_r != null ? `${st.long_r.toFixed(1)} R · ${st.spread_r.toFixed(1)} R` : undefined}
          sub2={st && st.long_r != null && st.spread_r != null ? "long · spread" : undefined}
          tone={st?.by === "r" ? "text-call-fig" : undefined}
          read={contractRead}
        />
      </dl>

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Rules, not advice. The contract under the block is the expiry rule&apos;s pick (Settings → Options), and risk
        per contract runs from the setup&apos;s entry to its stop. Chains are Cboe&apos;s, delayed about fifteen
        minutes.
      </p>
    </div>
  );
}

/** One figure: its label and number on the left (a second figure under it where there are two), what it means on the right. */
function Row({
  k,
  v,
  sub,
  v2,
  sub2,
  tone,
  read,
}: {
  k: string;
  v: string;
  sub?: string;
  v2?: string;
  sub2?: string;
  tone?: string;
  read: string;
}) {
  return (
    <>
      <dt className="flex min-w-0 flex-col gap-0.5">
        <span className="qt-cap text-[10px] text-ink-3">{k}</span>
        <span className={cn("fig text-[12.5px] leading-[1.3]", tone ?? "text-ink")}>{v}</span>
        {sub && <span className="fig text-[10.5px] leading-[1.3] text-ink-3">{sub}</span>}
        {v2 && <span className="fig mt-1 text-[12.5px] leading-[1.3] text-ink">{v2}</span>}
        {sub2 && <span className="fig text-[10.5px] leading-[1.3] text-ink-3">{sub2}</span>}
      </dt>
      <dd className="text-ink-2">{read}</dd>
    </>
  );
}
