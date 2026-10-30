/**
 * The chat's wire format, read once for both faces of Hermes — the panel
 * beside the page (AskPanel) and the tab of its own (HermesTab).
 *
 * NDJSON, one object per line: `delta` as the model writes, `thinking` while
 * it reasons before it speaks (the free reasoning models stream their
 * thinking on a channel of its own, which the reader would otherwise see as
 * silence), `tool` when it asks the collector for something (the tab only),
 * then exactly one `done` — with the numerals the check could not find — or
 * one `error`.
 */
export type Line =
  | { t: "delta"; text: string }
  | { t: "thinking" }
  | { t: "tool"; name: string; args: Record<string, unknown> }
  | {
      t: "done";
      model: string;
      finish: string | null;
      ms?: number;
      unverified?: string[];
      /** Figures an earlier answer carried that this turn's data does not — stale, not invented. */
      carried?: string[];
      usage?: { prompt: number; cached: number; completion: number; cost: number };
      /** How the router treated the question (the Hermes tab only). */
      route?: { tier: "quick" | "full"; desk: "futures" | "stocks" | "both" };
    }
  | { t: "error"; message: string };

/** "nemotron-3.5-super-vl (free)" from "nvidia/nemotron-3.5-super-vl:free". */
/** A token count as a footer shows it: "840", "3.1k", "47k". */
export function tokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

export const shortModel = (m: string) => m.split("/").pop()?.replace(/:free$/, " (free)") ?? m;

/** What a tool call is doing, in the words the pending line shows. */
export function describeTool(name: string, args: Record<string, unknown>): string {
  const s = (k: string) => (typeof args[k] === "string" ? (args[k] as string) : "");
  switch (name) {
    case "scanner_row":
      return `Reading ${s("sym").toUpperCase() || "the"} scanner row`;
    case "bars":
      return `Reading ${s("sym").toUpperCase()} ${s("tf") || "10m"} bars`;
    case "wire":
      return s("query") ? `Searching the wire for “${s("query")}”` : "Reading the wire";
    case "levels":
      return `Reading ${s("book") || "the"} levels`;
    case "heavyweights":
      return `Reading the ${s("book") || "index"} heavyweights`;
    case "event_risk":
      return "Reading the event risk";
    case "earnings":
      return "Reading earnings";
    case "calendar":
      return `Reading the calendar for ${s("day") || "today"}`;
    case "sessions":
      return "Reading the session clock";
    case "digest":
      return `Reading the ${s("desk") || "futures"} digest`;
    case "note":
      return `Reading the latest ${s("kind") === "plan" ? "game plan" : "brief"}`;
    default:
      return `Reading ${name}`;
  }
}

/**
 * Read a streamed answer to its end, applying each line as it lands. A line
 * that is not JSON is skipped; the last line needs no newline.
 */
export async function readNdjson(body: ReadableStream<Uint8Array>, apply: (line: Line) => void): Promise<void> {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  const take = (raw: string) => {
    const line = raw.trim();
    if (!line) return;
    let ev: Line;
    try {
      ev = JSON.parse(line) as Line;
    } catch {
      return;
    }
    apply(ev);
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      take(buf.slice(0, nl));
      buf = buf.slice(nl + 1);
    }
  }
  take(buf);
}
