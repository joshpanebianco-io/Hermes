import { NextResponse } from "next/server";
import {
  chatConfig,
  hermesModels,
  hermesOptions,
  NO_KEY,
  streamChat,
  TOOLS_UNSUPPORTED,
  type ChatEvent,
  type ChatMsg,
  type ChatOptions,
  type ToolSpec,
} from "@/lib/ask/llm";
import {
  askSystem,
  hermesSlimParts,
  hermesSystem,
  HERMES_TURNS,
  MAX_MESSAGE_CHARS,
  MAX_TURNS,
  numeralsIn,
  splitUnverified,
  type AskContext,
  type SlimContext,
} from "@/lib/ask/prompt";
import { localAnswer, routeQuestion, type GlanceLike, type Route } from "@/lib/ask/router";

/**
 * Hermes — the assistant's one route, for both of its seats.
 *
 *   GET                         whether a key is set, and which model answers
 *   GET ?for=hermes             the same, for the Hermes tab's own chain
 *   GET ?dry=1&tab=&sym=&desk=  the context it would be given right now, with
 *                               no model called — for checking what an answer
 *                               was written from (`&slim=1` on the hermes tab
 *                               shows the slim picture and the tool count;
 *                               `&q=` adds how the router would treat a
 *                               question and any local answer)
 *   POST {tab, sym, desk, messages, summary}
 *                               assemble the context, stream one answer
 *
 * THE ANSWER STREAMS AS NDJSON: one JSON object per line, `delta` lines as the
 * model writes, `thinking` while it reasons before speaking, `tool` when it
 * asks the collector for something, then one `done` (with the numerals the
 * check could not find) or one `error`. A missing key, a dead collector and a
 * rate-limited model all arrive the same way, as the first line, so the panel
 * has one reader and one place to show a reason.
 *
 * THE PANEL'S CONTEXT IS THE COLLECTOR'S (/api/ask/context, ask.py): the
 * digest the desk's own note is written from, read fresh for every question.
 *
 * THE TAB RUNS ON A SLIM PICTURE AND TOOLS (2026-10-30). It opens on a few
 * thousand tokens — the desk at a glance (ask.slim_context) — and the list of
 * what it may ask for (tools.py); the turn runs as rounds, each tool call
 * answered by the collector, until the model answers in words. Every tool
 * result's numerals join the known set, so the check still holds. A model
 * that will not take tools falls back to the whole-terminal context, streamed,
 * as the tab worked before.
 *
 * AND A ROUTER DECIDES HOW MUCH OF THAT A QUESTION GETS (lib/ask/router.ts,
 * owner 2026-10-30: "so the model uses less when it doesn't need to"). A
 * handful of checks are answered from the glance without a model. A quick
 * check gets the glance, no tools and no thinking. A run-down gets the
 * desk's tool set — the futures set or the stocks set, not both — and the
 * thinking budget. The fixed start of the prompt is marked for the provider's
 * cache (llm.ts cachePrefix). The `done` line says which tier ran.
 *
 * EARLIER TURNS ARE REMEMBERED AS A SUMMARY. Past HERMES_TURNS the oldest
 * turns fall off the request; the page keeps a rolling summary of them
 * (/api/ask/summary) and sends it, so "the AMZN retest we discussed" still
 * means something twenty turns on.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// The tab's turn may think for a while, call tools and then write at length;
// the panel's is a fraction of this (see llm.ts hermesOptions and BUDGET_MS).
export const maxDuration = 300;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const HERMES = "hermes";
const TABS = new Set(["terminal", "structure", "tape", "report", "market", "scanner", "plan", "settings", HERMES]);
const noStore = { headers: { "cache-control": "no-store" } };
/** The rolling summary the page sends back, capped. */
const MAX_SUMMARY_CHARS = 2_500;
/** A quick check's answer cap — a line or two, no thinking. */
const QUICK_MAX_TOKENS = 900;
/** The model name the footer shows for an answer no model wrote. */
const LOCAL = "hermes/glance";

const asTab = (v: unknown): string => (typeof v === "string" && TABS.has(v) ? v : "terminal");
const asSym = (v: unknown): string | null =>
  typeof v === "string" && /^[A-Z0-9.\-]{1,12}$/.test(v.toUpperCase()) ? v.toUpperCase() : null;
const asDesk = (v: unknown): "futures" | "stocks" | null => (v === "futures" || v === "stocks" ? v : null);

async function fromCollector<T>(path: string, timeoutMs = 20_000, init?: RequestInit): Promise<T | null> {
  try {
    const r = await fetch(`${API}${path}`, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs), ...init });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

/** What the collector hands over for this tab, or null when it is not answering. */
function gather(tab: string, sym: string | null, desk: string | null): Promise<AskContext | null> {
  const q = new URLSearchParams({ tab });
  if (sym) q.set("sym", sym);
  if (desk) q.set("desk", desk);
  return fromCollector<AskContext>(`/api/ask/context?${q}`);
}

/** The tab's opening picture (ask.slim_context), with the selected scanner name beside it. */
function gatherSlim(sym: string | null, desk: string | null): Promise<SlimContext | null> {
  const q = new URLSearchParams({ tab: HERMES, slim: "1" });
  if (sym) q.set("sym", sym);
  if (desk) q.set("desk", desk);
  return fromCollector<SlimContext>(`/api/ask/context?${q}`);
}

/** The desk's tool set (tools.py spec_for), or every tool. */
async function gatherTools(desk: Route["desk"]): Promise<ToolSpec[]> {
  const got = await fromCollector<{ tools: ToolSpec[] }>(`/api/ask/tools?desk=${desk}`, 10_000);
  return got?.tools ?? [];
}

/** Run one of the model's tool calls on the collector; an error is an answer the model can read. */
async function runTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const got = await fromCollector<unknown>("/api/ask/tool", 30_000, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, args }),
  });
  return got ?? { error: "the collector did not answer the tool call" };
}

/** The conversation as the model sees it: the reader's turns and Hermes's, trimmed and capped. */
function takeHistory(v: unknown, turns: number): ChatMsg[] {
  if (!Array.isArray(v)) return [];
  const out: ChatMsg[] = [];
  for (const m of v) {
    if (!m || typeof m !== "object") continue;
    const { role, content } = m as { role?: unknown; content?: unknown };
    if ((role !== "user" && role !== "assistant") || typeof content !== "string") continue;
    const text = content.trim().slice(0, MAX_MESSAGE_CHARS);
    if (text) out.push({ role, content: text });
  }
  return out.slice(-turns);
}

/** The scanner's names, for the router to recognise a ticker. */
function watchlistOf(slim: SlimContext): string[] {
  const scanner = slim.slim.scanner as { watchlist?: unknown } | null | undefined;
  return Array.isArray(scanner?.watchlist) ? scanner.watchlist.filter((s): s is string => typeof s === "string") : [];
}

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  if (q.get("dry") !== "1") {
    return NextResponse.json(q.get("for") === HERMES ? chatConfig(hermesModels()) : chatConfig(), noStore);
  }
  const tab = asTab(q.get("tab"));
  const sym = asSym(q.get("sym"));
  const desk = asDesk(q.get("desk"));
  if (tab === HERMES && q.get("slim") === "1") {
    const slim = await gatherSlim(sym, desk);
    if (!slim) return NextResponse.json({ error: "The collector did not answer." }, { status: 503, ...noStore });
    const question = (q.get("q") ?? "").trim();
    const route = question ? routeQuestion(question, { desk, sym, watchlist: watchlistOf(slim), followUp: q.get("followup") === "1" }) : null;
    const tools = await gatherTools(route && route.tier === "quick" ? "both" : (route?.desk ?? "both"));
    const parts = hermesSlimParts(slim, sym, { summary: "", tools: route?.tier === "quick" ? [] : tools.map((t) => t.name) });
    return NextResponse.json(
      {
        config: chatConfig(hermesModels()),
        chars: parts.fixed.length + parts.live.length,
        fixedChars: parts.fixed.length,
        tools: route?.tier === "quick" ? 0 : tools.length,
        route,
        local: question ? localAnswer(question, slim.slim as GlanceLike) : null,
        context: slim,
        system: parts.fixed + parts.live,
      },
      noStore,
    );
  }
  const ctx = await gather(tab, sym, desk);
  if (!ctx) return NextResponse.json({ error: "The collector did not answer." }, { status: 503, ...noStore });
  const system = tab === HERMES ? hermesSystem(ctx, sym) : askSystem(ctx, sym);
  return NextResponse.json({ config: chatConfig(tab === HERMES ? hermesModels() : undefined), chars: system.length, context: ctx }, noStore);
}

type Done = Extract<ChatEvent, { t: "done" }> & {
  /** Figures in the answer that are in none of this turn's data. */
  unverified: string[];
  /** Figures an earlier answer in this chat carried but this turn's data does not — true then, stale now. */
  carried: string[];
  route?: { tier: Route["tier"]; desk: Route["desk"] };
};
type Line = ChatEvent | Done;

export async function POST(req: Request) {
  let body: { tab?: unknown; sym?: unknown; desk?: unknown; messages?: unknown; summary?: unknown } = {};
  try {
    body = await req.json();
  } catch {
    /* an empty body is no question */
  }
  const tab = asTab(body.tab);
  const sym = asSym(body.sym);
  const desk = asDesk(body.desk);
  const hermes = tab === HERMES;
  const history = takeHistory(body.messages, hermes ? HERMES_TURNS : MAX_TURNS);
  const summary = hermes && typeof body.summary === "string" ? body.summary.trim().slice(0, MAX_SUMMARY_CHARS) : "";
  if (!history.length || history[history.length - 1].role !== "user") {
    return NextResponse.json({ error: "The last message must be the reader's question." }, { status: 400, ...noStore });
  }
  const question = history[history.length - 1].content;
  const followUp = history.some((m) => m.role === "assistant");

  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let open = true;
      const send = (line: Line) => {
        if (!open) return;
        try {
          controller.enqueue(enc.encode(`${JSON.stringify(line)}\n`));
        } catch {
          open = false; // the reader went away
        }
      };
      const noCollector = () =>
        send({
          t: "error",
          message:
            "The collector did not answer, so there is no live data to read from — and an answer without it would be fiction. Start it (.\\dev.ps1) and ask again.",
        });
      // A figure the reader typed is a figure Hermes may repeat. A figure an
      // earlier answer carried is not data — it is named separately.
      const known = new Set(history.filter((m) => m.role === "user").flatMap((m) => numeralsIn(m.content)));
      const earlier = new Set(history.filter((m) => m.role === "assistant").flatMap((m) => numeralsIn(m.content)));
      let text = "";
      /** Stream one system prompt with these options; "fallback" when no model in the chain took tools. */
      const run = async (system: string, opts: ChatOptions, route?: Route): Promise<"done" | "fallback"> => {
        for (const k of numeralsIn(system)) known.add(k);
        for await (const ev of streamChat([{ role: "system", content: system }, ...history], req.signal, opts)) {
          if (ev.t === "error" && ev.message.startsWith(TOOLS_UNSUPPORTED)) return "fallback";
          if (ev.t === "delta") text += ev.text;
          send(
            ev.t === "done"
              ? { ...ev, ...splitUnverified(text, known, earlier), route: route ? { tier: route.tier, desk: route.desk } : undefined }
              : ev,
          );
          if (!open) break;
        }
        return "done";
      };
      try {
        if (!chatConfig().enabled) {
          send({ t: "error", message: NO_KEY });
          return;
        }
        if (hermes) {
          const slim = await gatherSlim(sym, desk);
          if (!slim) {
            noCollector();
            return;
          }
          // A check the glance answers whole never reaches a model.
          const t0 = Date.now();
          const local = localAnswer(question, slim.slim as GlanceLike);
          if (local) {
            send({ t: "delta", text: local });
            send({ t: "done", model: LOCAL, finish: "stop", ms: Date.now() - t0, usage: { prompt: 0, cached: 0, completion: 0, cost: 0 }, unverified: [], carried: [], route: { tier: "quick", desk: "both" } });
            return;
          }
          const route = routeQuestion(question, { desk, sym, watchlist: watchlistOf(slim), followUp });
          const tools = route.tier === "full" ? await gatherTools(route.desk) : [];
          const parts = hermesSlimParts(slim, sym, { summary, tools: tools.map((t) => t.name) });
          const base = hermesOptions();
          const opts: ChatOptions =
            route.tier === "quick"
              ? { ...base, maxTokens: QUICK_MAX_TOKENS, reasoningTokens: 0, cachePrefix: parts.fixed }
              : {
                  ...base,
                  cachePrefix: parts.fixed,
                  tools: tools.length ? tools : undefined,
                  runTool,
                  onToolResult: (t) => {
                    for (const k of numeralsIn(t)) known.add(k);
                  },
                };
          if ((await run(parts.fixed + parts.live, opts, route)) === "done") return;
          // No model in the chain takes tools: the whole terminal, streamed, as before.
          send({ t: "thinking" });
          const ctx = await gather(tab, sym, desk);
          if (!ctx) {
            noCollector();
            return;
          }
          await run(hermesSystem(ctx, sym, summary), hermesOptions());
          return;
        }
        const ctx = await gather(tab, sym, desk);
        if (!ctx) {
          noCollector();
          return;
        }
        await run(askSystem(ctx, sym), {});
      } catch (e) {
        send({ t: "error", message: e instanceof Error ? e.message : String(e) });
      } finally {
        try {
          controller.close();
        } catch {
          /* already closed by the reader */
        }
      }
    },
  });
  return new Response(stream, {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-store",
      // A proxy that buffers would turn the stream back into a wait.
      "x-accel-buffering": "no",
    },
  });
}
