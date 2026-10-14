import type { ReactNode } from "react";

/**
 * The little Markdown a chat answer actually uses — paragraphs, bullet and
 * numbered lists, **bold** and `code` — and nothing else.
 *
 * NOT A MARKDOWN LIBRARY, on purpose (the same call GEXYGEN's assistant
 * made). The prompt asks for short prose with the odd list; a full renderer
 * would add a dependency, a sanitiser and a surface for tables and headings
 * the panel has no room for. Anything this does not recognise renders as the
 * text it is, which is also what makes it safe on a HALF-STREAMED answer: an
 * unclosed `**` is just two asterisks until its partner arrives.
 */
export function Markdownish({ text }: { text: string }) {
  const blocks = text.replace(/\r\n/g, "\n").trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trimEnd());
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={i} className="my-1.5 list-disc space-y-1 pl-4 marker:text-ink-4">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        if (lines.every((l) => /^\s*\d+[.)]\s+/.test(l))) {
          return (
            <ol key={i} className="my-1.5 list-decimal space-y-1 pl-4 marker:text-ink-4">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*\d+[.)]\s+/, ""))}</li>
              ))}
            </ol>
          );
        }
        // A heading the model drew anyway becomes a bold line, not a header.
        const para = lines.map((l) => l.replace(/^#{1,6}\s+(.*)$/, "**$1**"));
        return (
          <p key={i} className="my-1.5 first:mt-0 last:mb-0">
            {para.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(l)}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}

const TOKEN = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function inline(s: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of s.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(s.slice(last, at));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<b key={at} className="font-semibold text-ink">{tok.slice(2, -2)}</b>);
    else out.push(<code key={at} className="fig rounded-[3px] border border-ring px-1 text-[11px] text-ink">{tok.slice(1, -1)}</code>);
    last = at + tok.length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}
