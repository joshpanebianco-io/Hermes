"use client";

import { useCallback, useEffect, useState } from "react";
import type { PoolView, Watchlist } from "@/types/scanner";
import { age } from "@/lib/format";
import { segItem } from "@/lib/seg";

/**
 * The Scanner's list editor: the PINNED names (the owner's, always scanned)
 * over the POOL (sources/pool.py) that fills what they leave of the forty.
 *
 * TWO LISTS, ONE EDITOR. The pinned list is text, as it always was. The
 * pool's part is read-only by design — the collector decides it at the marks
 * — but the strip under the text says everything the reader would otherwise
 * ask the collector: whether promotion is on, how many names came through the
 * gates, which marks have run and which is next, what was promoted and why
 * (the reason on hover, a pin to keep it), and the names in play that did
 * not make the cut, so "why is X not on the list?" has its answer here.
 */

/** The scanner's cap — sources/scanner.MAX_SYMBOLS; the pool fills what the pinned list leaves of it. */
const CAP = 40;

export function WatchlistEditor({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [text, setText] = useState("");
  const [dflt, setDflt] = useState<string[]>([]);
  const [pool, setPool] = useState<PoolView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const take = useCallback((w: Watchlist) => {
    setText(w.symbols.join(" "));
    setDflt(w.default);
    setPool(w.pool ?? null);
    if (w.error) setErr(w.error);
  }, []);

  useEffect(() => {
    let live = true;
    void fetch("/api/scanner/watchlist", { cache: "no-store" })
      .then((r) => r.json() as Promise<Watchlist>)
      .then((w) => {
        if (live) take(w);
      })
      .catch((e: unknown) => live && setErr(e instanceof Error ? e.message : "could not read the list"));
    return () => {
      live = false;
    };
  }, [take]);

  const symbols = text
    .toUpperCase()
    .split(/[\s,;]+/)
    .map((s) => s.replace(/^\$/, "").trim())
    .filter(Boolean);
  const slots = Math.max(0, CAP - symbols.length);

  const save = async (list: string[]) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/scanner/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: list }),
      });
      const w = (await r.json()) as Watchlist;
      if (!r.ok || w.error) {
        setErr(w.error ?? `HTTP ${r.status}`);
        return;
      }
      if (w.rejected && w.rejected.length > 0) {
        // Saved, but not all of it — keep the editor open so the dropped
        // names are seen rather than silently missing from the list.
        take(w);
        setErr(`Saved without ${w.rejected.join(", ")} — not a valid ticker.`);
        return;
      }
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const switchPromotion = async (on: boolean) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/scanner/promotion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ on }),
      });
      const w = (await r.json()) as Watchlist;
      if (!r.ok || w.error) {
        setErr(w.error ?? `HTTP ${r.status}`);
        return;
      }
      setPool(w.pool ?? null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "could not switch promotion");
    } finally {
      setBusy(false);
    }
  };

  // A promoted name worth keeping goes into the text, and is saved with the rest.
  const pin = (sym: string) => {
    if (!symbols.includes(sym)) setText((t) => `${t.trim()} ${sym}`.trim());
  };

  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-ring bg-surface-2/40 px-6 py-3">
      <div className="flex items-baseline gap-3">
        <label htmlFor="scan-watchlist" className="qt-cap text-[10.5px] text-ink-3">
          Pinned
        </label>
        <p className="text-[11.5px] text-ink-3">
          Your names, always scanned — tickers separated by spaces or commas, up to {CAP}. SPY and QQQ are always
          fetched as the benchmarks; list them to see them as rows. What the pinned list leaves of the {CAP}, the pool
          fills with today&apos;s movers. New names appear within a minute or two.
        </p>
      </div>
      <textarea
        id="scan-watchlist"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        spellCheck={false}
        className="fig w-full resize-y rounded-[4px] border border-ring-2 bg-bg px-2.5 py-2 text-[12.5px] text-ink outline-none focus:border-ink-3"
      />
      <div className="flex items-center gap-2">
        <span className="fig text-[11px] text-ink-3">
          {symbols.length} pinned · {slots} {slots === 1 ? "slot" : "slots"} for the pool
        </span>
        {err && <span className="text-[11.5px] text-err">{err}</span>}
        <div className="ml-auto flex items-center gap-2">
          {dflt.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setText(dflt.join(" "))}
              {...segItem(false, { className: "border border-ring-2" })}
              title={dflt.join(" ")}
            >
              Reset to the Pine list
            </button>
          )}
          <button type="button" onClick={onCancel} {...segItem(false, { className: "border border-ring-2" })}>
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || symbols.length === 0}
            onClick={() => void save(symbols)}
            {...segItem(true, { className: "border border-ring-2 disabled:cursor-not-allowed disabled:opacity-40" })}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
      {pool && <PoolStrip pool={pool} pinned={symbols} busy={busy} onSwitch={switchPromotion} onPin={pin} />}
    </div>
  );
}

function PoolStrip({
  pool,
  pinned,
  busy,
  onSwitch,
  onPin,
}: {
  pool: PoolView;
  pinned: string[];
  busy: boolean;
  onSwitch: (on: boolean) => void;
  onPin: (sym: string) => void;
}) {
  const promoted = pool.promoted.filter((p) => !pinned.includes(p.symbol));
  const next = pool.top.filter((r) => !r.promoted && !pinned.includes(r.symbol)).slice(0, 6);
  const basis = pool.basis === "pre" ? "in the pre-market" : pool.basis === "day" ? "today" : "last session";
  const g = pool.gates;
  const gates = `Market cap $${Math.round(g.cap_usd / 1e9)}bn+ · $${Math.round(g.dollar_vol_usd / 1e6)}m+ traded a day · ATR ${g.atr_pct}%+ · $${g.price_usd}+ a share · promoted from ${g.min_score} points`;
  return (
    <div className="flex flex-col gap-1.5 border-t border-ring/60 pt-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">Pool</span>
        <button
          type="button"
          disabled={busy}
          onClick={() => onSwitch(!pool.on)}
          {...segItem(pool.on, { className: "border border-ring-2 disabled:cursor-not-allowed disabled:opacity-40" })}
          title={
            pool.on
              ? "Promotion is on: the pool fills the free slots at 08:00, 09:00, 09:25 and 10:00 ET. Click to turn it off and run the pinned list alone."
              : "Promotion is off: the pinned list alone. Click to turn it on — the pool reads again and runs today's latest mark."
          }
        >
          {pool.on ? "Promotion on" : "Promotion off"}
        </button>
        <span className="fig text-[11px] text-ink-3" title={gates}>
          {pool.ok
            ? `${pool.screened.toLocaleString()} names screened · ${pool.qualified} qualified`
            : (pool.error ?? "not read yet")}
          {pool.age_min != null && ` · read ${age(pool.age_min)}`}
          {pool.on && pool.marks_done.length > 0 && ` · marks ${pool.marks_done.join(", ")}`}
          {pool.on && pool.next_mark && ` · next ${pool.next_mark} ET`}
        </span>
        {pool.source === "stale" && (
          <span className="text-[11px] text-flip-fig" title={pool.error ?? undefined}>
            a stale copy — it ranks, it never promotes
          </span>
        )}
      </div>
      {pool.on && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11.5px] text-ink-3">
            {promoted.length > 0
              ? `Promoted today (${promoted.length}) —`
              : pool.marks_done.length > 0
                ? `Nothing promoted today: nothing in the pool scored ${g.min_score} or more at the marks.`
                : "Nothing promoted yet — the first mark is 08:00 ET."}
          </span>
          {promoted.map((p) => (
            <span
              key={p.symbol}
              className="fig inline-flex items-center gap-1.5 rounded-[3px] border border-ring-2 bg-bg px-1.5 py-0.5 text-[11.5px] text-ink"
              title={`${p.mark} ET · ${p.reason}`}
            >
              {p.symbol}
              <span className="text-ink-3">{p.score}</span>
              <button
                type="button"
                onClick={() => onPin(p.symbol)}
                className="hit text-[10.5px] text-ink-3 hover:text-ink"
                title="Keep it: add to the pinned list, then Save"
              >
                pin
              </button>
            </span>
          ))}
        </div>
      )}
      {next.length > 0 && (
        <p className="text-[11.5px] text-ink-3">
          In play {basis}, not on the list:{" "}
          {next.map((r, i) => (
            <span key={r.symbol} title={r.reason}>
              {i > 0 && " · "}
              <span className="fig text-ink-2">{r.symbol}</span> <span className="fig">{r.score}</span>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
