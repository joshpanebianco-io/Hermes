"use client";

import type { OptContract, OptionsCtx, OptionsFlow, ScanRow } from "@/types/scanner";
import { estTitle, optionsPick, premiumHue, shortDate, strike } from "@/components/panels/ScanTable";
import { Tick } from "@/components/ui/Tick";
import { OptionsFiguresPopover } from "@/components/vol/OptionsFigures";
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
  // What every figure's long form reads — the row, its chain, the rule's pick.
  const explain = { r, o, pick };
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
      {/*
       * EVERY FIGURE OPENS THE SAME LONG FORM (owner, 2026-10-22: "what they
       * mean for the stocks section"), the way every VIX figure opens the
       * bands: what each number says for this name's trade, read with the
       * name's own state — see OptionsFigures. The trigger is the figure
       * itself, so each is phrasing content inside the popover's button.
       */}
      <div className="grid grid-cols-5 gap-x-3">
        <OptionsFiguresPopover {...explain} className={TRIGGER}>
          <Fig label="IV30" v={o.iv30 != null ? `${o.iv30.toFixed(1)}%` : "—"} />
        </OptionsFiguresPopover>
        <OptionsFiguresPopover {...explain} className={TRIGGER}>
          <Fig label="RV20" v={o.rv20 != null ? `${o.rv20.toFixed(1)}%` : "—"} />
        </OptionsFiguresPopover>
        <OptionsFiguresPopover {...explain} className={TRIGGER}>
          <Fig
            label="IV / RV"
            v={o.iv_rv != null ? o.iv_rv.toFixed(2) : "—"}
            sub={o.premium ? <span className={cn("qt-cap text-[9.5px]", premiumHue(o.premium))}>{o.premium}</span> : null}
          />
        </OptionsFiguresPopover>
        <OptionsFiguresPopover {...explain} className={TRIGGER}>
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
        </OptionsFiguresPopover>
        <OptionsFiguresPopover {...explain} className={TRIGGER}>
          <Fig
            label="Skew"
            v={o.skew != null ? `${o.skew >= 0 ? "+" : ""}${o.skew.toFixed(1)}` : "—"}
            sub={<span className="text-[10.5px] text-ink-3">25Δ put − call</span>}
          />
        </OptionsFiguresPopover>
      </div>

      {/* expected moves */}
      <div className="flex flex-col gap-1">
        <p className="qt-cap text-[10.5px] text-ink-3">Expected move · the at-the-money straddle</p>
        {[front, weekly].filter(Boolean).map((e) => (
          <OptionsFiguresPopover
            key={e!.key}
            {...explain}
            className={cn(TRIGGER, "grid w-full grid-cols-[86px_minmax(0,1fr)_auto] items-baseline gap-x-3 text-[12px]")}
          >
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
          </OptionsFiguresPopover>
        ))}
        {/* THE EARNINGS NUMBER (owner, 2026-10-22): what the chain prices for
            the report against what the name did on its last few, and the
            term structure — where event premium shows as a near expiry priced
            above the ones behind it. Both open the same long form. */}
        {o.earnings_move && (o.earnings_move.implied || o.earnings_move.realised.length > 0) && (
          <OptionsFiguresPopover {...explain} className={cn(TRIGGER, "text-[12px]")}>
            <span className="qt-cap mr-2 text-[10.5px] text-ink-3">Earnings move</span>
            {o.earnings_move.implied && (
              <span className="fig text-ink">
                ±{o.earnings_move.implied.pct.toFixed(1)}%{" "}
                <span className="text-ink-3">
                  to {shortDate(o.earnings_move.implied.expiry)}
                  {o.earnings_move.implied.clean_pct != null && ` · event ≈ ±${o.earnings_move.implied.clean_pct.toFixed(1)}%`}
                </span>
              </span>
            )}
            {o.earnings_move.realised.length > 0 && (
              <span className="fig text-[11.5px] text-ink-3">
                {o.earnings_move.implied ? " · " : ""}realised{" "}
                {o.earnings_move.realised.map((m) => `${m.pct >= 0 ? "+" : ""}${m.pct.toFixed(1)}%`).join(", ")}
                {o.earnings_move.avg_abs != null && ` (avg ±${o.earnings_move.avg_abs.toFixed(1)}%)`}
              </span>
            )}
          </OptionsFiguresPopover>
        )}
        {o.term && o.term.length > 1 && (
          <OptionsFiguresPopover {...explain} className={cn(TRIGGER, "text-[11.5px]")}>
            <span className="qt-cap mr-2 text-[10.5px] text-ink-3">IV by expiry</span>
            <span className="fig text-ink-3">
              {o.term.slice(0, 4).map((t, i) => (
                <span key={t.expiry}>
                  {i > 0 && " · "}
                  {shortDate(t.expiry)} <span className="text-ink-2">{t.iv.toFixed(0)}</span>
                </span>
              ))}
            </span>
          </OptionsFiguresPopover>
        )}
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
        {lean && (
          <p className="text-[12px] leading-[1.5] text-ink-3">
            {lean}
            {/* The structure the engine picks, by R at the first target when
                both contracts are priced (optcalc.structure_pick). */}
            {o.structure?.by === "r" && o.structure.long_r != null && o.structure.spread_r != null && (
              <>
                {" "}
                By R at the first target the {o.structure.kind} pays better:{" "}
                <span className="fig text-ink-2">{o.structure.long_r.toFixed(1)} R</span> long against{" "}
                <span className="fig text-ink-2">{o.structure.spread_r.toFixed(1)} R</span> spread.
              </>
            )}
          </p>
        )}
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
        {/* Today's volume against the name's own 20-session average, and the
            change in open interest since the previous session, each side —
            from the OI log (sources/options.OiLog). */}
        {f.vol_x != null && (
          <span
            className={cn("ml-2", f.unusual ? "qt-cap text-[10px] text-flip-fig" : "fig text-ink-3")}
            title={`Today's chain volume against its 20-session average (${f.vol_days ?? 0} sessions logged)`}
          >
            {f.unusual ? `unusual ${f.vol_x.toFixed(1)}×` : `${f.vol_x.toFixed(1)}× avg`}
          </span>
        )}
        {(f.oi_chg_calls != null || f.oi_chg_puts != null) && (
          <span className="fig ml-2 text-ink-3" title={`Open interest since ${f.oi_prev_day ?? "the previous session"}, calls and puts`}>
            OI {signedCompact(f.oi_chg_calls)}C · {signedCompact(f.oi_chg_puts)}P
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
              {t.oi_chg != null && (
                <span className="text-ink-4" title="Open interest since the previous session">
                  {" "}
                  ({signedCompact(t.oi_chg)} OI)
                </span>
              )}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

/** "+12.4K", "−3.1K", "0" — a change in open interest, signed and compact. */
function signedCompact(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v === 0) return "0";
  return `${v > 0 ? "+" : "−"}${compact(Math.abs(v))}`;
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
      {/* THE REWARD HALF (owner, 2026-10-22): the contract priced at the first
          target by the same maths as the stop, and the option's own R. Red
          under one R; "better R" marks the structure the engine picks. */}
      {c.r_multiple != null && c.target_price != null && c.target_mid != null && (
        <p className="mt-1 text-[11.5px] text-ink-2">
          Worth about <span className="fig text-ink">${c.target_mid.toFixed(2)}</span> at{" "}
          {c.target_label} <span className="fig">{num(c.target_price)}</span>
          {" · "}
          <span className={cn("fig", c.r_multiple >= 1 ? "text-ink" : "text-put-fig")}>{c.r_multiple.toFixed(1)} R</span>
          {c.better_r && (
            <span className="qt-cap ml-2 text-[9.5px] text-call-fig" title="The structure the engine picks for this expiry, by R">
              better R
            </span>
          )}
          {c.target_basis?.startsWith("intrinsic") && (
            <span className="ml-1.5 text-[10px] text-ink-3" title={c.target_basis}>
              intrinsic floor
            </span>
          )}
        </p>
      )}
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

/** The figure's trigger: a little hit area round it, the row's own grid where it is one. */
const TRIGGER = "-mx-1.5 block min-w-0 px-1.5 py-0.5";

/** Spans, not paragraphs: a figure sits inside its popover's <button>, which takes phrasing content only. */
function Fig({ label, v, sub }: { label: string; v: string; sub?: React.ReactNode }) {
  return (
    <span className="block min-w-0">
      <span className="qt-cap mb-1 block text-[10px] text-ink-3">{label}</span>
      <span className="fig block text-[14px] text-ink">{v}</span>
      {sub && <span className="mt-0.5 block">{sub}</span>}
    </span>
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
