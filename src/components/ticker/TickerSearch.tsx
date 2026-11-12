"use client";

import { useEffect, useRef, useState } from "react";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { capShort } from "@/components/panels/ScanWide";
import { cn } from "@/lib/cn";
import { OPEN_SEARCH_EVENT, openTicker } from "@/lib/ticker";
import { lookupFor, lookupVerdict, matchRank, suggest, type StockHit, type Suggestion } from "@/lib/tickerSearch";

/**
 * Ctrl+K: any ticker or company, from any tab, into the slide-out.
 *
 * IT SHOWS WHAT IT KNOWS AS YOU TYPE, AND OPENS ONLY WHAT TRADES (owner, 2026-11-11; the
 * whole account is in lib/tickerSearch). The rows are the wide scan's stocks ($300m up)
 * and the funds the terminal reads, which are listed in the page and so appear on the
 * first letter whatever the collector is doing. Enter opens the lit row. Text that has a
 * ticker's shape and is no row gets one more row, "Check XYZ": opening that asks the
 * collector whether the symbol trades, and one that does not is said to be nothing and
 * is not opened. Until 2026-11-11 Enter opened the slide-out for any text at all.
 *
 * WAITING IS NOT "NOTHING MATCHES". The line under the box says which it is: searching,
 * no match, or the search not answering (and why).
 */

type Row = (Suggestion & { check?: false }) | { check: true; sym: string };
type Look = { sym: string; state: "asking" } | { sym: string; state: "missing" } | { sym: string; state: "unknown"; why: string };

export function TickerSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<StockHit[]>([]);
  // What the collector's list said for the text now in the box: nothing asked yet,
  // asked and waiting, answered, or not answering.
  const [list, setList] = useState<{ state: "idle" | "waiting" | "answered" } | { state: "down"; why: string }>({ state: "idle" });
  const [i, setI] = useState(0);
  const [look, setLook] = useState<Look | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const asked = useRef(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_SEARCH_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_SEARCH_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setHits([]);
      setList({ state: "idle" });
      setLook(null);
      setI(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    // New text: the last check was about other text, and the lit row starts at the top.
    setLook(null);
    setI(0);
    asked.current += 1;
    const text = q.trim();
    if (!open || !text) {
      setHits([]);
      setList({ state: "idle" });
      return;
    }
    setList({ state: "waiting" });
    const stop = new AbortController();
    const id = setTimeout(() => {
      void fetch(`/api/scanner/search?q=${encodeURIComponent(text)}`, { cache: "no-store", signal: stop.signal })
        .then((r) => r.json() as Promise<{ results?: StockHit[]; offline?: { reason: string } }>)
        .then((d) => {
          if (stop.signal.aborted) return;
          if (d.offline) {
            setHits([]);
            setList({ state: "down", why: d.offline.reason });
          } else {
            setHits(d.results ?? []);
            setList({ state: "answered" });
          }
        })
        .catch((e: unknown) => {
          if (stop.signal.aborted) return;
          setHits([]);
          setList({ state: "down", why: e instanceof Error ? e.message : "request failed" });
        });
    }, 90);
    return () => {
      stop.abort();
      clearTimeout(id);
    };
  }, [q, open]);

  if (!open) return null;

  const text = q.trim();
  // While the answer for this text is on its way, the stocks answered for the text
  // before it stay, those of them that still match: "nv" then "nvd" keeps NVIDIA on
  // screen between the two answers instead of emptying the box at every letter.
  const found = suggest(text, list.state === "answered" ? hits : hits.filter((h) => matchRank(text, h.sym, h.name) !== null));
  const check = list.state === "waiting" ? null : lookupFor(text, found);
  const rows: Row[] = check ? [...found, { check: true, sym: check }] : found;
  const lit = Math.min(i, Math.max(0, rows.length - 1));

  const choose = (sym: string) => {
    openTicker(sym);
    setOpen(false);
  };

  /** Ask the collector whether the symbol trades; open it only on a yes. */
  const verify = (sym: string) => {
    const mine = ++asked.current;
    setLook({ sym, state: "asking" });
    void fetch(`/api/scanner/name/${encodeURIComponent(sym)}`, { cache: "no-store" })
      .then((r) => r.json() as Promise<{ ok?: boolean; error?: string | null; offline?: { reason: string } }>)
      .catch(() => null)
      .then((d) => {
        if (mine !== asked.current) return;
        const v = lookupVerdict(d);
        if (v.kind === "found") choose(sym);
        else if (v.kind === "missing") setLook({ sym, state: "missing" });
        else setLook({ sym, state: "unknown", why: v.why });
      });
  };

  const act = (row: Row | undefined) => {
    if (!row) return;
    if (row.check) {
      if (look?.sym === row.sym && look.state === "asking") return;
      verify(row.sym);
    } else {
      choose(row.sym);
    }
  };

  const note = !text
    ? "Any US stock from $300m up, and the funds the terminal reads. ↑ ↓ to move, Enter to open, Esc to close."
    : list.state === "waiting" && rows.length === 0
      ? "Searching…"
      : list.state === "down"
        ? `The stock list is not answering (${list.why}).${found.length ? " Funds only for now." : ""}`
        : rows.length === 0
          ? "No stock, fund or company matches that."
          : null;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-[12vh]" onMouseDown={() => setOpen(false)}>
      <div className="w-[min(560px,calc(100vw-32px))] overflow-hidden rounded-[6px] border border-ring-2 bg-surface shadow-[0_18px_60px_rgba(0,0,0,.6)] qt:rounded-[4px]" onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label="Search for a ticker">
        <input
          ref={input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ticker or company…"
          spellCheck={false}
          autoComplete="off"
          role="combobox"
          aria-expanded={rows.length > 0}
          aria-controls="ticker-search-rows"
          aria-autocomplete="list"
          className="w-full border-b border-ring bg-transparent px-4 py-3 text-[14px] text-ink outline-none placeholder:text-ink-3"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setI(Math.min(lit + 1, rows.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setI(Math.max(lit - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              // Only a row opens: a stock on the list, a fund, or a symbol the collector
              // has just said trades. Text with no row opens nothing.
              act(rows[lit]);
            }
          }}
        />
        {rows.length > 0 && (
          <ul id="ticker-search-rows" role="listbox" className="max-h-[50vh] overflow-y-auto py-1">
            {rows.map((h, k) => (
              <li key={h.check ? `check:${h.sym}` : h.sym} role="option" aria-selected={k === lit}>
                {h.check ? (
                  <button type="button" onMouseEnter={() => setI(k)} onClick={() => act(h)} className={cn("flex w-full items-center gap-2.5 border-t border-ring px-4 py-2 text-left", k === lit && "bg-surface-2")}>
                    <span className="w-[18px] shrink-0 text-center text-[13px] text-ink-3" aria-hidden>
                      ?
                    </span>
                    <span className="w-[64px] shrink-0 text-[13px] font-semibold text-ink">{h.sym}</span>
                    <span className="min-w-0 flex-1 text-[12.5px] text-ink-2">
                      {look?.sym !== h.sym
                        ? "Not on the list. Check whether it trades"
                        : look.state === "asking"
                          ? "Checking…"
                          : look.state === "missing"
                            ? "Nothing trades under this symbol. Not opened."
                            : `Could not check (${look.why}). Not opened.`}
                    </span>
                    {(look?.sym !== h.sym || look.state === "unknown") && <span className="fig shrink-0 rounded-[3px] border border-ring-2 px-1.5 text-[10px] text-ink-3">Enter</span>}
                  </button>
                ) : (
                  <button type="button" onMouseEnter={() => setI(k)} onClick={() => act(h)} className={cn("flex w-full items-center gap-2.5 px-4 py-1.5 text-left", k === lit && "bg-surface-2")}>
                    <TickerLogo sym={h.sym} size={18} />
                    <span className="w-[64px] shrink-0 text-[13px] font-semibold text-ink">{h.sym}</span>
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">{h.name}</span>
                    {h.kind === "fund" ? <span className="qt-cap text-[9.5px] text-ink-3">Fund</span> : h.sector && <span className="qt-cap text-[9.5px] text-ink-3">{h.sector}</span>}
                    <span className="fig w-[62px] shrink-0 text-right text-[11px] text-ink-3">{h.kind === "fund" ? "" : capShort(h.cap)}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {note && <p className={cn("px-4 py-3 text-[12px] text-ink-3", rows.length > 0 && "border-t border-ring")}>{note}</p>}
      </div>
    </div>
  );
}
