import { NextResponse } from "next/server";
import { chatConfig, NO_KEY, streamChat, type ChatEvent, type ChatMsg } from "@/lib/ask/llm";
import { askSystem, MAX_MESSAGE_CHARS, MAX_TURNS, numeralsIn, unverifiedNumerals, type AskContext } from "@/lib/ask/prompt";

/**
 * Hermes — the assistant's one route.
 *
 *   GET                         whether a key is set, and which model answers
 *   GET ?dry=1&tab=&sym=        the context it would be given right now, with
 *                               no model called — for checking what an answer
 *                               was written from
 *   POST {tab, sym, messages}   assemble the context, stream one answer
 *
 * THE ANSWER STREAMS AS NDJSON: one JSON object per line, `delta` lines as the
 * model writes, then one `done` (with the numerals the check could not find)
 * or one `error`. A missing key, a dead collector and a rate-limited model all
 * arrive the same way, as the first line, so the panel has one reader and one
 * place to show a reason.
 *
 * THE CONTEXT IS THE COLLECTOR'S (/api/ask/context, ask.py): the digest the
 * desk's own note is written from, read fresh for every question — the
 * collector already holds it in memory, so there is nothing to memoise.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 150;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const TABS = new Set(["terminal", "report", "market", "scanner", "plan", "settings"]);
const noStore = { headers: { "cache-control": "no-store" } };

const asTab = (v: unknown): string => (typeof v === "string" && TABS.has(v) ? v : "terminal");
const asSym = (v: unknown): string | null =>
  typeof v === "string" && /^[A-Z0-9.\-]{1,12}$/.test(v.toUpperCase()) ? v.toUpperCase() : null;

/** What the collector hands over for this tab, or null when it is not answering. */
async function gather(tab: string, sym: string | null): Promise<AskContext | null> {
  const q = new URLSearchParams({ tab });
  if (sym) q.set("sym", sym);
  try {
    const r = await fetch(`${API}/api/ask/context?${q}`, { cache: "no-store", signal: AbortSignal.timeout(20_000) });
    return r.ok ? ((await r.json()) as AskContext) : null;
  } catch {
    return null;
  }
}

/** The conversation as the model sees it: the reader's turns and Hermes's, trimmed and capped. */
function takeHistory(v: unknown): ChatMsg[] {
  if (!Array.isArray(v)) return [];
  const out: ChatMsg[] = [];
  for (const m of v) {
    if (!m || typeof m !== "object") continue;
    const { role, content } = m as { role?: unknown; content?: unknown };
    if ((role !== "user" && role !== "assistant") || typeof content !== "string") continue;
    const text = content.trim().slice(0, MAX_MESSAGE_CHARS);
    if (text) out.push({ role, content: text });
  }
  return out.slice(-MAX_TURNS);
}

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  if (q.get("dry") !== "1") return NextResponse.json(chatConfig(), noStore);
  const tab = asTab(q.get("tab"));
  const sym = asSym(q.get("sym"));
  const ctx = await gather(tab, sym);
  if (!ctx) return NextResponse.json({ error: "The collector did not answer." }, { status: 503, ...noStore });
  const system = askSystem(ctx, sym);
  return NextResponse.json({ config: chatConfig(), chars: system.length, context: ctx }, noStore);
}

type Line = ChatEvent | (Extract<ChatEvent, { t: "done" }> & { unverified: string[] });

export async function POST(req: Request) {
  let body: { tab?: unknown; sym?: unknown; messages?: unknown } = {};
  try {
    body = await req.json();
  } catch {
    /* an empty body is no question */
  }
  const tab = asTab(body.tab);
  const sym = asSym(body.sym);
  const history = takeHistory(body.messages);
  if (!history.length || history[history.length - 1].role !== "user") {
    return NextResponse.json({ error: "The last message must be the reader's question." }, { status: 400, ...noStore });
  }

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
      try {
        if (!chatConfig().enabled) {
          send({ t: "error", message: NO_KEY });
          return;
        }
        const ctx = await gather(tab, sym);
        if (!ctx) {
          send({
            t: "error",
            message:
              "The collector did not answer, so there is no live data to read from — and an answer without it would be fiction. Start it (.\\dev.ps1) and ask again.",
          });
          return;
        }
        const system = askSystem(ctx, sym);
        // A figure the reader typed is a figure Hermes may repeat.
        const known = new Set([...numeralsIn(system), ...history.filter((m) => m.role === "user").flatMap((m) => numeralsIn(m.content))]);
        let text = "";
        for await (const ev of streamChat([{ role: "system", content: system }, ...history], req.signal)) {
          if (ev.t === "delta") text += ev.text;
          send(ev.t === "done" ? { ...ev, unverified: unverifiedNumerals(text, known) } : ev);
          if (!open) break;
        }
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
