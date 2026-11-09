"use client";

import { useEffect, useRef, useState } from "react";
import type { SearchHit } from "@/types/scanner";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { capShort } from "@/components/panels/ScanWide";
import { cn } from "@/lib/cn";
import { OPEN_SEARCH_EVENT, openTicker } from "@/lib/ticker";

/**
 * Ctrl+K: any ticker or company, from any tab, into the slide-out.
 *
 * Reads the wide scan's list, so it knows every US stock from $300m up. A symbol it
 * does not know still opens on Enter: the chart will say if Yahoo does not either.
 */
export function TickerSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [i, setI] = useState(0);
  const input = useRef<HTMLInputElement | null>(null);

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
      setI(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open || !q.trim()) {
      setHits([]);
      return;
    }
    let live = true;
    const id = setTimeout(() => {
      void fetch(`/api/scanner/search?q=${encodeURIComponent(q.trim())}`, { cache: "no-store" })
        .then((r) => r.json() as Promise<{ results?: SearchHit[] }>)
        .then((d) => {
          if (live) {
            setHits(d.results ?? []);
            setI(0);
          }
        })
        .catch(() => {});
    }, 90);
    return () => {
      live = false;
      clearTimeout(id);
    };
  }, [q, open]);

  if (!open) return null;

  const choose = (sym: string) => {
    openTicker(sym);
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-[12vh]" onMouseDown={() => setOpen(false)}>
      <div className="w-[min(560px,calc(100vw-32px))] overflow-hidden rounded-[6px] border border-ring-2 bg-surface shadow-[0_18px_60px_rgba(0,0,0,.6)] qt:rounded-[4px]" onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label="Search for a ticker">
        <input
          ref={input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ticker or company…"
          spellCheck={false}
          className="w-full border-b border-ring bg-transparent px-4 py-3 text-[14px] text-ink outline-none placeholder:text-ink-3"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setI((v) => Math.min(v + 1, hits.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setI((v) => Math.max(v - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              const pick = hits[i]?.sym ?? q.trim().toUpperCase();
              if (/^[A-Z0-9][A-Z0-9.-]{0,9}$/.test(pick)) choose(pick);
            }
          }}
        />
        {hits.length > 0 ? (
          <ul className="max-h-[50vh] overflow-y-auto py-1">
            {hits.map((h, k) => (
              <li key={h.sym}>
                <button type="button" onMouseEnter={() => setI(k)} onClick={() => choose(h.sym)} className={cn("flex w-full items-center gap-2.5 px-4 py-1.5 text-left", k === i && "bg-surface-2")}>
                  <TickerLogo sym={h.sym} size={18} />
                  <span className="w-[64px] shrink-0 text-[13px] font-semibold text-ink">{h.sym}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">{h.name}</span>
                  {h.sector && <span className="qt-cap text-[9.5px] text-ink-3">{h.sector}</span>}
                  <span className="fig w-[62px] shrink-0 text-right text-[11px] text-ink-3">{capShort(h.cap)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3 text-[12px] text-ink-3">{q.trim() ? "Nothing matches. Enter opens it as a ticker anyway." : "Any US stock from $300m up. ↑ ↓ to move, Enter to open, Esc to close."}</p>
        )}
      </div>
    </div>
  );
}
