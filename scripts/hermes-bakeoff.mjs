#!/usr/bin/env node
/**
 * Hermes model bake-off — the same questions, the same slim prompt and the
 * same tools, on several models, with what each answer cost (2026-10-30).
 *
 *   node scripts/hermes-bakeoff.mjs
 *   node scripts/hermes-bakeoff.mjs --models anthropic/claude-haiku-5.5,deepseek/deepseek-v4.1-flash
 *   node scripts/hermes-bakeoff.mjs --questions 3 --out docs/hermes-bakeoff.md
 *
 * Needs the collector (8100) and the web app (3100) running, and the
 * OpenRouter key in .env.local or the environment. The system prompt is the
 * one the tab itself would send right now (GET /api/ask?dry=1&tab=hermes&slim=1),
 * the tool list is the collector's (GET /api/ask/tools) and tool calls are run
 * on the collector (POST /api/ask/tool), so the only variable is the model.
 *
 * The rounds are the tab's (src/lib/ask/llm.ts `rounds`): non-streamed, up to
 * six tool rounds, then an answer in words. `usage.cost` is OpenRouter's own
 * figure. The numeral check is a port of prompt.ts unverifiedNumerals: every
 * figure in an answer must appear in the prompt, the question or a tool result.
 *
 * The report is Markdown: one summary table, then every answer, so the judge
 * of quality is you.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = process.env.NT_WEB ?? "http://localhost:3100";
const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const ENDPOINT = "https://openrouter.ai/api/v1/chat/completions";

const DEFAULT_MODELS = [
  "nvidia/nemotron-3.5-super-vl:free", // the tab's default — the baseline
  "anthropic/claude-haiku-5.5",
  "google/gemini-3.8-flash",
  "deepseek/deepseek-v4.1-flash",
  "deepseek/deepseek-v4-pro",
];

const QUESTIONS = [
  "What is AMZN's setup right now, and is it worth a trade today?",
  "Why is NQ down overnight? What moved it?",
  "Give me the NQ levels that matter for the New York open.",
  "Which earnings printed since yesterday's close, and which are ahead today?",
  "What's on the calendar today that could move ES?",
  "Compare the top three scanner names and tell me which has the cleanest break-and-retest.",
  "What did the latest brief say, and does the data still support it?",
  "Is gold a short here? Where would that be wrong?",
];

// The tab's own budgets (llm.ts hermesOptions / rounds).
const MAX_TOKENS = 6_000;
const REASONING_TOKENS = 3_000;
const MAX_ROUNDS = 6;
const ROUND_MS = 180_000;
const TOOL_RESULT_CHARS = 24_000;

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function key() {
  if (process.env.OPENROUTER_API_KEY?.trim()) return process.env.OPENROUTER_API_KEY.trim();
  try {
    for (const line of readFileSync(resolve(ROOT, ".env.local"), "utf-8").split(/\r?\n/)) {
      const m = /^\s*OPENROUTER_API_KEY\s*=\s*(.+?)\s*$/.exec(line);
      if (m) return m[1].replace(/^["']|["']$/g, "");
    }
  } catch {
    /* no .env.local */
  }
  throw new Error("No OPENROUTER_API_KEY in the environment or .env.local");
}

async function json(url, init) {
  const r = await fetch(url, { ...init, signal: AbortSignal.timeout(60_000) });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

// ---- the numeral check, ported from src/lib/ask/prompt.ts ----------------
const NUM = /\d+(?:[.,]\d+)*/g;
function numKey(tok) {
  const grouped = /^\d{1,3}(?:,\d{3})+(?:\.\d+)?$/.test(tok);
  const clean = grouped ? tok.replace(/,/g, "") : tok.split(",")[0];
  const v = Number(clean);
  return Number.isFinite(v) ? String(Math.round(v * 10_000) / 10_000) : null;
}
function numeralsIn(s) {
  const out = [];
  for (const m of s.matchAll(NUM)) {
    const k = numKey(m[0]);
    if (k != null) out.push(k);
  }
  return out;
}
function twoPlaces(k) {
  const m = /^(\d+)\.(\d{3,})$/.exec(k);
  if (!m) return null;
  let whole = Number(m[1]);
  let cents = Number(m[2].slice(0, 2)) + (Number(m[2][2]) >= 5 ? 1 : 0);
  if (cents === 100) {
    cents = 0;
    whole += 1;
  }
  return String(Number(`${whole}.${String(cents).padStart(2, "0")}`));
}
function unverifiedNumerals(answer, known) {
  const k = new Set(known);
  for (const n of [...k]) {
    const t = twoPlaces(n);
    if (t != null) k.add(t);
  }
  const bad = new Set();
  for (const n of numeralsIn(answer)) {
    if (k.has(n)) continue;
    if (/^\d{1,2}$/.test(n) && Number(n) <= 12) continue;
    bad.add(n);
  }
  return [...bad];
}

// ---- one turn, as the tab runs it -----------------------------------------
async function turn(model, system, question, tools, apiKey) {
  const convo = [
    { role: "system", content: system },
    { role: "user", content: question },
  ];
  const known = new Set([...numeralsIn(system), ...numeralsIn(question)]);
  const out = { model, question, ms: 0, rounds: 0, calls: [], usage: { prompt: 0, completion: 0, cost: 0 }, text: "", error: null, finish: null, unverified: [] };
  const t0 = Date.now();
  try {
    for (;;) {
      const last = out.rounds >= MAX_ROUNDS;
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json", "HTTP-Referer": "http://localhost:3100", "X-Title": "HERMES bake-off" },
        body: JSON.stringify({
          model,
          messages: convo,
          tools,
          tool_choice: last ? "none" : "auto",
          stream: false,
          temperature: 0.3,
          max_tokens: MAX_TOKENS,
          reasoning: { max_tokens: REASONING_TOKENS },
          usage: { include: true },
        }),
        signal: AbortSignal.timeout(ROUND_MS),
      });
      if (!r.ok) {
        out.error = `HTTP ${r.status}: ${(await r.text()).slice(0, 300)}`;
        break;
      }
      const j = await r.json();
      if (j.error) {
        out.error = typeof j.error === "string" ? j.error : (j.error.message ?? "provider error");
        break;
      }
      const u = j.usage ?? {};
      out.usage.prompt += u.prompt_tokens ?? 0;
      out.usage.completion += u.completion_tokens ?? 0;
      out.usage.cost += u.cost ?? 0;
      const choice = j.choices?.[0];
      const msg = choice?.message ?? {};
      const calls = msg.tool_calls ?? [];
      if (calls.length && !last) {
        convo.push({ role: "assistant", content: msg.content ?? "", tool_calls: calls });
        for (const c of calls) {
          let args = {};
          try {
            args = JSON.parse(c.function.arguments || "{}");
          } catch {
            args = {};
          }
          out.calls.push(`${c.function.name}(${Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})`);
          let result;
          try {
            result = await json(`${API}/api/ask/tool`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: c.function.name, args }) });
          } catch (e) {
            result = { error: String(e) };
          }
          const text = JSON.stringify(result ?? null).slice(0, TOOL_RESULT_CHARS);
          for (const k of numeralsIn(text)) known.add(k);
          convo.push({ role: "tool", tool_call_id: c.id, content: text });
        }
        out.rounds++;
        continue;
      }
      out.text = (msg.content ?? "").trim();
      out.finish = choice?.finish_reason ?? null;
      if (!out.text) out.error = `empty answer after ${out.rounds} rounds`;
      break;
    }
  } catch (e) {
    out.error = e instanceof Error ? e.message : String(e);
  }
  out.ms = Date.now() - t0;
  out.unverified = out.text ? unverifiedNumerals(out.text, known) : [];
  return out;
}

// ---- the run ---------------------------------------------------------------
const apiKey = key();
const models = arg("models", DEFAULT_MODELS.join(",")).split(",").map((s) => s.trim()).filter(Boolean);
const questions = QUESTIONS.slice(0, Number(arg("questions", QUESTIONS.length)));
const stamp = new Date().toISOString().slice(0, 10);
const outPath = resolve(ROOT, arg("out", `docs/hermes-bakeoff-${stamp}.md`));

const dry = await json(`${WEB}/api/ask?dry=1&tab=hermes&slim=1`);
const { tools: spec } = await json(`${API}/api/ask/tools`);
const tools = spec.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.parameters } }));
console.log(`prompt ${dry.chars} chars (~${Math.round(dry.chars / 4)} tokens), ${spec.length} tools, ${questions.length} questions, ${models.length} models`);

// Models in parallel, questions in sequence within each — a free model shares
// a pool and is rate-limited per minute, so its questions must not pile up.
const results = await Promise.all(
  models.map(async (model) => {
    const rows = [];
    for (const q of questions) {
      const r = await turn(model, dry.system, q, tools, apiKey);
      rows.push(r);
      console.log(
        `${model.padEnd(36)} ${String(Math.round(r.ms / 1000)).padStart(4)}s  rounds ${r.rounds}  ${String(r.usage.prompt + r.usage.completion).padStart(6)} tok  $${r.usage.cost.toFixed(4)}  ${r.error ? `ERROR ${r.error.slice(0, 80)}` : `${r.unverified.length} unverified`}  — ${q.slice(0, 50)}`,
      );
    }
    return rows;
  }),
);

// ---- the report ------------------------------------------------------------
const fmt = (n, d = 0) => (Number.isFinite(n) ? n.toFixed(d) : "—");
const lines = [];
lines.push(`# Hermes model bake-off — ${stamp}`, "");
lines.push(`Prompt ${dry.chars} chars (~${Math.round(dry.chars / 4)} tokens) · ${spec.length} tools · ${questions.length} questions · desk as of ${dry.context?.slim?.as_of_et ?? "?"}`, "");
lines.push("| Model | Answered | Avg s | Avg tokens (in / out) | Tool calls / answer | Unverified figures | Cost, all questions |");
lines.push("|---|---|---|---|---|---|---|");
for (const rows of results) {
  const ok = rows.filter((r) => !r.error);
  const avg = (f) => (ok.length ? ok.reduce((a, r) => a + f(r), 0) / ok.length : NaN);
  lines.push(
    `| ${rows[0].model} | ${ok.length}/${rows.length} | ${fmt(avg((r) => r.ms / 1000), 1)} | ${fmt(avg((r) => r.usage.prompt))} / ${fmt(avg((r) => r.usage.completion))} | ${fmt(avg((r) => r.calls.length), 1)} | ${ok.reduce((a, r) => a + r.unverified.length, 0)} | $${rows.reduce((a, r) => a + r.usage.cost, 0).toFixed(4)} |`,
  );
}
lines.push("", "Unverified figures: numerals in the answer that appear nowhere in the prompt, the question or a tool result (the tab's own check). Cost is OpenRouter's `usage.cost`.", "");
questions.forEach((q, qi) => {
  lines.push(`## ${qi + 1}. ${q}`, "");
  for (const rows of results) {
    const r = rows[qi];
    lines.push(`### ${r.model}`, "");
    lines.push(`${(r.ms / 1000).toFixed(1)}s · ${r.rounds} round${r.rounds === 1 ? "" : "s"} · ${r.usage.prompt} in / ${r.usage.completion} out · $${r.usage.cost.toFixed(4)}${r.calls.length ? ` · tools: ${r.calls.join("; ")}` : " · no tools"}${r.unverified.length ? ` · unverified: ${r.unverified.join(", ")}` : ""}`, "");
    if (r.error) lines.push(`**Error:** ${r.error}`, "");
    if (r.text) lines.push(r.text.replace(/^#{1,2} /gm, "#### "), "");
  }
});
mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, lines.join("\n"), "utf-8");
console.log(`\nwrote ${outPath}`);
