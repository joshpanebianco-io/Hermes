"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { OPEN_ASK_EVENT, useAskFocus } from "@/lib/ask/open";
import { GREETING, suggestionsFor } from "@/lib/ask/suggest";
import { readNdjson, shortModel } from "@/lib/ask/stream";
import { HelmInline } from "@/components/ui/HelmLoader";
import { cn } from "@/lib/cn";
import { Markdownish } from "./Markdownish";

/**
 * Hermes — the terminal's assistant, in a panel beside the page (owner,
 * 2026-10-14: "a chatbot that uses our llm model that we can ask it to explain
 * anything … with some pre selection we can click on depending on what
 * section we're in, like gexygen has"). GEXYGEN's assistant, ported: the same
 * mechanism, HERMES's own words and data.
 *
 * MOUNTED ONCE, OPENED BY EVENT — the rail's Ask key, the A key, and
 * `askHermes()` from anywhere. Closing HIDES it rather than unmounting it, so
 * a reader who closes it to look at a panel and reopens it finds their thread.
 *
 * NOT MODAL. A second reader beside the page: no overlay, focus is not
 * trapped, and Escape closes it only when the panel itself has focus.
 *
 * WHAT TRAVELS WITH A QUESTION: the tab on screen, the Scanner's selected
 * name, and the thread so far without the greeting. The route reads the
 * desk's live digest from the collector and streams NDJSON back, applied to
 * the pending reply line by line, so the answer reads as it is written.
 *
 * THE SECTION'S QUESTIONS STAY ON THE PAGE, above the box, not just before
 * the first question — switch from the Macro tab to the Scanner mid-thread
 * and the openers follow you there.
 *
 * THE UNVERIFIED LINE is the notes' rule kept: every numeral in an answer is
 * checked against the data the model was shown, and any it cannot find is
 * named under the answer — shown and marked, never passed off.
 *
 * ON THE HERMES TAB IT STANDS ASIDE (2026-10-30): the page is already Hermes,
 * with the whole terminal behind it, so the Ask key and A focus that page's
 * box (HermesTab) and this panel stays shut.
 */

interface Msg {
  id: number;
  role: "user" | "assistant";
  text: string;
  pending?: boolean;
  /** Reasoning before speaking — so the wait has a word on it. */
  thinking?: boolean;
  error?: string | null;
  unverified?: string[];
  /** Which model actually answered — the chain falls through on the free tier. */
  model?: string | null;
  ms?: number;
}

const HELLO: Msg = { id: 0, role: "assistant", text: GREETING };

/** A speech bubble — drawn, because one 16px glyph is not worth a dependency. */
export function AskGlyph({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className={cn("h-[13px] w-[13px] shrink-0", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M13.5 9.5a1.8 1.8 0 0 1-1.8 1.8H6.4L3.3 13.7v-2.4h-.8A1.8 1.8 0 0 1 .7 9.5v-6A1.8 1.8 0 0 1 2.5 1.7h9.2a1.8 1.8 0 0 1 1.8 1.8z" />
      <path d="M4.4 4.9h5.6M4.4 7.3h3.6" />
    </svg>
  );
}

/** `tab` is the key the collector knows (lib/tabs.ts askTab): Analysis arrives as its half. */
export function AskPanel({ tab }: { tab: string }) {
  const focus = useAskFocus();
  const sym = tab === "scanner" ? focus : null;

  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([HELLO]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<{ enabled: boolean; model: string } | null>(null);
  const nextId = useRef(1);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // The thread as of the last render, for a send that must not close over a stale list.
  const threadRef = useRef(messages);
  threadRef.current = messages;
  // The tab as of the last render, for the listener below, which is bound once.
  const tabRef = useRef(tab);
  tabRef.current = tab;

  // Open on the shared event; toggle when it fires while open. An event that
  // carries a question (askHermes) opens and puts the question in the box.
  // On the Hermes tab the event is that page's to answer.
  useEffect(() => {
    const onOpen = (e: Event) => {
      if (tabRef.current === "hermes") return;
      const q = (e as CustomEvent<{ question?: string }>).detail?.question;
      if (q) {
        setOpen(true);
        setInput(q);
        return;
      }
      setOpen((o) => !o);
    };
    window.addEventListener(OPEN_ASK_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_ASK_EVENT, onOpen);
  }, []);

  // Focus the box on open, and learn which model answers the first time.
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => inputRef.current?.focus());
    if (!config) {
      fetch("/api/ask", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((c: { enabled: boolean; model: string } | null) => c && setConfig(c))
        .catch(() => {});
    }
    return () => cancelAnimationFrame(raf);
  }, [open, config]);

  // The box fits its question however it got there — typed, put there by
  // askHermes, or emptied by a send. Measured only while the panel shows.
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el || !open) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 110)}px`;
  }, [input, wide, open]);

  // Keep the newest line in view as it streams.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  // Abandon a stream when the page unmounts — never on close.
  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: number, f: (m: Msg) => Msg) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? f(m) : m)));
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const q = raw.trim();
      if (!q || busy) return;
      const ask: Msg = { id: nextId.current++, role: "user", text: q };
      const reply: Msg = { id: nextId.current++, role: "assistant", text: "", pending: true };
      // The thread the model sees: no greeting, no reply that never arrived.
      const history = [...threadRef.current, ask]
        .filter((m) => m.id !== HELLO.id && (m.role === "user" || m.text))
        .map((m) => ({ role: m.role, content: m.text }));
      setMessages((ms) => [...ms, ask, reply]);
      setInput("");
      setBusy(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const res = await fetch("/api/ask", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ tab, sym, messages: history }),
          signal: ctrl.signal,
          cache: "no-store",
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        await readNdjson(res.body, (ev) => {
          if (ev.t === "delta") patch(reply.id, (m) => ({ ...m, thinking: false, text: m.text + ev.text }));
          else if (ev.t === "thinking") patch(reply.id, (m) => ({ ...m, thinking: true }));
          else if (ev.t === "done") patch(reply.id, (m) => ({ ...m, pending: false, thinking: false, model: ev.model, ms: ev.ms, unverified: ev.unverified ?? [] }));
          else if (ev.t === "error") patch(reply.id, (m) => ({ ...m, pending: false, thinking: false, error: ev.message }));
        });
      } catch (e) {
        if (!ctrl.signal.aborted) {
          patch(reply.id, (m) => ({ ...m, pending: false, error: e instanceof Error ? e.message : String(e) }));
        }
      } finally {
        patch(reply.id, (m) => (m.pending ? { ...m, pending: false, error: m.error ?? "The answer ended before the model finished." } : m));
        setBusy(false);
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [busy, patch, sym, tab],
  );

  const retry = useCallback(
    (failedId: number) => {
      const ms = threadRef.current;
      const at = ms.findIndex((m) => m.id === failedId);
      const ask = at > 0 ? ms[at - 1] : null;
      if (!ask || ask.role !== "user") return;
      // Drop the failed reply and its question; `send` puts both back.
      const kept = ms.filter((m) => m.id !== failedId && m.id !== ask.id);
      setMessages(kept);
      threadRef.current = kept;
      void send(ask.text);
    },
    [send],
  );

  const clear = useCallback(() => {
    abortRef.current?.abort();
    setMessages([HELLO]);
    setBusy(false);
    inputRef.current?.focus();
  }, []);

  const asked = messages.some((m) => m.role === "user");
  const status = !config
    ? "reads your desk beside you"
    : config.enabled
      ? `reads your desk beside you · ${shortModel(config.model)}`
      : "no OPENROUTER_API_KEY — add one to .env.local";

  return (
    <section
      role="dialog"
      aria-label="Hermes"
      hidden={!open}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          setOpen(false);
        }
      }}
      className={cn(
        "fixed right-4 bottom-12 z-50 flex-col overflow-hidden text-ink transition-[width,height] duration-150",
        open ? "flex" : "hidden",
        wide ? "h-[calc(100vh-80px)] w-[min(700px,calc(100vw-32px))]" : "h-[min(660px,calc(100vh-80px))] w-[420px]",
        "rounded-[8px] border border-ring-2 bg-surface shadow-[0_18px_60px_rgba(0,0,0,.6)] qt:rounded-[4px]",
      )}
    >
      <header className="flex h-11 shrink-0 items-center gap-2.5 border-b border-ring px-3.5">
        <span aria-hidden className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[4px] border border-ring text-ink-2">
          <AskGlyph />
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="text-[13px] font-semibold text-ink">Hermes</div>
          <div className="truncate text-[10.5px] text-ink-3" title={config?.model}>
            {status}
          </div>
        </div>
        {asked && (
          <button
            type="button"
            onClick={clear}
            className="hit rounded-[4px] px-1.5 py-0.5 text-[10.5px] font-medium text-ink-3 hover:bg-surface-2 hover:text-ink"
          >
            Clear
          </button>
        )}
        <button
          type="button"
          aria-label={wide ? "Shrink Hermes" : "Expand Hermes"}
          aria-pressed={wide}
          title={wide ? "Back to the compact panel" : "Expand the panel — wider, taller, larger type"}
          onClick={() => setWide((w) => !w)}
          className="hit flex h-6 w-6 items-center justify-center rounded-[4px] text-ink-3 hover:bg-surface-2 hover:text-ink"
        >
          {/* Two corner arrows, pointing out to expand and in to shrink. */}
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
            {wide ? <path d="M6.5 2.5v4h-4M9.5 13.5v-4h4M6.5 6.5 2 2M9.5 9.5 14 14" /> : <path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" />}
          </svg>
        </button>
        <button
          type="button"
          aria-label="Close Hermes"
          onClick={() => setOpen(false)}
          className="hit flex h-6 w-6 items-center justify-center rounded-[4px] text-[16px] leading-none text-ink-3 hover:bg-surface-2 hover:text-ink"
        >
          ×
        </button>
      </header>

      <div ref={listRef} className={cn("min-h-0 flex-1 space-y-3.5 overflow-y-auto py-3", wide ? "px-5" : "px-3.5")} aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} className={cn("flex flex-col gap-1", m.role === "user" && "items-end")}>
            <span className="fig text-[9.5px] tracking-[0.08em] text-ink-4 uppercase">{m.role === "user" ? "You" : "Hermes"}</span>
            <div
              className={cn(
                "max-w-[94%]",
                // A step larger when expanded — the reason to expand.
                wide ? "text-[14px] leading-[1.6]" : "text-[12.5px] leading-[1.55]",
                m.role === "user" ? "rounded-[4px] bg-surface-3 px-3 py-2 whitespace-pre-wrap text-ink" : "text-ink-2",
              )}
            >
              {m.role === "user" ? m.text : <Markdownish text={m.text} />}
              {m.pending && !m.text && <HelmInline className="text-[12px] text-ink-3" label={m.thinking ? "Thinking" : "Reading the desk"} />}
            </div>
            {m.role === "assistant" && m.model && (
              <span className="fig text-[9.5px] text-ink-4" title="The model that wrote this answer, and how long it took">
                {shortModel(m.model)}
                {m.ms != null && ` · ${(m.ms / 1000).toFixed(1)}s`}
              </span>
            )}
            {m.unverified && m.unverified.length > 0 && (
              <p className="max-w-[94%] text-[11px] leading-snug text-put-fig">
                Unverified {m.unverified.length === 1 ? "figure" : "figures"}: <span className="fig">{m.unverified.join(", ")}</span> — not in the
                data Hermes was shown. Read {m.unverified.length === 1 ? "it" : "them"} as unchecked.
              </p>
            )}
            {m.error && (
              <p className="max-w-[94%] text-[11px] leading-snug text-err">
                {m.text ? "The answer stopped early: " : "Hermes couldn't answer: "}
                {m.error}{" "}
                <button type="button" onClick={() => retry(m.id)} className="hit underline decoration-err/50 underline-offset-2 hover:text-ink">
                  Try again
                </button>
              </p>
            )}
          </div>
        ))}
      </div>

      {!busy && (
        <div className="flex shrink-0 flex-wrap gap-1.5 border-t border-ring px-3 pt-2.5">
          {suggestionsFor(tab, sym).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => void send(s)}
              className="hit rounded-[3px] border border-ring bg-surface-2 px-2.5 py-1 text-left text-[11px] text-ink-2 hover:bg-surface-3 hover:text-ink"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className={cn("shrink-0 p-2.5", busy && "border-t border-ring")}
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <div className="flex items-end gap-2 rounded-[4px] border border-ring bg-surface-2 px-3 py-2 focus-within:border-ring-2">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            placeholder={sym ? `Ask about ${sym}, a panel or the session…` : "Ask about a panel, a reading or the session…"}
            aria-label="Ask Hermes"
            className={cn(
              "max-h-[110px] min-h-[20px] flex-1 resize-none bg-transparent leading-[1.5] text-ink outline-none placeholder:text-ink-3",
              wide ? "text-[14px]" : "text-[12.5px]",
            )}
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={!input.trim() || busy}
            className="hit flex h-6 w-6 shrink-0 items-center justify-center rounded-[4px] text-ink-2 hover:bg-surface-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />
            </svg>
          </button>
        </div>
        <p className="mt-1.5 px-1 text-[10px] leading-snug text-ink-4">
          Enter to send · Shift+Enter for a new line · every figure is checked against the live data
        </p>
      </form>
    </section>
  );
}
