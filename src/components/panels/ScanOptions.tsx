"use client";

import type { OptContract, OptionsCtx, OptionsFlow, ScanRow } from "@/types/scanner";
import { estTitle, optionsPick, premiumHue, shortDate, strike } from "@/components/panels/ScanTable";
import { Tick } from "@/components/ui/Tick";
import { useOptionsPrefs } from "@/lib/optionsPrefs";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The selected name's options — how the owner actually trades the stocks desk
 * (owner, 2026-10-13: "the separate stocks and ETFs that we use for options").
 *
 * READ IN THE ORDER THE DECISION IS MADE: is premium cheap or rich (implied
 * against realised), how far does the market expect it to go (the straddle),
 * can it be traded (the spread), is there a reason not to hold it (earnings
 * inside the expiry) — and then the contract, a long option or a debit spread,
 * with what it puts at risk to the setup's own stop.
 *
 * THE CONTRACT IS A SUGGESTION FROM RULES, AND SAYS WHICH. The strike nearest
 * 0.60 delta (enough of the move, less theta than at-the-money's coin flip),
 * the spread selling the 0.30 delta; which expiry is the collector's one rule
 * (`o.pick`), marked on the page. Risk runs from the setup's ENTRY to its stop:
 * the contract re-marked to each through delta and gamma, plus half its
 * bid-ask — an approximation that ignores time, named here, not hidden.
 * Cboe's chains are delayed fifteen minutes; the age is on the page.
 */

export function ScanOptions({ r }: { r: ScanRow }) {
  const o = r.options;
  const prefs = useOptionsPrefs();
  return (
    <section className="px-6 py-4" aria-label={`${r.sym} options`}>
      <div className="mb-2.5 flex items-baseline gap-2">
        <h3 className="text-[13.5px] font-semibold text-ink">Options</h3>
        {o?.asof && (
          <span className="fig ml-auto text-[11px] text-ink-3" title="Cboe's delayed chain — about fifteen minutes behind">
            Cboe · {etTime(o.asof)} ET{o.age_min != null ? ` · ${Math.round(o.age_min)}m` : ""}
          </span>
        )}
      </div>
      {!o || !o.ok ? (
        <p className="text-[12px] text-ink-3">{o?.error ?? "No chain yet — the options job reads Cboe a few names at a time."}</p>
      ) : (
        <Body r={r} o={o} budget={prefs.budget} zeroDte={prefs.zeroDte} />
      )}
    </section>
  );
}

function Body({ r, o, budget, zeroDte }: { r: ScanRow; o: OptionsCtx; budget: number | null; zeroDte: boolean }) {
  const front = o.em.find((e) => e.key === "front");
  const weekly = o.em.find((e) => e.key === "weekly");
  // 0DTE off in Settings: no same-day contract on any name — the weekly instead.
  const hideFront = !zeroDte && front?.dte === 0;
  const contracts = o.contracts.filter((c) => !(hideFront && c.key === "front"));
  const pick = optionsPick(o, zeroDte);
  // The pick first: it is the contract the rule says to trade.
  const keys = [...new Set(contracts.map((c) => c.key))].sort((a, b) => Number(b === pick) - Number(a === pick));
  const lean =
    o.premium === "rich"
      ? "Premium is rich against realised volatility — the debit spread sells some of it back."
      : o.premium === "cheap"
        ? "Premium is cheap against realised volatility — a long option keeps the convexity."
        : o.premium === "fair"
          ? "Premium is fairly priced against realised volatility."
          : null;

  return (
    <div className="flex flex-col gap-4">
      {/* volatility */}
      <div className="grid grid-cols-5 gap-x-3">
        <Fig label="IV30" v={o.iv30 != null ? `${o.iv30.toFixed(1)}%` : "—"} />
        <Fig label="RV20" v={o.rv20 != null ? `${o.rv20.toFixed(1)}%` : "—"} />
        <Fig
          label="IV / RV"
          v={o.iv_rv != null ? o.iv_rv.toFixed(2) : "—"}
          sub={o.premium ? <span className={cn("qt-cap text-[9.5px]", premiumHue(o.premium))}>{o.premium}</span> : null}
        />
        <Fig
          label="IV rank"
          v={o.iv_rank != null ? `${Math.round(o.iv_rank)}` : "—"}
          sub={
            o.iv_rank == null ? (
              <span className="text-[10.5px] text-ink-3" title="IV rank needs twenty logged sessions of IV30">
                building · {o.iv_days}/20d
              </span>
            ) : o.iv_pct != null ? (
              <span className="text-[10.5px] text-ink-3">pct {Math.round(o.iv_pct)}</span>
            ) : null
          }
        />
        <Fig
          label="Skew"
          v={o.skew != null ? `${o.skew >= 0 ? "+" : ""}${o.skew.toFixed(1)}` : "—"}
          sub={<span className="text-[10.5px] text-ink-3">25Δ put − call</span>}
        />
      </div>

      {/* expected moves */}
      <div className="flex flex-col gap-1">
        <p className="qt-cap text-[10.5px] text-ink-3">Expected move · the at-the-money straddle</p>
        {[front, weekly].filter(Boolean).map((e) => (
          <div key={e!.key} className="grid grid-cols-[86px_minmax(0,1fr)_auto] items-baseline gap-x-3 text-[12px]">
            <span className="text-ink-2">
              {e!.dte === 0 ? "0DTE" : e!.key === "front" ? "Front" : "Weekly"}{" "}
              <span className="text-[11px] text-ink-3">{shortDate(e!.expiry)}</span>
            </span>
            <span className="fig text-ink">
              ±${e!.straddle.toFixed(2)} <span className="text-ink-3">· ±{e!.pct.toFixed(2)}%</span>
            </span>
            <span className="fig text-[11.5px] text-ink-3">
              {num(e!.lo)} – {num(e!.hi)}
            </span>
          </div>
        ))}
      </div>

      {/* liquidity and warnings */}
      <div className="flex flex-col gap-1.5 text-[12px]">
        <p className="text-ink-2">
          <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Liquidity</span>
          <span
            className={cn(
              "qt-cap text-[10.5px]",
              o.liquidity.grade === "good" ? "text-call-fig" : o.liquidity.grade === "poor" ? "text-put-fig" : "text-ink-2",
            )}
          >
            {o.liquidity.grade ?? "—"}
          </span>
          <span className="fig ml-2 text-ink-3">
            spread {o.liquidity.spread_pct != null ? `${o.liquidity.spread_pct.toFixed(1)}%` : "—"} · OI {compact(o.liquidity.oi)} · vol{" "}
            {compact(o.liquidity.volume)}
          </span>
        </p>
        {o.flow && o.flow.pc_vol != null && <Flow f={o.flow} />}
        {o.earnings_in && (
          <Warn>
            Earnings land before the {shortDate(o.earnings_in)} expiry — implied volatility collapses after the report, so
            a long option bought into it pays for a move it may not keep.
          </Warn>
        )}
        {o.liquidity.grade === "poor" && <Warn>Wide spreads — the fill alone can cost a good part of the move.</Warn>}
        {lean && <p className="text-[12px] leading-[1.5] text-ink-3">{lean}</p>}
      </div>

      {/* the contract */}
      {contracts.length === 0 ? (
        <p className="text-[12px] text-ink-3">
          {r.score.side ? "No contract near 0.60 delta in the expiries read." : "No side yet — nothing to suggest until the levels pick one."}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {keys.map((k) => (
            <div key={k} className="flex flex-col gap-2">
              <p className="qt-cap text-[10.5px] text-ink-3">
                {k === "front" ? "Front expiry" : "Weekly"} · {r.score.side === "short" ? "puts" : "calls"}
                {k === pick && (
                  <span className="ml-2 text-call-fig" title="The expiry the desk's rule picks for this name — Settings → Options">
                    the pick
                  </span>
                )}
              </p>
              {contracts
                .filter((c) => c.key === k)
                .map((c) => (
                  <ContractCard key={`${c.key}-${c.kind}`} c={c} budget={budget} />
                ))}
            </div>
          ))}
        </div>
      )}

      <p className="text-[10.5px] leading-[1.5] text-ink-3">
        Risk per contract runs from the setup&apos;s entry to its stop: the contract re-marked to each through delta and
        gamma, plus half its bid-ask to get out — an approximation that ignores time decay. Chains are Cboe&apos;s,
        delayed about fifteen minutes. Rules, not advice.
      </p>
    </div>
  );
}

/**
 * Today's flow: put against call volume, how much of it is fresh (volume over
 * open interest), and the strikes it is concentrated in. A lean that agrees
 * with the setup's side is support for it; one against it is a reason for a
 * smaller size or a spread — it never decides the trade on its own.
 */
function Flow({ f }: { f: OptionsFlow }) {
  const lean = f.lean === "calls" ? "text-call-fig" : f.lean === "puts" ? "text-put-fig" : "text-ink-2";
  return (
    <div className="flex flex-col gap-1">
      <p className="text-ink-2">
        <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Flow today</span>
        <span className="fig">
          calls {compact(f.call_vol)} · puts {compact(f.put_vol)} · P/C{" "}
          <span className="text-ink">{f.pc_vol != null ? f.pc_vol.toFixed(2) : "—"}</span>
        </span>
        {f.lean && <span className={cn("qt-cap ml-2 text-[10px]", lean)}>{f.lean}</span>}
        {f.vol_oi != null && (
          <span className="fig ml-2 text-ink-3" title="Volume as a share of open interest — above about 0.5, today's trading is mostly fresh positions">
            vol/OI {f.vol_oi.toFixed(2)}
          </span>
        )}
      </p>
      {f.top.length > 0 && (
        <p className="fig text-[11.5px] text-ink-3">
          busiest{" "}
          {f.top.map((t, i) => (
            <span key={`${t.strike}${t.right}${t.expiry}`}>
              {i > 0 && " · "}
              <span className={t.right === "C" ? "text-call-fig" : "text-put-fig"}>
                {strike(t.strike)}
                {t.right}
              </span>{" "}
              {shortDate(t.expiry)} {compact(t.volume)}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function ContractCard({ c, budget }: { c: OptContract; budget: number | null }) {
  const hue = c.right === "C" ? "text-call-fig" : "text-put-fig";
  const size = budget != null && c.risk_per_contract ? Math.floor(budget / c.risk_per_contract) : null;
  return (
    <div className="rounded-[4px] border border-ring-2 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="qt-cap text-[10px] text-ink-3">{c.kind === "long" ? "Long" : "Debit spread"}</span>
        <span className={cn("fig text-[13px] font-semibold", hue)}>
          {c.kind === "spread" ? `${strike(c.strike)} / ${strike(c.short_strike)}` : strike(c.strike)}
          {c.right}
        </span>
        <span className="fig text-[12px] text-ink-2">
          {shortDate(c.expiry)} · {c.dte === 0 ? "0DTE" : `${c.dte}d`}
        </span>
        <span className="ml-auto flex items-baseline gap-1" title={estTitle(c) ?? undefined}>
          {c.est_mid != null && <span className="qt-cap text-[9.5px] text-ink-3">est</span>}
          <Tick value={`$${(c.est_mid ?? c.mid).toFixed(2)}`} className="fig text-[13px] text-ink" />
        </span>
      </div>
      {c.est_mid != null && c.quote_spot != null && (
        <p className="fig mt-0.5 text-right text-[10.5px] text-ink-3">
          quoted ${c.mid.toFixed(2)} at ${c.quote_spot.toFixed(2)}
        </p>
      )}
      <p className="fig mt-1 text-[11.5px] text-ink-3">
        {Math.abs(c.est_delta ?? c.delta).toFixed(2)}Δ
        {c.theta != null && ` · θ ${c.theta.toFixed(2)}${c.kind === "spread" ? " net" : ""}`}
        {c.iv != null && ` · IV ${c.iv.toFixed(0)}${c.short_iv != null ? ` / ${c.short_iv.toFixed(0)}` : ""}%`}
        {` · ${c.bid.toFixed(2)} / ${c.ask.toFixed(2)}`}
        {c.spread_pct != null && ` (${c.spread_pct.toFixed(1)}%)`}
        {c.max_value != null && ` · worth up to $${c.max_value.toFixed(2)}`}
      </p>
      <p className="mt-1 text-[11.5px] text-ink-2">
        {c.risk_per_contract != null ? (
          <>
            About <span className="fig text-ink">${Math.round(c.risk_per_contract)}</span> at risk per contract
            {c.stock_risk != null && <span className="text-ink-3"> to a ${c.stock_risk.toFixed(2)} stock stop</span>}
            {size != null && (
              <>
                {" · "}
                <span className={cn("fig", size > 0 ? "text-ink" : "text-put-fig")}>{size}</span> for a ${budget} budget
              </>
            )}
            {c.stock_entry != null && c.stock_stop != null && (
              <span className="mt-0.5 block text-[10.5px] text-ink-3" title={c.risk_basis ?? undefined}>
                entry <span className="fig">{num(c.stock_entry)}</span> → stop <span className="fig">{num(c.stock_stop)}</span>
                {c.risk_basis && ` · ${c.risk_basis}`}
                {c.entry_mid != null && (
                  <>
                    {" · "}about <span className="fig">${c.entry_mid.toFixed(2)}</span> at the entry
                  </>
                )}
              </span>
            )}
          </>
        ) : (
          <span className="text-ink-3">No stop to size against yet.</span>
        )}
      </p>
      <p className="mt-1 text-[10.5px] text-ink-3">
        <span className="fig select-all">{c.symbol}</span>
        {c.short_symbol && (
          <>
            {" / "}
            <span className="fig select-all">{c.short_symbol}</span>
          </>
        )}
      </p>
    </div>
  );
}

function Fig({ label, v, sub }: { label: string; v: string; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="qt-cap mb-1 text-[10px] text-ink-3">{label}</p>
      <p className="fig text-[14px] text-ink">{v}</p>
      {sub && <div className="mt-0.5">{sub}</div>}
    </div>
  );
}

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex gap-2 text-[12px] leading-[1.5] text-ink-2">
      <span aria-hidden className="mt-[6px] h-[6px] w-[6px] shrink-0 rounded-[1px] bg-flip-fig" />
      <span>{children}</span>
    </p>
  );
}

const etTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" });
