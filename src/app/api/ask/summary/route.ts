import { NextResponse } from "next/server";
import { chatConfig, completeOnce, hermesModels, type ChatMsg } from "@/lib/ask/llm";

/**
 * The Hermes tab's rolling memory: the turns that have fallen off the window,
 * folded into a paragraph the next question carries (2026-10-30).
 *
 * WHY A SUMMARY AND NOT A LONGER WINDOW. Twenty-four turns travel with every
 * question; the rest would cost tokens on every turn for the rare question
 * that reaches back. A summary of what fell off costs one small call, once,
 * and keeps "the retest we were talking about" alive. It is the page's to
 * keep (useHermes), beside the chat, and to send back with each question.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

const noStore = { headers: { "cache-control": "no-store" } };
/** The transcript handed to the summariser, capped — the oldest turns go first and are what matters least. */
const MAX_TRANSCRIPT_CHARS = 24_000;

const SUMMARISE = `You keep the memory of a trading-desk chat. Summarise the conversation below in at most 180 words of plain prose, for the assistant who will carry on the chat: the names, books and levels discussed, what the reader asked for and decided, what the assistant said the data showed, and any open thread. Keep every figure exactly as written. No preamble.`;

export async function POST(req: Request) {
  if (!chatConfig().enabled) return NextResponse.json({ summary: null }, noStore);
  let body: { messages?: unknown; previous?: unknown } = {};
  try {
    body = await req.json();
  } catch {
    /* empty */
  }
  const turns: ChatMsg[] = [];
  if (Array.isArray(body.messages)) {
    for (const m of body.messages) {
      const { role, content } = (m ?? {}) as { role?: unknown; content?: unknown };
      if ((role === "user" || role === "assistant") && typeof content === "string" && content.trim()) {
        turns.push({ role, content: content.trim() });
      }
    }
  }
  if (!turns.length) return NextResponse.json({ summary: null }, noStore);
  const previous = typeof body.previous === "string" ? body.previous.trim().slice(0, 2_500) : "";
  let transcript = turns.map((m) => `${m.role === "user" ? "Reader" : "Hermes"}: ${m.content}`).join("\n\n");
  if (transcript.length > MAX_TRANSCRIPT_CHARS) transcript = transcript.slice(-MAX_TRANSCRIPT_CHARS);
  const user = (previous ? `Earlier summary:\n${previous}\n\n` : "") + `Conversation:\n${transcript}`;
  const summary = await completeOnce(
    [
      { role: "system", content: SUMMARISE },
      { role: "user", content: user },
    ],
    { models: hermesModels(), maxTokens: 400, reasoningTokens: 256 },
  );
  return NextResponse.json({ summary }, noStore);
}
