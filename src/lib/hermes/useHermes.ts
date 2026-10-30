"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { describeTool, readNdjson } from "@/lib/ask/stream";
import type { Desk } from "@/lib/tabs";

/**
 * The Hermes tab's chats — owned above the tab switch, kept in this browser.
 *
 * WHY IT IS NOT IN THE TAB. The tab unmounts when you leave it, and a stream
 * mid-answer would be abandoned with it; the thread is state that outlives
 * the page you are looking at, the same reason the report's generation lives
 * in `useReport` rather than its panel. So the controller is created once in
 * the Terminal and handed down.
 *
 * KEPT IN THE BROWSER (owner, 2026-10-30: a chat laid out like the ones they
 * know, which keep their chats). localStorage, under the terminal's own
 * prefix, written a beat after the last change rather than on every streamed
 * token — thirty chats of eighty messages serialised per token would be the
 * wrong kind of live. Read once after mount, like every preference
 * (usePersisted says why not during render). A chat that is still being
 * written is saved as finished text; a reload mid-answer keeps what was heard.
 *
 * ONE ANSWER AT A TIME. A send while one is streaming is ignored, as the
 * panel's is; Stop ends the current one and keeps what has arrived.
 */

export interface HermesMsg {
  id: number;
  role: "user" | "assistant";
  text: string;
  pending?: boolean;
  /** The model is reasoning before it speaks — shown so silence is not read as a stall. */
  thinking?: boolean;
  /** What the model is reading right now ("Reading AMZN's scanner row") — the wait, explained. */
  activity?: string | null;
  /** Ended by the reader, with whatever had arrived. */
  stopped?: boolean;
  error?: string | null;
  unverified?: string[];
  /** Figures repeated from an earlier answer in this chat that this turn's data did not carry. */
  carried?: string[];
  /** Which model actually answered — the chain falls through on the free tier. */
  model?: string | null;
  ms?: number;
  /** Tokens in (and how many of them from cache), tokens out and OpenRouter's cost for the turn, summed over its tool rounds. */
  usage?: { prompt: number; cached: number; completion: number; cost: number };
  /** How the router treated the question: a quick check or the full kit, and whose tools. */
  route?: { tier: "quick" | "full"; desk: "futures" | "stocks" | "both" };
}

export interface HermesChat {
  id: string;
  /** The first question, cut short — what the rail shows. */
  title: string;
  created: number;
  updated: number;
  messages: HermesMsg[];
  /** The turns that fell off the window, folded into a paragraph (/api/ask/summary). */
  summary?: string;
  /** How many messages that summary covers, counted from the start of the chat. */
  summaryUpTo?: number;
}

export interface HermesController {
  chats: HermesChat[];
  /** The chat on screen; null is a fresh one, made on the first send. */
  current: HermesChat | null;
  currentId: string | null;
  busy: boolean;
  config: { enabled: boolean; model: string } | null;
  select: (id: string) => void;
  newChat: () => void;
  remove: (id: string) => void;
  send: (text: string, sym: string | null, desk: Desk | null) => void;
  /** Ask a failed question again, in place. */
  retry: (failedId: number, sym: string | null, desk: Desk | null) => void;
  /** End the answer being written, keeping what has arrived. */
  stop: () => void;
}

const CHATS_KEY = "nt.hermes.chats";
const CURRENT_KEY = "nt.hermes.current";
/** How many chats the rail keeps; the oldest falls off. */
export const MAX_CHATS = 30;
/** How many messages a chat keeps; the oldest turns fall off the top. */
export const MAX_MESSAGES = 80;
/** A chat's title is its first question, cut here. */
const TITLE_CHARS = 60;
/** How many messages travel with a question; older ones live on as the summary (prompt.ts HERMES_TURNS). */
const KEEP_TURNS = 24;
const SAVE_AFTER_MS = 400;

const isMsg = (v: unknown): v is HermesMsg =>
  !!v &&
  typeof v === "object" &&
  typeof (v as HermesMsg).id === "number" &&
  ((v as HermesMsg).role === "user" || (v as HermesMsg).role === "assistant") &&
  typeof (v as HermesMsg).text === "string";

const isChat = (v: unknown): v is HermesChat =>
  !!v &&
  typeof v === "object" &&
  typeof (v as HermesChat).id === "string" &&
  typeof (v as HermesChat).title === "string" &&
  typeof (v as HermesChat).created === "number" &&
  typeof (v as HermesChat).updated === "number" &&
  Array.isArray((v as HermesChat).messages) &&
  (v as HermesChat).messages.every(isMsg) &&
  ((v as HermesChat).summary === undefined || typeof (v as HermesChat).summary === "string");

/** What was saved, or nothing. A chat saved mid-answer comes back finished. */
function load(): { chats: HermesChat[]; current: string | null } {
  try {
    const raw = window.localStorage.getItem(CHATS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    const chats = Array.isArray(parsed) ? parsed.filter(isChat) : [];
    for (const c of chats) {
      c.messages = c.messages.map((m) => (m.pending ? { ...m, pending: false, thinking: false, stopped: true } : m));
    }
    const current = window.localStorage.getItem(CURRENT_KEY);
    return { chats, current: current && chats.some((c) => c.id === current) ? current : null };
  } catch {
    return { chats: [], current: null };
  }
}

function save(chats: HermesChat[], current: string | null): void {
  try {
    window.localStorage.setItem(CHATS_KEY, JSON.stringify(chats));
    if (current) window.localStorage.setItem(CURRENT_KEY, current);
    else window.localStorage.removeItem(CURRENT_KEY);
  } catch {
    /* applies to this session; it just will not persist */
  }
}

const titleOf = (q: string): string => {
  const one = q.replace(/\s+/g, " ").trim();
  return one.length > TITLE_CHARS ? `${one.slice(0, TITLE_CHARS - 1).trimEnd()}…` : one;
};

const newChatId = (): string => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

export function useHermes(): HermesController {
  const [chats, setChats] = useState<HermesChat[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<{ enabled: boolean; model: string } | null>(null);
  const loaded = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // Message ids: unique across reloads, so a retry never collides with a saved id.
  const nextId = useRef(Date.now());
  // The chats as of the last render, for a send that must not close over a stale list.
  const chatsRef = useRef(chats);
  chatsRef.current = chats;

  useEffect(() => {
    const got = load();
    if (got.chats.length) setChats(got.chats);
    setCurrentId(got.current ?? got.chats[0]?.id ?? null);
    loaded.current = true;
  }, []);

  useEffect(() => {
    if (!loaded.current) return;
    const t = setTimeout(() => save(chats, currentId), SAVE_AFTER_MS);
    return () => clearTimeout(t);
  }, [chats, currentId]);

  useEffect(() => {
    fetch("/api/ask?for=hermes", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((c: { enabled: boolean; model: string } | null) => c && setConfig(c))
      .catch(() => {});
  }, []);

  // Abandon a stream when the page unmounts — never on a tab switch.
  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((chatId: string, msgId: number, f: (m: HermesMsg) => HermesMsg) => {
    setChats((cs) =>
      cs.map((c) => (c.id !== chatId ? c : { ...c, updated: Date.now(), messages: c.messages.map((m) => (m.id === msgId ? f(m) : m)) })),
    );
  }, []);

  /**
   * Fold the turns that have fallen off the window into the chat's summary,
   * once per turn at most and only when something new has fallen off. A
   * summariser that does not answer leaves the old summary in place.
   */
  const remember = useCallback(async (chatId: string) => {
    const chat = chatsRef.current.find((c) => c.id === chatId);
    if (!chat) return;
    const settled = chat.messages.filter((m) => !m.pending && (m.role === "user" || m.text));
    const cut = settled.length - KEEP_TURNS;
    if (cut <= 0 || (chat.summaryUpTo ?? 0) >= cut) return;
    const older = settled.slice(chat.summaryUpTo ?? 0, cut).map((m) => ({ role: m.role, content: m.text }));
    try {
      const r = await fetch("/api/ask/summary", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: older, previous: chat.summary ?? "" }),
        cache: "no-store",
      });
      const { summary } = (await r.json()) as { summary: string | null };
      if (summary) setChats((cs) => cs.map((c) => (c.id === chatId ? { ...c, summary, summaryUpTo: cut } : c)));
    } catch {
      /* next turn */
    }
  }, []);

  const send = useCallback(
    (raw: string, sym: string | null, desk: Desk | null) => {
      const q = raw.trim();
      if (!q || busy) return;
      const now = Date.now();
      const found = currentId ? chatsRef.current.find((c) => c.id === currentId) : undefined;
      const base: HermesChat = found ?? { id: newChatId(), title: titleOf(q), created: now, updated: now, messages: [] };
      const ask: HermesMsg = { id: nextId.current++, role: "user", text: q };
      const reply: HermesMsg = { id: nextId.current++, role: "assistant", text: "", pending: true };
      // The thread the model sees: no reply that never arrived, the last
      // KEEP_TURNS of it, and the summary of whatever fell off before them.
      const history = [...base.messages, ask]
        .filter((m) => m.role === "user" || m.text)
        .map((m) => ({ role: m.role, content: m.text }))
        .slice(-KEEP_TURNS);
      const summary = base.summary ?? "";
      const chat: HermesChat = {
        ...base,
        updated: now,
        title: base.messages.length ? base.title : titleOf(q),
        messages: [...base.messages, ask, reply].slice(-MAX_MESSAGES),
      };
      // The chat being written rises to the top of the rail.
      setChats((cs) => [chat, ...cs.filter((c) => c.id !== chat.id)].slice(0, MAX_CHATS));
      setCurrentId(chat.id);
      setBusy(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      void (async () => {
        try {
          const res = await fetch("/api/ask", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ tab: "hermes", sym, desk, messages: history, summary }),
            signal: ctrl.signal,
            cache: "no-store",
          });
          if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
          await readNdjson(res.body, (ev) => {
            if (ev.t === "delta") patch(chat.id, reply.id, (m) => ({ ...m, thinking: false, activity: null, text: m.text + ev.text }));
            else if (ev.t === "thinking") patch(chat.id, reply.id, (m) => ({ ...m, thinking: true }));
            else if (ev.t === "tool") patch(chat.id, reply.id, (m) => ({ ...m, activity: describeTool(ev.name, ev.args) }));
            else if (ev.t === "done")
              patch(chat.id, reply.id, (m) => ({
                ...m,
                pending: false,
                thinking: false,
                activity: null,
                model: ev.model,
                ms: ev.ms,
                usage: ev.usage,
                route: ev.route,
                unverified: ev.unverified ?? [],
                carried: ev.carried ?? [],
              }));
            else patch(chat.id, reply.id, (m) => ({ ...m, pending: false, thinking: false, error: ev.message }));
          });
        } catch (e) {
          if (!ctrl.signal.aborted) {
            patch(chat.id, reply.id, (m) => ({ ...m, pending: false, thinking: false, error: e instanceof Error ? e.message : String(e) }));
          }
        } finally {
          patch(chat.id, reply.id, (m) =>
            m.pending
              ? {
                  ...m,
                  pending: false,
                  thinking: false,
                  activity: null,
                  stopped: ctrl.signal.aborted,
                  error: m.error ?? (ctrl.signal.aborted ? null : "The answer ended before the model finished."),
                }
              : m,
          );
          setBusy(false);
          if (abortRef.current === ctrl) abortRef.current = null;
          void remember(chat.id);
        }
      })();
    },
    [busy, currentId, patch, remember],
  );

  const retry = useCallback(
    (failedId: number, sym: string | null, desk: Desk | null) => {
      const chat = chatsRef.current.find((c) => c.id === currentId);
      if (!chat) return;
      const at = chat.messages.findIndex((m) => m.id === failedId);
      const ask = at > 0 ? chat.messages[at - 1] : null;
      if (!ask || ask.role !== "user") return;
      // Drop the failed reply and its question; `send` puts both back.
      const kept = { ...chat, messages: chat.messages.filter((m) => m.id !== failedId && m.id !== ask.id) };
      const next = chatsRef.current.map((c) => (c.id === chat.id ? kept : c));
      chatsRef.current = next;
      setChats(next);
      send(ask.text, sym, desk);
    },
    [currentId, send],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const select = useCallback((id: string) => setCurrentId(id), []);

  const newChat = useCallback(() => setCurrentId(null), []);

  const remove = useCallback(
    (id: string) => {
      if (busy && id === currentId) abortRef.current?.abort();
      setChats((cs) => cs.filter((c) => c.id !== id));
      setCurrentId((cur) => (cur === id ? null : cur));
    },
    [busy, currentId],
  );

  const current = currentId ? (chats.find((c) => c.id === currentId) ?? null) : null;
  return { chats, current, currentId, busy, config, select, newChat, remove, send, retry, stop };
}
