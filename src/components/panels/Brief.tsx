"use client";

import type {
  Book,
  BriefBody,
  BriefCall,
  BriefFacts,
  BriefGamma,
  BriefLadder,
  BriefLadderRow,
  BriefRead,
  BriefSnapshotRow,
  Report,
  Tone,
} from "@/types/terminal";
import { biasInk, biasLabel, convictionWord } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { bp, dir, num, pct, signed } from "@/lib/format";

/**
 * The session brief — the model's read, laid out like a desk's morning note.
 *
 * TWO AUTHORS ON ONE PAGE, AND THE SPLIT IS THE POINT. Every table here — the
 * snapshot, the levels ladder, the gamma card, the catalysts, the ratio strip,
 * the headline list — is printed from `rep.facts`, which the collector computed
 * from the snapshot. The model's answer supplies only words: the thesis, the
 * calls, the regime chains and reads, and short notes joined onto table rows
 * by id. So a call wall on this page cannot be a model's transcription error,
 * and a note for a row that does not exist never arrives here: the server
 * dropped it (`sanitize_brief`).
 *
 * THE SERIF APPEARS NOWHERE ELSE IN THE PRODUCT. The terminal is an instrument
 * you operate; this tab is a document you read top to bottom before a session,
 * and the owner's own brief — the page this was modelled on — reads that way
 * because its headings are set like one.
 *
 * THE HUES ARE THE TERMINAL'S, NOT THE SOURCE BRIEF'S. That page drew the flip
 * purple and every wall amber. Here amber is the flip and teal and magenta are
 * the call and put walls, exactly as the Gamma panel and GEXYGEN draw them —
 * a wall that changed colour between two tabs of one product would be a lie
 * told by a stylesheet.
 */

// The name a reader says, not the ticker they type (owner, 2026-09-22: "Nasdaq",
// as GC was already "Gold"). The pickers and the terminal panels keep the ticker.
const BOOK_NAME: Record<Book, string> = { NQ: "Nasdaq", ES: "ES", GC: "Gold" };

const TONE_HUE: Record<Tone, string> = {
  bear: "var(--put)",
  bull: "var(--call)",
  mixed: "var(--flip)",
  neutral: "var(--ink-3)",
};

const KIND_HUE: Record<BriefLadderRow["kind"], string> = {
  flip: "var(--flip)",
  call: "var(--call)",
  put: "var(--put)",
  range: "var(--ink-2)",
  em: "var(--em)",
  ref: "var(--ring-2)",
  last: "var(--spot)",
};

const LEGEND: [BriefLadderRow["kind"], string][] = [
  ["flip", "Gamma flip"],
  ["call", "Call wall"],
  ["put", "Put wall"],
  ["range", "Session range"],
  ["em", "Expected move"],
  ["ref", "Reference"],
];

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function tint(hue: string, amount: number): string {
  return `color-mix(in oklab, ${hue} ${amount}%, transparent)`;
}

/**
 * THE MEASURE, HELD BACK WHILE THE PAGE WIDENS.
 *
 * The brief used to be one 880px column for everything, which left most of a
 * desk monitor empty — the panel's own column runs past 1400px at 1920. The
 * article now takes that room, but width is only a gift to the things that are
 * WIDE BY NATURE: the snapshot and catalyst tables (all `w-full`), the ladders
 * and gamma cards, which go two-up and get real columns instead of cramped
 * ones.
 *
 * Running text is not one of those things. Prose has a comfortable line length
 * regardless of the glass it is displayed on, and body copy set at 13.5px was
 * already reaching ~135 characters inside the old 880px — past comfortable, not
 * short of it. So the paragraphs keep the width they have always had while
 * everything around them expands: nothing reads worse than before, and the
 * space goes where it buys something.
 */
const MEASURE = "max-w-[840px]";

export function Brief({ rep }: { rep: Report }) {
  const b = rep.report as BriefBody;
  const f = rep.facts as BriefFacts;
  const watch = new Map(b.snapshot_watch.map((w) => [w.key, w.note]));
  const callOf = new Map(b.calls.map((c) => [c.book, c]));
  /*
   * Was the session ALREADY TRADING when this note was written? Older reports
   * predate the flag and were genuinely composed as pre-open notes, so absent
   * means false and the original headings are the honest ones for them.
   */
  const live = rep.session_underway === true;

  return (
    <article className="w-full px-5 pt-4 pb-6">
      {/*
        * THE MASTHEAD. This was a 13.5px bold sans label, and it looked wrong
        * without saying why (owner, 2026-09-22): it is the document's TITLE and
        * it was set smaller than the document's own section headings, in the
        * one face no other heading here uses — so it read as a stray caption
        * floating over the thesis. It is now what it is: the brief's serif, a
        * step above the sections, on a rule that separates the name of the
        * document from the first thing the document says. Title case stays —
        * that was chosen on purpose.
        */}
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-ring/60 pb-3">
        <h1 className="font-serif text-[23.5px] leading-tight font-normal text-ink">
          {rep.session_label} Session Brief
        </h1>
        <span className="fig text-[11.5px] text-ink-3">{f.as_of}</span>
      </header>

      {f.partial.length > 0 && (
        <div className="mt-3 border-l-[3px] border-warn bg-warn/10 px-3 py-2 text-[11.5px] leading-relaxed text-warn">
          <strong className="font-semibold">Partial data.</strong>
          {f.partial.map((p, i) => (
            <div key={i}>{p}</div>
          ))}
        </div>
      )}

      {/* A clear step under the 23.5px masthead: at 22 against 25 the two read as
          one size and the title stopped looking like the title. */}
      <p className={cn("mt-4 font-serif text-[18.5px] leading-[1.45] text-ink", MEASURE)}>
        {b.thesis}
      </p>

      <Calls calls={b.calls} live={live} />

      {f.snapshot.length > 0 && (
        <Section title="Snapshot">
          <Snapshot rows={f.snapshot} watch={watch} />
        </Section>
      )}

      {f.ladders.length > 0 && (
        <Section title="Levels">
          <Legend />
          <div className={cn("grid gap-x-8 gap-y-6", f.ladders.length > 1 && "lg:grid-cols-2")}>
            {f.ladders.map((l) => (
              <Ladder key={l.book} l={l} />
            ))}
          </div>
        </Section>
      )}

      {f.gamma.length > 0 && (
        <Section title="Dealer gamma">
          <div className={cn("grid gap-3", f.gamma.length > 1 && "lg:grid-cols-2")}>
            {f.gamma.map((g) => (
              <GammaCard key={g.book} g={g} />
            ))}
          </div>
          {b.gamma_read && <P className="mt-3">{b.gamma_read}</P>}
        </Section>
      )}

      <Catalysts f={f} b={b} />

      {b.reads.length > 0 && (
        <Section title="The read">
          {b.reads.map((r) => (
            <Read key={r.book} r={r} call={callOf.get(r.book)} live={live} />
          ))}
        </Section>
      )}

      <Rotation f={f} b={b} />
      <Headlines f={f} b={b} />

      {(b.cross_asset || b.risks.length > 0) && (
        <Section title="Cross-asset">
          {b.cross_asset && (
            <p className={cn("font-serif text-[16px] leading-relaxed text-ink", MEASURE)}>
              {b.cross_asset}
            </p>
          )}
          {b.risks.length > 0 && (
            <>
              <Label className="mt-4">Risks</Label>
              <ul className="space-y-1">
                {b.risks.map((x, i) => (
                  <li key={i} className="text-[12.5px] leading-snug text-ink-2">
                    · {x}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}
    </article>
  );
}

/* ---------------------------------------------------------------- the calls */

function Calls({ calls, live }: { calls: BriefCall[]; live?: boolean }) {
  return (
    <div
      className={cn(
        "mt-5 grid gap-2.5",
        calls.length > 1 && "sm:grid-cols-2",
        calls.length > 2 && "lg:grid-cols-3",
      )}
    >
      {calls.map((c) => {
        const ink = biasInk(c.open_bias);
        return (
          <div
            key={c.book}
            className="border-t-[3px] px-3.5 pt-3 pb-3.5"
            style={{ borderColor: ink, background: tint(ink, 10) }}
          >
            <div className="text-[16px] font-semibold text-ink-3">{BOOK_NAME[c.book]}</div>
            <div className="mt-0.5 font-serif text-[29px] leading-9" style={{ color: ink }}>
              {biasLabel(c.open_bias)}
            </div>
            <div className="mt-0.5 mb-3 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-3">
              <span>
                {convictionWord(c.conviction)} conviction {live ? "from here" : "at the open"}
              </span>
              <Pips n={c.conviction} hue={ink} />
            </div>
            {/*
              * THE REASONING SITS ON THE CARD, NOT IN THE READ BELOW IT. A bias
              * and a conviction score with no "because" is a number that cannot
              * be argued with; the owner asked for the call to explain itself.
              * Each line names its layer, so a macro reason and a structure
              * reason cannot be blurred into one sentence — and a conflict
              * between them is visible as two lines that disagree.
              */}
            {c.why && c.why.length > 0 && (
              <>
                <Label>Why</Label>
                <ul className="mb-3 space-y-1">
                  {c.why.map((w, i) => (
                    <li key={i} className="flex gap-1.5 text-[12.5px] leading-snug text-ink">
                      <span aria-hidden className="text-ink-3">
                        ·
                      </span>
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <Label>{live ? "Rest of session" : "Rest of day"}</Label>
            <div className="mb-2.5 text-[13.5px] leading-snug text-ink">
              {c.rest_of_day || biasLabel(c.rest_of_day_bias)}
            </div>
            {c.wrong_if && (
              <>
                <Label>Wrong if</Label>
                <div className="text-[13.5px] leading-snug font-semibold text-ink">
                  {c.wrong_if}
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Pips({ n, hue }: { n: number; hue: string }) {
  return (
    <span
      className="flex items-center gap-[3px]"
      title={`Conviction ${n}/5 — the model's own confidence, not a probability`}
    >
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className="h-[8px] w-[8px] rounded-full"
          style={{ background: i <= n ? hue : "var(--ring-2)" }}
        />
      ))}
    </span>
  );
}

/* ---------------------------------------------------------------- snapshot */

function Snapshot({ rows, watch }: { rows: BriefSnapshotRow[]; watch: Map<string, string> }) {
  return (
    <>
      <table className="w-full border-collapse">
        <tbody>
          {rows.map((row) => {
            const note = watch.get(row.key);
            const value =
              row.last2 !== null && row.last2 !== undefined
                ? `${num(row.last, row.dp)} / ${num(row.last2, row.dp)}`
                : `${num(row.last, row.dp)}${row.last !== null ? row.suffix : ""}`;
            return (
              <tr key={row.key} className="border-b border-ring/60 align-top">
                <td className="py-2 pr-2">
                  <div className="text-[13px] font-semibold text-ink">
                    {row.label}
                    {note !== undefined && (
                      <span className="ml-1.5 align-[2px] text-[9px] text-flip" title="Flagged to watch">
                        ●
                      </span>
                    )}
                  </div>
                  {row.sub && <div className="text-[11px] leading-snug text-ink-3">{row.sub}</div>}
                  {note && <div className="text-[11.5px] leading-snug text-ink-2">{note}</div>}
                </td>
                <td className="fig px-2 py-2 text-right text-[13px] whitespace-nowrap text-ink">
                  {value}
                </td>
                <td className="fig py-2 text-right text-[12px] whitespace-nowrap">
                  <Change row={row} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {watch.size > 0 && (
        <div className="mt-2 text-[11px] text-ink-3">
          <span className="text-[9px] text-flip">●</span> flagged to watch
        </div>
      )}
    </>
  );
}

function Change({ row }: { row: BriefSnapshotRow }) {
  if (row.chg === null || row.chg === undefined) {
    return <span className="text-ink-3">{row.tag ?? ""}</span>;
  }
  const d = dir(row.chg);
  const text =
    row.chg_unit === "bp" ? bp(row.chg) : row.chg_unit === "pts" ? signed(row.chg, row.dp) : pct(row.chg);
  return (
    <span className={d}>
      <span className="mr-1 align-[1px] text-[8px]">{d === "up" ? "▲" : d === "down" ? "▼" : "–"}</span>
      {text}
      {row.tag ? ` · ${row.tag}` : ""}
    </span>
  );
}

/* ---------------------------------------------------------------- levels */

function Legend() {
  return (
    <div className="-mt-1 mb-4 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-3">
      {LEGEND.map(([k, label]) => (
        <span key={k} className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <span className="inline-block h-2 w-2" style={{ background: KIND_HUE[k] }} />
          {label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <span className="inline-block h-2 w-3 bg-surface-3" />
        Inside the expected move
      </span>
    </div>
  );
}

function Ladder({ l }: { l: BriefLadder }) {
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-[14px] font-bold text-ink">{l.label}</span>
        <span className="text-[11px] text-ink-3">
          Last <span className="fig">{num(l.last, l.dp)}</span>
          {l.em !== null && (
            <>
              {" "}
              · expected move <span className="fig">±{num(l.em, l.dp)}</span>
              {l.em_basis && l.em_basis !== "GEXYGEN" && ` (${l.em_basis})`}
            </>
          )}
        </span>
      </div>
      <table className="w-full border-collapse border-t border-ring/60">
        <tbody>
          {l.rows.map((r, i) => {
            const last = r.kind === "last";
            const quiet = r.kind === "em" || r.kind === "ref";
            const ink = last ? "text-bg" : quiet ? "text-ink-3" : "text-ink";
            return (
              <tr
                key={i}
                className="border-b border-ring/60"
                style={{
                  background: last
                    ? "var(--spot)"
                    : r.inside_em
                      ? "color-mix(in oklab, var(--surface-3) 80%, transparent)"
                      : undefined,
                }}
              >
                <td className="w-[4px] p-0" style={{ background: KIND_HUE[r.kind] }} />
                <td
                  className={cn(
                    "fig w-[88px] px-2.5 py-1.5 text-right text-[12.5px] whitespace-nowrap",
                    ink,
                    (last || r.kind === "flip") && "font-bold",
                  )}
                >
                  {num(r.price, l.dp)}
                </td>
                <td
                  className={cn(
                    "px-2.5 py-1.5 text-[12.5px]",
                    ink,
                    (last || r.kind === "flip") && "font-bold",
                    r.kind === "em" && "italic",
                  )}
                >
                  {r.label}
                </td>
                <td
                  className={cn(
                    "fig px-2.5 py-1.5 text-right text-[12px] whitespace-nowrap",
                    last ? "text-bg" : "text-ink-3",
                  )}
                >
                  {r.dist === null ? "" : signed(r.dist, l.dp)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {l.note && <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">{l.note}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- gamma */

function GammaCard({ g }: { g: BriefGamma }) {
  const regime = g.regime === "NEG" ? "Negative gamma" : g.regime === "POS" ? "Positive gamma" : "Gamma";
  const hue = g.regime === "NEG" ? biasInk("bearish") : g.regime === "POS" ? biasInk("bullish") : "var(--ink-2)";
  // flip_dist is flip minus last: positive means the flip sits overhead.
  const side = g.flip_dist === null ? null : g.flip_dist > 0 ? "above" : "below";
  const flipSub =
    g.flip_dist_pct === null
      ? undefined
      : `${pct(g.flip_dist_pct, 1)}${g.flip_em !== null && side ? `, ${g.flip_em} EM ${side}` : ""}`;
  return (
    <div
      className="border-l-[3px] px-4 pt-3 pb-1"
      style={{ borderColor: "var(--flip)", background: tint("var(--flip)", 7) }}
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="font-serif text-[20px]" style={{ color: hue }}>
          {regime}
        </span>
        <span className="text-[12px] font-semibold text-ink-3">{g.label}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4">
        <Stat k="Flip" v={num(g.flip, g.dp)} sub={flipSub} />
        <Stat
          k="Expected move"
          v={g.em !== null ? `±${num(g.em, g.dp)}` : "—"}
          sub={g.em_basis && g.em_basis !== "GEXYGEN" ? g.em_basis : undefined}
        />
        <Stat k="Walls (call / put)" v={`${num(g.call_wall, g.dp)} / ${num(g.put_wall, g.dp)}`} />
        <Stat
          k="Spot"
          v={num(g.last, g.dp)}
          sub={side === "above" ? "below the flip" : side === "below" ? "above the flip" : undefined}
        />
      </div>
    </div>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div className="pb-3">
      <div className="text-[11px] text-ink-3">{k}</div>
      <div className="fig text-[15px] font-semibold text-ink">{v}</div>
      {sub && <div className="text-[11px] text-ink-3">{sub}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- catalysts */

function Catalysts({ f, b }: { f: BriefFacts; b: BriefBody }) {
  if (f.catalysts.length === 0 && !b.catalysts_intro) return null;
  const notes = new Map(b.catalyst_notes.map((n) => [n.id, n.note]));
  return (
    <Section title="Catalysts">
      {b.catalysts_intro && <P muted>{b.catalysts_intro}</P>}
      {f.catalysts.length > 0 && (
        <table className="w-full border-collapse border-t border-ring/60">
          <tbody>
            {f.catalysts.map((c) => {
              const note = notes.get(c.id);
              const detail = [
                c.actual && `actual ${c.actual}`,
                c.consensus && `${c.kind === "earnings" ? "EPS est." : "consensus"} ${c.consensus}`,
                c.previous && `prior ${c.previous}`,
                c.note,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <tr key={c.id} className="border-b border-ring/60 align-top">
                  <td
                    className={cn(
                      "fig w-[136px] py-2 pr-3 text-[11.5px] font-semibold whitespace-nowrap",
                      c.released ? "text-ink-3" : "text-ink",
                    )}
                  >
                    {c.when}
                  </td>
                  <td className="py-2">
                    <div className={cn("text-[13px] leading-snug", c.released ? "text-ink-2" : "text-ink")}>
                      {c.title}
                      {c.country && c.kind === "data" && (
                        <span className="ml-1.5 text-[11px] text-ink-3">{c.country}</span>
                      )}
                      {c.released && c.kind !== "fed" && <Chip>Released</Chip>}
                      {c.high && <Chip hue="var(--flip)">High impact</Chip>}
                    </div>
                    {detail && (
                      <div className="mt-0.5 text-[11.5px] leading-snug text-ink-3">
                        {detail.charAt(0).toUpperCase() + detail.slice(1)}
                      </div>
                    )}
                    {note && <div className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{note}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

/* ---------------------------------------------------------------- the read */

function Read({ r, call, live }: { r: BriefRead; call?: BriefCall; live?: boolean }) {
  const ink = biasInk(call?.open_bias);
  return (
    <div className="mb-8 last:mb-0">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-serif text-[21px] text-ink">{BOOK_NAME[r.book]}</span>
        {call && (
          <Chip hue={ink}>
            {biasLabel(call.open_bias)} {live ? "from here" : "at the open"}
          </Chip>
        )}
      </div>

      {r.regime && <Label>Regime: {r.regime}</Label>}
      {r.chain.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-x-1.5 gap-y-1.5 text-[12px]">
          {r.chain.map((link, i) => (
            <span key={i} className="contents">
              {i > 0 && (
                <span aria-hidden className="text-ink-3">
                  →
                </span>
              )}
              <span className="border border-ring bg-surface-2 px-2 py-0.5 text-ink">{link}</span>
            </span>
          ))}
        </div>
      )}

      {r.at_open && (
        <>
          <Label>{live ? "Where we are" : "At the open"}</Label>
          <P>{r.at_open}</P>
        </>
      )}

      {r.wrong_if && (
        <div className="mb-4 border-l-[3px] bg-surface-2 px-3 py-2" style={{ borderColor: ink }}>
          <Label>Wrong if</Label>
          <div className="text-[13px] leading-snug text-ink">{r.wrong_if}</div>
        </div>
      )}

      <Label>Rest of day</Label>
      {call?.rest_of_day && (
        <div className="mb-1.5">
          <Chip hue={biasInk(call.rest_of_day_bias)} className="ml-0">
            {call.rest_of_day}
          </Chip>
        </div>
      )}
      {r.rest_of_day && <P>{r.rest_of_day}</P>}

      {r.flips.length > 0 && (
        <>
          <Label>What flips it</Label>
          <ul className="mb-4 space-y-1">
            {r.flips.map((x, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink">
                <span aria-hidden className="text-ink-3">
                  ↺
                </span>
                {x}
              </li>
            ))}
          </ul>
        </>
      )}

      {r.drivers.length > 0 && (
        <>
          <Label>Drivers</Label>
          <ul className="border-t border-ring/60">
            {r.drivers.map((d, i) => (
              <li key={i} className="flex gap-2.5 border-b border-ring/60 py-1.5 text-[12.5px] leading-snug">
                <span
                  className="mt-[6px] h-[7px] w-[7px] shrink-0 rounded-full"
                  style={{ background: TONE_HUE[d.tone] }}
                  title={d.tone}
                />
                <span>
                  <strong className="font-semibold text-ink">{d.label}</strong>{" "}
                  <span className="text-ink-2">{d.text}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
            {(Object.keys(TONE_HUE) as Tone[]).map((t) => (
              <span key={t} className="inline-flex items-center gap-1">
                <span className="h-[7px] w-[7px] rounded-full" style={{ background: TONE_HUE[t] }} />
                {t}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- rotation */

function Rotation({ f, b }: { f: BriefFacts; b: BriefBody }) {
  const { ratios, megacaps, megacap_index, index_pct } = f.rotation;
  if (ratios.length === 0 && megacaps.length === 0) return null;
  const reads = new Map(b.ratio_reads.map((r) => [r.id, r.read]));
  return (
    <Section title="Rotation">
      {b.rotation_read && <P>{b.rotation_read}</P>}
      {ratios.length > 0 && (
        <table className="mb-4 w-full border-collapse border-t border-ring/60">
          <tbody>
            {ratios.map((r) => (
              <tr key={r.id} className="border-b border-ring/60 align-top">
                <td className="fig w-[104px] py-1.5 pr-2 text-[12px] font-semibold whitespace-nowrap text-ink">
                  {r.id}
                </td>
                <td className="fig w-[96px] py-1.5 pr-3 text-right text-[12px] whitespace-nowrap text-ink">
                  {num(r.level, r.level < 10 ? 3 : 2)} <span className={r.dir}>{ARROW[r.dir]}</span>
                </td>
                <td className="py-1.5 text-[12.5px] leading-snug text-ink-2">
                  {reads.get(r.id) ??
                    (r.chg_5d !== null && (
                      <span className="text-ink-3">{pct(r.chg_5d)} over 5 sessions</span>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {megacaps.length > 0 && (
        <div className="mb-3">
          <Label>
            Megacaps
            {megacap_index && index_pct !== null ? ` (${megacap_index} ${pct(index_pct, 1)})` : ""}
          </Label>
          <div className="flex flex-wrap gap-1.5">
            {megacaps.map((m) => {
              const hue = m.pct === null ? "var(--ink-3)" : m.pct >= 0 ? "var(--call)" : "var(--put)";
              return (
                <span
                  key={m.symbol}
                  className="fig rounded-[3px] px-1.5 py-0.5 text-[11px] text-ink"
                  style={{ background: tint(hue, 22) }}
                >
                  {m.symbol} {pct(m.pct, 1)}
                </span>
              );
            })}
          </div>
        </div>
      )}
      {b.rotation_notes.map((n, i) => (
        <P key={i} muted>
          {n}
        </P>
      ))}
    </Section>
  );
}

/* ---------------------------------------------------------------- headlines */

function Headlines({ f, b }: { f: BriefFacts; b: BriefBody }) {
  const byId = new Map(f.headlines.map((h) => [h.id, h]));
  const picks = b.headlines.filter((p) => byId.has(p.id));
  if (picks.length === 0) return null;
  return (
    <Section title="Headlines that move price">
      <ul className="border-t border-ring/60">
        {picks.map((p) => {
          const h = byId.get(p.id)!;
          return (
            <li key={p.id} className="border-b border-ring/60 py-2.5">
              <div className="flex flex-wrap items-center text-[11px] text-ink-3">
                <span>{[h.publisher, h.time_et].filter(Boolean).join(", ")}</span>
                {p.books.length > 0 && <Chip>{p.books.map((bk) => BOOK_NAME[bk]).join(" + ")}</Chip>}
              </div>
              {h.url ? (
                <a
                  href={h.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-0.5 block text-[13.5px] leading-snug text-ink hover:underline"
                >
                  {h.title}
                </a>
              ) : (
                <div className="mt-0.5 text-[13.5px] leading-snug text-ink">{h.title}</div>
              )}
              {p.note && <div className="mt-0.5 text-[12px] leading-snug text-ink-3">{p.note}</div>}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* ---------------------------------------------------------------- type */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 border-t border-ring/60 pt-5">
      <h3 className="mb-3 font-serif text-[19px] font-normal text-ink">{title}</h3>
      {children}
    </section>
  );
}

function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mb-1 text-[12px] text-ink-3", className)}>{children}</div>;
}

function P({
  children,
  muted,
  className,
}: {
  children: React.ReactNode;
  muted?: boolean;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mb-3 text-[13.5px] leading-[1.6]",
        MEASURE,
        muted ? "text-ink-3" : "text-ink-2",
        className,
      )}
    >
      {children}
    </p>
  );
}

function Chip({
  hue,
  className,
  children,
}: {
  hue?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const h = hue ?? "var(--ink-2)";
  return (
    <span
      className={cn(
        "ml-1.5 inline-block rounded-[3px] px-1.5 py-px align-[1px] text-[10.5px] leading-[16px] font-semibold",
        className,
      )}
      style={{ color: h, background: tint(h, 16) }}
    >
      {children}
    </span>
  );
}
