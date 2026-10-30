/*
 * SERVER ONLY — the OpenRouter key is read here and never leaves the server.
 * Called from /api/ask; nothing in `components/` imports it.
 */

/**
 * One chat turn for Hermes.
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
 *
 * TWO SEATS, ONE CLIENT (2026-10-30). The panel beside the page wants a quick
 * answer and is capped tightly; the Hermes tab is the reader sitting down
 * with the whole terminal and may think longer and write at length
 * (`hermesOptions`). Same fallbacks, different budgets — and
 * `NT_HERMES_MODEL` lets that tab alone run on a model the owner names.
 *
 * TOOLS (2026-10-30, owner: "how can we make our hermes ai more
 * intelligent?"). Handed `tools` and a way to run one, the turn runs as
 * ROUNDS rather than one stream: the model is asked, and if it asks the
 * collector for something — a name's row, the wire, a ladder — the answer is
 * fetched (server/newsterminal/tools.py) and the model is asked again with
 * it, until it answers in words. The rounds are not streamed, because a
 * tool call is a JSON object that only means something whole; the final
 * answer is handed out in pieces so the page reads it the way it reads the
 * panel. The reader sees each call as it happens (`tool` events), which is
 * the wait explained rather than hidden.
 *
 * WHAT A TURN COSTS IS MEASURED, NOT GUESSED (owner, 2026-10-30: "is there
 * ways to minimise token usage?"). Every request asks OpenRouter for its
 * usage and the `done` event carries it — tokens in, tokens out, how many
 * of the input were read from cache, and the dollar figure — summed over
 * the turn's rounds. Two things act on it here:
 *
 *   `cachePrefix`  The start of the system message that never changes
 *                  between turns (the rules, the tools, the product). An
 *                  Anthropic model caches nothing unless the request marks
 *                  what to cache — measured 2026-10-30: the same prompt sent
 *                  twice read zero from cache; marked, the second read 5,734
 *                  of 9,971 tokens at a tenth of the price. So for an
 *                  Anthropic model the prefix is sent as its own marked part,
 *                  and the reader's latest question is marked too, so a tool
 *                  round re-reads the whole first round from cache. Other
 *                  providers cache on their own and are sent plain text.
 *   `reasoningTokens: 0`
 *                  No thinking at all — the router's quick tier. Thinking is
 *                  output, five times the input price, and "is London open?"
 *                  does not need it.
 */

const ENDPOINT = "https://openrouter.ai/api/v1/chat/completions";
/** The report's default and fallbacks (report.py DEFAULT_MODEL / FALLBACK_MODELS). */
const DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl:free";
const FALLBACK_MODELS = ["dots-studio/dots-3-note-preview:free", "xingchen-agi/xing4.0-29b-a4b:free"];
/**
 * Silence before the first token — the model never started; try the next one.
 * Reasoning counts as sound: a model thinking aloud on its own channel is
 * working, and only a stretch with nothing on either channel is silence.
 */
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
 * thinks for thousands of tokens. Small on purpose for the panel: roughly
 * twenty seconds at the ~55 tokens/s the report measured.
 */
const REASONING_TOKENS = 1_024;
/** How often a `thinking` line is sent while the model reasons — a pulse, not a firehose. */
const THINKING_PULSE_MS = 1_000;
/** Rounds of tool calls before the model is told to answer with what it has. */
const MAX_ROUNDS = 6;
/** One round's own ceiling, within the turn's budget. */
const ROUND_MS = 120_000;
/** A tool's answer, as handed to the model — tools.py caps lower; this is the belt. */
const TOOL_RESULT_CHARS = 24_000;

export type ChatMsg = { role: "system" | "user" | "assistant"; content: string };

/** What a turn cost, summed over its rounds: tokens in, of which read from cache, tokens out, dollars (OpenRouter's own figure). */
export interface Usage {
  prompt: number;
  cached: number;
  completion: number;
  cost: number;
}

type RawUsage =
  | {
      prompt_tokens?: number;
      completion_tokens?: number;
      cost?: number;
      prompt_tokens_details?: { cached_tokens?: number } | null;
    }
  | undefined;

function addUsage(into: Usage, raw: RawUsage): Usage {
  return {
    prompt: into.prompt + (raw?.prompt_tokens ?? 0),
    cached: into.cached + (raw?.prompt_tokens_details?.cached_tokens ?? 0),
    completion: into.completion + (raw?.completion_tokens ?? 0),
    cost: into.cost + (raw?.cost ?? 0),
  };
}
const NO_USAGE: Usage = { prompt: 0, cached: 0, completion: 0, cost: 0 };

export type ChatEvent =
  | { t: "delta"; text: string }
  | { t: "thinking" }
  | { t: "tool"; name: string; args: Record<string, unknown> }
  | { t: "done"; model: string; finish: string | null; ms: number; usage?: Usage }
  | { t: "error"; message: string };

/** A tool as the model is shown it (tools.py SPEC, OpenAI's function shape). */
export interface ToolSpec {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export type ToolRunner = (name: string, args: Record<string, unknown>) => Promise<unknown>;

/** What one seat may spend on a turn. Anything left out takes the panel's figure. */
export interface ChatOptions {
  /** The chain to try, preferred first. */
  models?: string[];
  /** The answer's token cap, thinking included. */
  maxTokens?: number;
  /** The thinking's own cap inside it; 0 turns thinking off. */
  reasoningTokens?: number;
  /** The whole turn, every model included. */
  budgetMs?: number;
  /** The tab's tools and how to run one — with these the turn runs as rounds. */
  tools?: ToolSpec[];
  runTool?: ToolRunner;
  /** Hears every tool result's text, so the route can count its numerals as known. */
  onToolResult?: (text: string) => void;
  maxRounds?: number;
  /** The unchanging start of the system message, cached on providers that need telling. */
  cachePrefix?: string;
}

export const NO_KEY =
  "No OPENROUTER_API_KEY. Add one to .env.local and restart the web app — Hermes answers through a model, and there is deliberately no canned reply that would invent a reading.";

/** The error the rounds end with when no model in the chain takes tools — the route falls back. */
export const TOOLS_UNSUPPORTED = "tools unsupported";

export function chatConfig(models: string[] = chatModels()): { enabled: boolean; model: string } {
  return { enabled: !!process.env.OPENROUTER_API_KEY?.trim(), model: models[0] };
}

/** The preferred model first, then the report's fallbacks, none twice. */
export function chatModels(): string[] {
  const first = process.env.NT_CHAT_MODEL?.trim() || process.env.NT_REPORT_MODEL?.trim() || DEFAULT_MODEL;
  return [first, ...FALLBACK_MODELS.filter((m) => m !== first)];
}

/** The Hermes tab's chain: `NT_HERMES_MODEL` if the owner named one, then the panel's. */
export function hermesModels(): string[] {
  const own = process.env.NT_HERMES_MODEL?.trim();
  const chain = chatModels();
  return own ? [own, ...chain.filter((m) => m !== own)] : chain;
}

/**
 * The tab's budgets. Three thousand thinking tokens is the notes' own cap
 * (report.py REASONING) — about a minute at the measured rate, and the
 * reader sees "Thinking" for all of it rather than a blank line; six thousand
 * for the answer because a run-down with a table is several times a panel
 * reply; five minutes for the turn so a long think, a few tool rounds and a
 * long answer all fit, with a fallback after a quick refusal still possible.
 */
export function hermesOptions(): ChatOptions {
  return { models: hermesModels(), maxTokens: 6_000, reasoningTokens: 3_000, budgetMs: 300_000 };
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

function headers(key: string): Record<string, string> {
  return {
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:3100",
    "X-Title": "HERMES",
  };
}

/** The `reasoning` field: a cap, or off. */
function reasoning(tokens: number): Record<string, unknown> {
  return tokens > 0 ? { max_tokens: tokens } : { enabled: false };
}

type WireMsg = Record<string, unknown>;
const EPHEMERAL = { type: "ephemeral" };

/**
 * The messages as the request carries them. An Anthropic model gets the
 * cache marks — the fixed prefix of the system message as its own part, and
 * the reader's latest question — so the next turn and the next tool round
 * read them from cache (see the file comment). Everyone else gets plain text.
 */
function wire(model: string, messages: ChatMsg[], cachePrefix?: string): WireMsg[] {
  if (!model.startsWith("anthropic/")) return messages.map((m) => ({ ...m }));
  const lastUser = messages.map((m) => m.role).lastIndexOf("user");
  return messages.map((m, i) => {
    if (i === 0 && m.role === "system" && cachePrefix && m.content.startsWith(cachePrefix)) {
      const rest = m.content.slice(cachePrefix.length);
      return {
        role: "system",
        content: [{ type: "text", text: cachePrefix, cache_control: EPHEMERAL }, ...(rest ? [{ type: "text", text: rest }] : [])],
      };
    }
    if (i === lastUser) return { role: "user", content: [{ type: "text", text: m.content, cache_control: EPHEMERAL }] };
    return { ...m };
  });
}

/** One server-sent line from OpenRouter, as the pieces this module reads. */
function parseSse(data: string): { text: string; thinking: boolean; finish: string | null; error: string | null; usage: RawUsage } | null {
  try {
    const j = JSON.parse(data) as {
      choices?: {
        delta?: { content?: string | null; reasoning?: string | null; reasoning_details?: unknown[] };
        finish_reason?: string | null;
      }[];
      usage?: RawUsage;
      error?: { message?: string } | string;
    };
    const c = j.choices?.[0];
    const d = c?.delta;
    return {
      text: d?.content ?? "",
      thinking: !!d?.reasoning || (Array.isArray(d?.reasoning_details) && d.reasoning_details.length > 0),
      finish: c?.finish_reason ?? null,
      error: j.error ? (typeof j.error === "string" ? j.error : (j.error.message ?? "provider error mid-stream")) : null,
      usage: j.usage,
    };
  } catch {
    return null;
  }
}

/** A finished answer in pieces of about eighty characters, cut at spaces. */
function* pieces(text: string): Generator<string> {
  let at = 0;
  while (at < text.length) {
    let end = Math.min(text.length, at + 80);
    if (end < text.length) {
      const sp = text.lastIndexOf(" ", end);
      if (sp > at + 20) end = sp + 1;
    }
    yield text.slice(at, end);
    at = end;
  }
}

/** A signal that aborts on the outer one OR after `ms`, and the cleanup for it. */
function leash(outer: AbortSignal | undefined, ms: number): { signal: AbortSignal; release: () => void } {
  const ctrl = new AbortController();
  const onOuter = () => ctrl.abort();
  outer?.addEventListener("abort", onOuter, { once: true });
  const timer = setTimeout(() => ctrl.abort(), ms);
  return {
    signal: ctrl.signal,
    release: () => {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onOuter);
    },
  };
}

/**
 * Stream one answer. Yields deltas as they arrive — and a `thinking` pulse
 * while the model reasons before speaking — then exactly one `done` or
 * `error`. With tools it runs as rounds instead (see the file comment).
 * Never throws; a cancelled `signal` ends the stream quietly.
 */
export async function* streamChat(messages: ChatMsg[], signal?: AbortSignal, opts: ChatOptions = {}): AsyncGenerator<ChatEvent> {
  const key = process.env.OPENROUTER_API_KEY?.trim();
  if (!key) {
    yield { t: "error", message: NO_KEY };
    return;
  }
  if (opts.tools?.length && opts.runTool) {
    yield* rounds(messages, signal, opts, key);
    return;
  }
  const models = opts.models ?? chatModels();
  const budgetMs = opts.budgetMs ?? BUDGET_MS;
  const maxTokens = opts.maxTokens ?? MAX_TOKENS;
  const reasoningTokens = opts.reasoningTokens ?? REASONING_TOKENS;

  const started = Date.now();
  const failures: string[] = [];
  for (const model of models) {
    if (signal?.aborted) return;
    if (budgetMs - (Date.now() - started) < 5_000) break;

    const ctrl = new AbortController();
    const onOuter = () => ctrl.abort();
    signal?.addEventListener("abort", onOuter, { once: true });
    const t0 = Date.now();
    let spoke = false;
    let lastPulse = 0;
    let finish: string | null = null;
    let usage: Usage | undefined;
    try {
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: headers(key),
        body: JSON.stringify({
          model,
          messages: wire(model, messages, opts.cachePrefix),
          stream: true,
          temperature: 0.3,
          max_tokens: maxTokens,
          reasoning: reasoning(reasoningTokens),
          usage: { include: true },
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
        const budget = Math.min(spoke ? IDLE_MS : FIRST_TOKEN_MS, budgetMs - (Date.now() - started));
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
          } else if (p.thinking && !spoke && Date.now() - lastPulse >= THINKING_PULSE_MS) {
            lastPulse = Date.now();
            yield { t: "thinking" };
          }
          if (p.finish) finish = p.finish;
          if (p.error) midError = p.error;
          if (p.usage) usage = addUsage(NO_USAGE, p.usage);
        }
      }
      if (spoke) {
        if (midError) yield { t: "error", message: `The model stopped early: ${midError.slice(0, 200)}` };
        else yield { t: "done", model, finish, ms: Date.now() - t0, usage };
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

type ToolCall = { id: string; type?: string; function: { name: string; arguments: string } };
type RoundReply = {
  choices?: { message?: { content?: string | null; tool_calls?: ToolCall[] }; finish_reason?: string | null }[];
  usage?: RawUsage;
  error?: { message?: string } | string;
};

/** The turn as rounds of tool calls, one model at a time, until one answers in words. */
async function* rounds(messages: ChatMsg[], signal: AbortSignal | undefined, opts: ChatOptions, key: string): AsyncGenerator<ChatEvent> {
  const models = opts.models ?? chatModels();
  const budgetMs = opts.budgetMs ?? BUDGET_MS;
  const maxTokens = opts.maxTokens ?? MAX_TOKENS;
  const reasoningTokens = opts.reasoningTokens ?? REASONING_TOKENS;
  const maxRounds = opts.maxRounds ?? MAX_ROUNDS;
  const runTool = opts.runTool!;
  const tools = opts.tools!.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.parameters } }));

  const started = Date.now();
  const failures: string[] = [];
  let refusedTools = 0;
  for (const model of models) {
    if (signal?.aborted) return;
    if (budgetMs - (Date.now() - started) < 5_000) break;
    const convo: WireMsg[] = wire(model, messages, opts.cachePrefix);
    const t0 = Date.now();
    let round = 0;
    let usage = NO_USAGE;
    try {
      for (;;) {
        if (signal?.aborted) return;
        const left = budgetMs - (Date.now() - started);
        if (left < 5_000) {
          failures.push(`${model}: out of time after ${round} rounds`);
          break;
        }
        yield { t: "thinking" };
        const last = round >= maxRounds;
        const { signal: leashed, release } = leash(signal, Math.min(ROUND_MS, left));
        let r: Response;
        try {
          r = await fetch(ENDPOINT, {
            method: "POST",
            headers: headers(key),
            body: JSON.stringify({
              model,
              messages: convo,
              tools,
              tool_choice: last ? "none" : "auto",
              stream: false,
              temperature: 0.3,
              max_tokens: maxTokens,
              reasoning: reasoning(reasoningTokens),
              usage: { include: true },
            }),
            signal: leashed,
            cache: "no-store",
          });
        } finally {
          release();
        }
        if (!r.ok) {
          const msg = errorText(await r.text().catch(() => ""));
          if (r.status === 401 || r.status === 402 || r.status === 403) {
            yield { t: "error", message: `OpenRouter HTTP ${r.status}: ${msg}` };
            return;
          }
          if (r.status === 400 && /tool|function/i.test(msg)) {
            refusedTools++;
            failures.push(`${model}: no tool calling — ${msg.slice(0, 120)}`);
            break;
          }
          failures.push(`${model}: HTTP ${r.status}${msg ? ` — ${msg.slice(0, 160)}` : ""}`);
          break;
        }
        const j = (await r.json()) as RoundReply;
        if (j.error) {
          const m = typeof j.error === "string" ? j.error : (j.error.message ?? "provider error");
          failures.push(`${model}: ${m.slice(0, 160)}`);
          break;
        }
        usage = addUsage(usage, j.usage);
        const choice = j.choices?.[0];
        const msg = choice?.message ?? {};
        const calls = msg.tool_calls ?? [];
        if (calls.length && !last) {
          convo.push({ role: "assistant", content: msg.content ?? "", tool_calls: calls });
          for (const c of calls) {
            let args: Record<string, unknown> = {};
            try {
              const parsed: unknown = JSON.parse(c.function.arguments || "{}");
              if (parsed && typeof parsed === "object") args = parsed as Record<string, unknown>;
            } catch {
              args = {};
            }
            yield { t: "tool", name: c.function.name, args };
            let result: unknown;
            try {
              result = await runTool(c.function.name, args);
            } catch (e) {
              result = { error: e instanceof Error ? e.message : String(e) };
            }
            const text = JSON.stringify(result ?? null).slice(0, TOOL_RESULT_CHARS);
            opts.onToolResult?.(text);
            convo.push({ role: "tool", tool_call_id: c.id, content: text });
          }
          round++;
          continue;
        }
        const text = (msg.content ?? "").trim();
        if (!text) {
          failures.push(`${model}: empty answer after ${round} rounds`);
          break;
        }
        for (const piece of pieces(text)) yield { t: "delta", text: piece };
        yield { t: "done", model, finish: choice?.finish_reason ?? null, ms: Date.now() - t0, usage };
        return;
      }
    } catch (e) {
      if (signal?.aborted) return;
      failures.push(`${model}: unreachable — ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  const secs = Math.round((Date.now() - started) / 1000);
  if (refusedTools > 0 && refusedTools === models.length) {
    yield { t: "error", message: `${TOOLS_UNSUPPORTED}: ${failures.join(" · ")}` };
    return;
  }
  yield { t: "error", message: `No model answered in ${secs}s. ${failures.join(" · ") || "The budget ran out before any attempt."}` };
}

/**
 * One short, non-streamed completion — the chat's rolling summary. Null
 * when nothing answered; the thread simply goes on without one.
 */
export async function completeOnce(messages: ChatMsg[], opts: ChatOptions = {}): Promise<string | null> {
  const key = process.env.OPENROUTER_API_KEY?.trim();
  if (!key) return null;
  const models = opts.models ?? chatModels();
  for (const model of models) {
    const { signal, release } = leash(undefined, 60_000);
    try {
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: headers(key),
        body: JSON.stringify({
          model,
          messages: wire(model, messages),
          stream: false,
          temperature: 0.2,
          max_tokens: opts.maxTokens ?? 400,
          reasoning: reasoning(opts.reasoningTokens ?? 256),
        }),
        signal,
        cache: "no-store",
      });
      if (!r.ok) continue;
      const j = (await r.json()) as RoundReply;
      const text = (j.choices?.[0]?.message?.content ?? "").trim();
      if (text) return text;
    } catch {
      /* the next model */
    } finally {
      release();
    }
  }
  return null;
}
