/*
 * SERVER ONLY — the OpenRouter key is read here and never leaves the server.
 * Called from /api/ask; nothing in `components/` imports it.
 */

/**
 * One streamed chat turn for Hermes, token by token.
 *
 * PORTED FROM GEXYGEN'S ASSISTANT CLIENT, mechanism unchanged, because the
 * reasons are the same here: a chat answer is read as it arrives, so this
 * streams ONE model and only moves to the next if the first failed before it
 * said anything. Once a model has started answering, its answer is the
 * answer; a failure after that ends the turn with what was heard and says so.
 * (The Analysis note is different — it wants one finished JSON object and
 * will wait for it; see server/newsterminal/report.py.)
 *
 * THE MODEL. `NT_CHAT_MODEL` first, so the chat can run on a faster model
 * than the notes; else `NT_REPORT_MODEL`, so one key and one setting run both
 * (owner, 2026-10-14: "uses our llm model"); else the report's default. Then
 * the report's own fallback chain — a `:free` model shares a provider pool
 * that saturates, and a second model beats an error.
 */

const ENDPOINT = "https://openrouter.ai/api/v1/chat/completions";
/** The report's default and fallbacks (report.py DEFAULT_MODEL / FALLBACK_MODELS). */
const DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl:free";
const FALLBACK_MODELS = ["dots-studio/dots-3-note-preview:free", "xingchen-agi/xing4.0-29b-a4b:free"];
/** Silence before the first token — the model never started; try the next one. */
const FIRST_TOKEN_MS = 45_000;
/** Silence mid-answer — the model stalled; the answer ends where it stopped. */
const IDLE_MS = 30_000;
/** The whole turn, every model included. */
const BUDGET_MS = 120_000;
/** Plenty for an explanation, and a cap on a model that will not stop. */
const MAX_TOKENS = 2_500;
/**
 * How much the model may think before it speaks, as a token cap. Nvidia's free
 * endpoint ignores `effort` (see report.py REASONING): left to itself the model
 * thinks for thousands of tokens, and thinking streams as `reasoning` deltas,
 * not `content` — silence to the first-token timer above, which would move the
 * turn on to the next model. Small on purpose: roughly twenty seconds at the
 * ~55 tokens/s the report measured.
 */
const REASONING_TOKENS = 1_024;

export type ChatMsg = { role: "system" | "user" | "assistant"; content: string };

export type ChatEvent =
  | { t: "delta"; text: string }
  | { t: "done"; model: string; finish: string | null; ms: number }
  | { t: "error"; message: string };

export const NO_KEY =
  "No OPENROUTER_API_KEY. Add one to .env.local and restart the web app — Hermes answers through a model, and there is deliberately no canned reply that would invent a reading.";

export function chatConfig(): { enabled: boolean; model: string } {
  return { enabled: !!process.env.OPENROUTER_API_KEY?.trim(), model: chatModels()[0] };
}

/** The preferred model first, then the report's fallbacks, none twice. */
export function chatModels(): string[] {
  const first = process.env.NT_CHAT_MODEL?.trim() || process.env.NT_REPORT_MODEL?.trim() || DEFAULT_MODEL;
  return [first, ...FALLBACK_MODELS.filter((m) => m !== first)];
}

type Chunk = { done: boolean; value?: Uint8Array; timeout?: boolean };

/** `reader.read()` that gives up after `ms` of silence. */
function readFor(reader: ReadableStreamDefaultReader<Uint8Array>, ms: number): Promise<Chunk> {
  let timer: ReturnType<typeof setTimeout>;
  const quiet = new Promise<Chunk>((res) => {
    timer = setTimeout(() => res({ done: true, timeout: true }), ms);
  });
  return Promise.race([reader.read().finally(() => clearTimeout(timer)), quiet]);
}

function errorText(raw: string): string {
  try {
    const j = JSON.parse(raw) as { error?: { message?: string; metadata?: { raw?: string } } | string };
    if (typeof j.error === "string") return j.error;
    const m = [j.error?.message, j.error?.metadata?.raw].filter(Boolean).join(" — ");
    if (m) return m;
  } catch {
    /* not JSON */
  }
  return raw.slice(0, 300);
}

/** One server-sent line from OpenRouter, as the pieces this module reads. */
function parseSse(data: string): { text: string; finish: string | null; error: string | null } | null {
  try {
    const j = JSON.parse(data) as {
      choices?: { delta?: { content?: string | null }; finish_reason?: string | null }[];
      error?: { message?: string } | string;
    };
    const c = j.choices?.[0];
    return {
      text: c?.delta?.content ?? "",
      finish: c?.finish_reason ?? null,
      error: j.error ? (typeof j.error === "string" ? j.error : (j.error.message ?? "provider error mid-stream")) : null,
    };
  } catch {
    return null;
  }
}

/**
 * Stream one answer. Yields deltas as they arrive, then exactly one `done`
 * or `error`. Never throws; a cancelled `signal` ends the stream quietly.
 */
export async function* streamChat(messages: ChatMsg[], signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const key = process.env.OPENROUTER_API_KEY?.trim();
  if (!key) {
    yield { t: "error", message: NO_KEY };
    return;
  }

  const started = Date.now();
  const failures: string[] = [];
  for (const model of chatModels()) {
    if (signal?.aborted) return;
    if (BUDGET_MS - (Date.now() - started) < 5_000) break;

    const ctrl = new AbortController();
    const onOuter = () => ctrl.abort();
    signal?.addEventListener("abort", onOuter, { once: true });
    const t0 = Date.now();
    let spoke = false;
    let finish: string | null = null;
    try {
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "http://localhost:3100",
          "X-Title": "HERMESX",
        },
        body: JSON.stringify({
          model,
          messages,
          stream: true,
          temperature: 0.3,
          max_tokens: MAX_TOKENS,
          reasoning: { max_tokens: REASONING_TOKENS },
        }),
        signal: ctrl.signal,
        cache: "no-store",
      });
      if (!r.ok || !r.body) {
        const msg = errorText(await r.text().catch(() => ""));
        // A bad key or an empty balance is not a model problem — the next
        // model would fail the same way, so say it now.
        if (r.status === 401 || r.status === 402 || r.status === 403) {
          yield { t: "error", message: `OpenRouter HTTP ${r.status}: ${msg}` };
          return;
        }
        failures.push(`${model}: HTTP ${r.status}${msg ? ` — ${msg.slice(0, 160)}` : ""}`);
        continue;
      }

      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let midError: string | null = null;
      for (;;) {
        const budget = Math.min(spoke ? IDLE_MS : FIRST_TOKEN_MS, BUDGET_MS - (Date.now() - started));
        const { done, value, timeout } = await readFor(reader, Math.max(1_000, budget));
        if (timeout) {
          void reader.cancel().catch(() => {});
          if (!spoke) {
            failures.push(`${model}: silent for ${Math.round(budget / 1000)}s`);
            break;
          }
          finish = "idle";
          break;
        }
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          // ": OPENROUTER PROCESSING" and friends are keep-alives.
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") continue;
          const p = parseSse(data);
          if (!p) continue;
          if (p.text) {
            spoke = true;
            yield { t: "delta", text: p.text };
          }
          if (p.finish) finish = p.finish;
          if (p.error) midError = p.error;
        }
      }
      if (spoke) {
        if (midError) yield { t: "error", message: `The model stopped early: ${midError.slice(0, 200)}` };
        else yield { t: "done", model, finish, ms: Date.now() - t0 };
        return;
      }
      if (midError) failures.push(`${model}: ${midError.slice(0, 160)}`);
      else if (!failures.some((f) => f.startsWith(`${model}:`))) failures.push(`${model}: empty answer`);
    } catch (e) {
      if (signal?.aborted) return;
      if (spoke) {
        yield { t: "error", message: `The connection dropped mid-answer: ${e instanceof Error ? e.message : String(e)}` };
        return;
      }
      failures.push(`${model}: unreachable — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      signal?.removeEventListener("abort", onOuter);
    }
  }

  const secs = Math.round((Date.now() - started) / 1000);
  const every429 = failures.length > 0 && failures.every((f) => /HTTP 429/.test(f));
  yield {
    t: "error",
    message: every429
      ? `Every model is rate-limited right now (${failures.length} tried in ${secs}s). OpenRouter's free tier limits requests per minute and per day — wait a minute and ask again, or set NT_CHAT_MODEL to another model.`
      : `No model answered in ${secs}s. ${failures.join(" · ") || "The budget ran out before any attempt."}`,
  };
}
