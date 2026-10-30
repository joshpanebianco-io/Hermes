"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { OPEN_ASK_EVENT, useAskFocus } from "@/lib/ask/open";
import { HERMES_INTRO, HERMES_SUGGESTIONS } from "@/lib/ask/suggest";
import { shortModel, tokens } from "@/lib/ask/stream";
import type { HermesChat, HermesController, HermesMsg } from "@/lib/hermes/useHermes";
import type { Desk } from "@/lib/tabs";
import { HelmMark } from "@/components/ui/HelmLoader";
import { Markdownish } from "@/components/ask/Markdownish";
import { cn } from "@/lib/cn";

/**
 * Hermes — the assistant on a page of its own (owner, 2026-10-30: "another
 * tab after analysis … essentially like the ask hermes chat box except in its
 * own tab … with the same ui layout as chatgpt, claude, gemini").
 *
 * THE LAYOUT THOSE SHARE, and nothing they do not: past chats down a rail on
 * the left, the thread in a centred column that scrolls, the box pinned at
 * the bottom with a hint under it. No model picker, no attachments, no
 * sidebar of tools — the terminal's data is the attachment, and it travels
 * with every question.
 *
 * ONE TAB FOR THE WHOLE DESK: the context is the whole terminal
 * (server/newsterminal/ask.py whole_context), both desks at once, not one
 * desk's digest — the bar has no desk since 2026-10-30 (lib/tabs.ts).
 *
 * THE STATE IS NOT HERE. The chats, the stream and the stop live in
 * `useHermes`, created once by the Terminal, so switching tabs mid-answer
 * does not abandon it — the reason the report's state lives above its panel.
 *
 * THE A KEY AND THE RAIL'S ASK KEY FOCUS THE BOX HERE instead of opening the
 * side panel over a page that is already Hermes.
 */
export function HermesTab({ hermes, desk }: { hermes: HermesController; desk: Desk }) {
  const { chats, current, currentId, busy, config, select, newChat, remove, send, retry, stop } = hermes;
  const sym = useAskFocus();
  const [input, setInput] = useState("");
  // The rail, on a window too narrow to keep it open beside the thread.
  const [railOpen, setRailOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Follow the newest line only while the reader is already at the bottom —
  // scrolling up to re-read an earlier answer must not be fought.
  const stick = useRef(true);
  // One array per chat, so the follow-the-stream effect below runs on a change, not on every render.
  const messages = useMemo(() => current?.messages ?? [], [current]);

  useEffect(() => {
    const onOpen = (e: Event) => {
      const q = (e as CustomEvent<{ question?: string }>).detail?.question;
      if (q) setInput(q);
      inputRef.current?.focus();
    };
    window.addEventListener(OPEN_ASK_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_ASK_EVENT, onOpen);
  }, []);

  // A fresh page, a new chat or a switch: the box has focus and the thread is at its end.
  useEffect(() => {
    inputRef.current?.focus();
    stick.current = true;
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setRailOpen(false);
  }, [currentId]);

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  useEffect(() => {
    const el = listRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const onScroll = useCallback(() => {
    const el = listRef.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  const submit = useCallback(
    (text: string) => {
      if (!text.trim() || busy) return;
      stick.current = true;
      setInput("");
      send(text, sym, desk);
    },
    [busy, desk, send, sym],
  );

  const hint = !config
    ? "reads the whole terminal"
    : config.enabled
      ? shortModel(config.model)
      : "no OPENROUTER_API_KEY — add one to .env.local";

  return (
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <Rail
        chats={chats}
        currentId={currentId}
        busy={busy}
        onSelect={select}
        onNew={newChat}
        onRemove={remove}
        className={cn(
          // Beside the thread from 1280px; a drawer over it below that.
          "hidden xl:flex",
          railOpen && "absolute inset-y-0 left-0 z-20 flex shadow-[8px_0_30px_rgba(0,0,0,.45)]",
        )}
      />
      {railOpen && <button type="button" aria-label="Close chats" onClick={() => setRailOpen(false)} className="absolute inset-0 z-10 bg-black/30 xl:hidden" />}

      <section className="flex min-w-0 flex-1 flex-col" aria-label="Hermes">
        {/* The narrow window's bar: the rail behind a key, New chat beside it. */}
        <div className="flex h-9 shrink-0 items-center gap-2 border-b border-ring px-3 xl:hidden">
          <button type="button" onClick={() => setRailOpen((o) => !o)} className="hit rounded-[4px] px-2 py-0.5 text-[11px] text-ink-2 hover:bg-surface-2 hover:text-ink">
            Chats{chats.length > 0 && <span className="fig text-ink-4"> · {chats.length}</span>}
          </button>
          <span className="min-w-0 flex-1 truncate text-[11px] text-ink-3">{current?.title ?? "New chat"}</span>
          <button type="button" onClick={newChat} disabled={!current} className="hit rounded-[4px] px-2 py-0.5 text-[11px] text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-40">
            New chat
          </button>
        </div>

        <div ref={listRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          <div className="mx-auto w-full max-w-[960px] px-4 py-6 sm:px-6">
            {messages.length === 0 ? (
              <Empty onPick={submit} disabled={busy} />
            ) : (
              <div className="flex flex-col gap-6">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <div key={m.id} className="flex justify-end">
                      <div className="max-w-[82%] rounded-[12px] rounded-br-[4px] bg-surface-3 px-4 py-2.5 text-[14px] leading-[1.6] whitespace-pre-wrap text-ink">{m.text}</div>
                    </div>
                  ) : (
                    <Answer key={m.id} m={m} onRetry={() => retry(m.id, sym, desk)} />
                  ),
                )}
              </div>
            )}
          </div>
        </div>

        {/* No rule above the box and no band behind it (owner, 2026-10-30):
            the box sits on the page it belongs to. */}
        <div className="shrink-0">
          <form
            // A taller box with air above and more below it (owner, 2026-10-30).
            className="mx-auto w-full max-w-[960px] px-4 pt-5 pb-6 sm:px-6"
            onSubmit={(e) => {
              e.preventDefault();
              submit(input);
            }}
          >
            <div className="flex items-end gap-3 rounded-[14px] border border-ring bg-surface-2 px-5 py-4 focus-within:border-ring-2">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit(input);
                  }
                }}
                placeholder="Ask Hermes anything about the desk…"
                aria-label="Ask Hermes"
                className="max-h-[220px] min-h-[52px] flex-1 resize-none bg-transparent text-[15px] leading-[1.6] text-ink outline-none placeholder:text-ink-3"
              />
              {busy ? (
                <button
                  type="button"
                  onClick={stop}
                  aria-label="Stop"
                  title="Stop — keep what has arrived"
                  className="hit flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-ink text-surface hover:opacity-90"
                >
                  <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor" aria-hidden>
                    <rect x="3" y="3" width="10" height="10" rx="1.5" />
                  </svg>
                </button>
              ) : (
                <button
                  type="submit"
                  aria-label="Send"
                  disabled={!input.trim()}
                  className="hit flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-ink text-surface hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />
                  </svg>
                </button>
              )}
            </div>
            <p className="mt-3 px-1 text-center text-[10.5px] leading-snug text-ink-4" title={config?.model}>
              Enter to send · Shift+Enter for a new line · {hint} · every figure is checked against the live data
            </p>
          </form>
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function Empty({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  const grad = useId();
  return (
    <div className="flex flex-col items-center pt-[6vh] text-center">
      <HelmMark size={52} gradId={`hermes-tab-${grad}`} />
      <h2 className="wordmark fig mt-4 text-[22px] font-semibold tracking-[0.12em]">Hermes AI</h2>
      <p className="mt-3 max-w-[560px] text-[13.5px] leading-[1.6] text-ink-3">{HERMES_INTRO}</p>
      <div className="mt-8 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {HERMES_SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="hit rounded-[10px] border border-ring bg-surface-2 px-4 py-3 text-left text-[13px] leading-snug text-ink-2 hover:border-ring-2 hover:bg-surface-3 hover:text-ink disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Answer({ m, onRetry }: { m: HermesMsg; onRetry: () => void }) {
  const grad = useId();
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard
      ?.writeText(m.text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {});
  }, [m.text]);
  const waiting = m.pending && !m.text;
  return (
    <div className="flex gap-3">
      {/* ONE HELM, NOT TWO (owner, 2026-10-30: "when it's thinking it has 2
          hermes logos next to each other"): while the answer is awaited the
          avatar itself is the loader — it takes the loader's cadence — and
          the words sit beside it, rather than a second helm in the text. */}
      <span
        aria-hidden
        className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-ring bg-surface-2", waiting && "helm-loader")}
      >
        <HelmMark size={18} gradId={`hermes-answer-${grad}`} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[14.5px] leading-[1.65] text-ink-2">
          {waiting ? (
            <span role="status" aria-live="polite" className="inline-block py-1 text-[13px] text-ink-3">
              {m.activity ?? (m.thinking ? "Thinking" : "Reading the desk")}…
            </span>
          ) : (
            <Markdownish text={m.text} />
          )}
        </div>
        {!m.pending && (
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-ink-4">
            {m.model && (
              <span className="fig" title="The model that wrote this answer, how long it took, and the tokens it read and wrote (with OpenRouter's cost when the model is paid)">
                {shortModel(m.model)}
                {m.ms != null && ` · ${(m.ms / 1000).toFixed(1)}s`}
                {m.usage && m.usage.prompt + m.usage.completion > 0 && ` · ${tokens(m.usage.prompt + m.usage.completion)} tok`}
                {m.usage && m.usage.cached > 0 && ` (${tokens(m.usage.cached)} cached)`}
                {m.route?.tier === "quick" && " · quick"}
                {m.usage && m.usage.cost > 0 && ` · $${m.usage.cost.toFixed(m.usage.cost < 0.01 ? 4 : 3)}`}
              </span>
            )}
            {m.stopped && <span>Stopped</span>}
            {m.text && (
              <button type="button" onClick={copy} className="hit rounded px-1 hover:bg-surface-2 hover:text-ink">
                {copied ? "Copied" : "Copy"}
              </button>
            )}
            {m.error && (
              <button type="button" onClick={onRetry} className="hit rounded px-1 hover:bg-surface-2 hover:text-ink">
                Try again
              </button>
            )}
          </div>
        )}
        {m.carried && m.carried.length > 0 && (
          <p className="mt-2 text-[11.5px] leading-snug text-ink-3">
            Carried from an earlier answer, not re-read this turn: <span className="fig">{m.carried.join(", ")}</span> — the market may have moved
            since. Ask again for the live {m.carried.length === 1 ? "figure" : "figures"}.
          </p>
        )}
        {m.unverified && m.unverified.length > 0 && (
          <p className="mt-2 text-[11.5px] leading-snug text-put-fig">
            Unverified {m.unverified.length === 1 ? "figure" : "figures"}: <span className="fig">{m.unverified.join(", ")}</span> — not in the data Hermes
            was shown. Read {m.unverified.length === 1 ? "it" : "them"} as unchecked.
          </p>
        )}
        {m.error && (
          <p className="mt-2 text-[11.5px] leading-snug text-err">
            {m.text ? "The answer stopped early: " : "Hermes couldn't answer: "}
            {m.error}
          </p>
        )}
      </div>
    </div>
  );
}

/** Today / Yesterday / Earlier, by the reader's own clock. */
function groupOf(ts: number, now: Date): string {
  const d = new Date(ts);
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86_400_000);
  return diff <= 0 ? "Today" : diff === 1 ? "Yesterday" : "Earlier";
}

function Rail({
  chats,
  currentId,
  busy,
  onSelect,
  onNew,
  onRemove,
  className,
}: {
  chats: HermesChat[];
  currentId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRemove: (id: string) => void;
  className?: string;
}) {
  // Delete asks once, in place: the × becomes "Delete?" for a moment.
  const [confirm, setConfirm] = useState<string | null>(null);
  useEffect(() => {
    if (!confirm) return;
    const t = setTimeout(() => setConfirm(null), 3000);
    return () => clearTimeout(t);
  }, [confirm]);
  const now = new Date();
  const groups: { label: string; items: HermesChat[] }[] = [];
  for (const c of chats) {
    const label = groupOf(c.updated, now);
    const g = groups.find((x) => x.label === label);
    if (g) g.items.push(c);
    else groups.push({ label, items: [c] });
  }
  return (
    <aside className={cn("w-[240px] shrink-0 flex-col border-r border-ring bg-surface", className)} aria-label="Chats">
      <div className="shrink-0 p-2.5">
        <button
          type="button"
          onClick={onNew}
          disabled={currentId === null && !busy}
          className="hit flex w-full items-center gap-2 rounded-[8px] border border-ring px-3 py-2 text-left text-[12.5px] font-medium text-ink hover:border-ring-2 hover:bg-surface-2 disabled:cursor-default disabled:opacity-50"
        >
          <span className="fig text-[15px] leading-none text-ink-3">+</span> New chat
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {chats.length === 0 && <p className="px-2 pt-2 text-[11px] leading-snug text-ink-4">Your chats will be kept here, in this browser.</p>}
        {groups.map((g) => (
          <div key={g.label} className="mt-2">
            <div className="fig px-2 pb-1 text-[9.5px] tracking-[0.1em] text-ink-4 uppercase">{g.label}</div>
            {g.items.map((c) => {
              const active = c.id === currentId;
              return (
                <div key={c.id} className={cn("group flex items-center rounded-[6px]", active ? "bg-surface-3" : "hover:bg-surface-2")}>
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    className={cn("hit min-w-0 flex-1 truncate px-2.5 py-1.5 text-left text-[12.5px]", active ? "text-ink" : "text-ink-2")}
                    title={c.title}
                  >
                    {c.title}
                  </button>
                  <button
                    type="button"
                    aria-label={confirm === c.id ? `Delete “${c.title}”` : `Delete chat “${c.title}”`}
                    onClick={() => {
                      if (confirm === c.id) {
                        setConfirm(null);
                        onRemove(c.id);
                      } else setConfirm(c.id);
                    }}
                    className={cn(
                      "hit mr-1 shrink-0 rounded px-1.5 py-0.5 text-[11px]",
                      confirm === c.id ? "text-err" : "text-ink-4 opacity-0 group-hover:opacity-100 hover:text-ink focus:opacity-100",
                      active && "opacity-100",
                    )}
                  >
                    {confirm === c.id ? "Delete?" : "×"}
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </aside>
  );
}
