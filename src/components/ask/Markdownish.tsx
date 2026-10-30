import type { ReactNode } from "react";

/**
 * The little Markdown a chat answer actually uses — paragraphs, bullet and
 * numbered lists, short headings, a small table, **bold**, *italic* and
 * `code` — and nothing else.
 *
 * NOT A MARKDOWN LIBRARY, on purpose (the same call GEXYGEN's assistant
 * made). A full renderer would add a dependency, a sanitiser and a surface
 * for things the panel has no room for. Anything this does not recognise
 * renders as the text it is, which is also what makes it safe on a
 * HALF-STREAMED answer: an unclosed `**` is just two asterisks until its
 * partner arrives, and a table is a table only once its header rule has
 * landed — before that it is a line of text with bars in it.
 *
 * HEADINGS AND TABLES ARRIVED WITH THE HERMES TAB (2026-10-30), whose prompt
 * invites them for a run-down. In the panel they were turned into bold
 * lines; here a heading is a heading — a bold line with air above it — and a
 * table is a table. The panel's prompt still asks for neither, so the panel
 * is unchanged in practice.
 */
export function Markdownish({ text }: { text: string }) {
  const blocks = text.replace(/\r\n/g, "\n").trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trimEnd());
        // A heading, or a line that is wholly bold, leading a block: the
        // title of what follows. The model often writes "## Beats" and the
        // bullets under it with no blank line between.
        const title = lines.length > 1 && (HEADING.test(lines[0]) || BOLD_LINE.test(lines[0])) ? lines[0] : null;
        const body = title ? lines.slice(1) : lines;
        return (
          <div key={i} className="my-2 first:mt-0 last:mb-0">
            {title && <Heading line={title} />}
            {body.length > 0 && <Body lines={body} />}
          </div>
        );
      })}
    </>
  );
}

const HEADING = /^#{1,6}\s+(.*)$/;
const BOLD_LINE = /^\*\*[^*\n]+\*\*:?$/;
const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function Heading({ line }: { line: string }) {
  const m = HEADING.exec(line);
  const textOf = m ? m[1] : line.replace(/^\*\*|\*\*:?$/g, "");
  return <p className="mt-3 mb-1 text-[0.95em] font-semibold text-ink first:mt-0">{inline(textOf)}</p>;
}

function Body({ lines }: { lines: string[] }) {
  if (lines.every((l) => BULLET.test(l))) {
    return (
      <ul className="my-1.5 list-disc space-y-1 pl-4 marker:text-ink-4">
        {lines.map((l, j) => (
          <li key={j}>{inline(l.replace(BULLET, ""))}</li>
        ))}
      </ul>
    );
  }
  if (lines.every((l) => NUMBERED.test(l))) {
    return (
      <ol className="my-1.5 list-decimal space-y-1 pl-4 marker:text-ink-4">
        {lines.map((l, j) => (
          <li key={j}>{inline(l.replace(NUMBERED, ""))}</li>
        ))}
      </ol>
    );
  }
  if (lines.length >= 2 && lines.every((l) => TABLE_ROW.test(l) || TABLE_RULE.test(l)) && TABLE_RULE.test(lines[1])) {
    return <Table lines={lines} />;
  }
  if (lines.length === 1 && HEADING.test(lines[0])) return <Heading line={lines[0]} />;
  // A heading the model drew mid-paragraph becomes a bold line, not a header.
  const para = lines.map((l) => l.replace(HEADING, "**$1**"));
  return (
    <p className="my-1.5 first:mt-0 last:mb-0">
      {para.map((l, j) => (
        <span key={j}>
          {j > 0 && <br />}
          {inline(l)}
        </span>
      ))}
    </p>
  );
}

/** `| a | b |` rows into cells; the outer bars are optional and dropped. */
function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

function Table({ lines }: { lines: string[] }) {
  const head = cells(lines[0]);
  const rows = lines.slice(2).filter((l) => !TABLE_RULE.test(l)).map(cells);
  return (
    <div className="my-2 overflow-x-auto">
      <table className="w-auto min-w-[50%] border-collapse text-[0.95em]">
        <thead>
          <tr>
            {head.map((h, j) => (
              <th key={j} className="border-b border-ring-2 px-2.5 py-1 text-left font-semibold text-ink">
                {inline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-ring/60 last:border-b-0">
              {head.map((_, j) => (
                <td key={j} className="px-2.5 py-1 align-top text-ink-2">
                  {inline(r[j] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TOKEN = /(\*\*[^*\n]+\*\*|`[^`\n]+`|(?<![\w*])\*[^*\n]+\*(?![\w*]))/g;

function inline(s: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of s.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(s.slice(last, at));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<b key={at} className="font-semibold text-ink">{tok.slice(2, -2)}</b>);
    else if (tok.startsWith("`")) out.push(<code key={at} className="fig rounded-[3px] border border-ring px-1 text-[11px] text-ink">{tok.slice(1, -1)}</code>);
    else out.push(<i key={at}>{tok.slice(1, -1)}</i>);
    last = at + tok.length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}
