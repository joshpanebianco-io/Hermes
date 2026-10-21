"use client";

import { useEffect, useState } from "react";
import { Module } from "@/components/ui/Module";
import { cn } from "@/lib/cn";

/**
 * The list of stored notes beside a report or a plan — open one, delete one,
 * or select several and delete those, or every one.
 *
 * ONE LIST FOR BOTH TABS. Past calls and Past plans were the same eighty lines
 * twice, down to the inline confirm, and the selection mode would have made
 * it a hundred and sixty. The row's content is the caller's (`row`); the
 * opening, the deleting and the asking are here.
 *
 * SELECTING IS A MODE, ENTERED ON PURPOSE (owner, 2026-10-21: "multi select
 * delete and delete all options"). "Select" in the module's head turns every
 * row into a checkbox and puts a bar under the list with the count, Select
 * all, Delete N and Delete all; Cancel, or Escape, leaves it with nothing
 * done. Outside the mode the rows open as they always did and the × on hover
 * deletes one. Checkboxes always on show would make a list that is read ten
 * times for every time it is pruned look like a form.
 *
 * EVERY DELETE ASKS FIRST, INLINE, AND SAYS HOW MANY — the single row's
 * question over the row, the bulk one in the bar. `window.confirm` would be a
 * modal over the thing being confirmed. There is no trash folder on the
 * collector (report.remove), so the question is the only undo.
 *
 * "DELETE ALL" IS EVERYTHING THE COLLECTOR KEEPS, not the rows on screen: the
 * list shows the newest twenty and the collector keeps forty, and an "all"
 * that left the older twenty behind would be a lie. The question says so.
 */

export interface PastItem {
  id: string;
  et_label: string;
}

export function PastList<T extends PastItem>({
  title,
  noun,
  items,
  skeleton,
  current,
  empty,
  onOpen,
  onDiscard,
  onDiscardMany,
  onDiscardAll,
  row,
}: {
  title: string;
  /** "report" or "plan" — the questions are written with it. */
  noun: string;
  /** Null while the feed has not answered yet. */
  items: T[] | null;
  /** What to draw while `items` is null. */
  skeleton?: React.ReactNode;
  /** The note on the page, highlighted. */
  current: string | null;
  empty: string;
  onOpen: (id: string) => void;
  onDiscard: (id: string) => void;
  onDiscardMany: (ids: string[]) => void;
  onDiscardAll: () => void;
  /** The row's content — phrasing content, it sits inside a <button>. */
  row: (item: T) => React.ReactNode;
}) {
  /** Which row is asking "Delete this one?" — one at a time. */
  const [confirming, setConfirming] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(() => new Set());
  /** The bar's question: the picked rows, or every stored note. */
  const [ask, setAsk] = useState<"picked" | "all" | null>(null);

  const total = items?.length ?? 0;
  const count = picked.size;

  // A row that went — a delete landed, a poll replaced the list — leaves the
  // selection, and an emptied list leaves the mode: a bar over nothing that
  // offers to delete nothing is a bar that should not be there.
  useEffect(() => {
    if (!items) return;
    const alive = new Set(items.map((i) => i.id));
    setPicked((p) => {
      const keep = new Set([...p].filter((id) => alive.has(id)));
      return keep.size === p.size ? p : keep;
    });
    if (items.length === 0) {
      setSelecting(false);
      setAsk(null);
    }
  }, [items]);

  const leave = () => {
    setSelecting(false);
    setPicked(new Set());
    setAsk(null);
  };
  const toggle = (id: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const plural = (n: number) => `${n} ${noun}${n === 1 ? "" : "s"}`;

  const bar =
    "hit rounded px-1.5 py-0.5 text-[10px] qt:rounded-[3px] qt:px-2 qt:text-[11.5px] disabled:cursor-default disabled:opacity-40";

  return (
    <Module
      title={title}
      large
      sub={`${total} kept`}
      className="xl:min-h-0 xl:flex-1"
      bodyClassName="px-0 py-0 xl:min-h-0 xl:overflow-y-auto"
      right={
        total > 0 && (
          <button
            type="button"
            onClick={() => (selecting ? leave() : setSelecting(true))}
            aria-pressed={selecting}
            title={selecting ? "Leave selecting with nothing deleted" : `Select ${noun}s to delete, or delete all of them`}
            className="fig hit rounded border border-ring px-2 py-px text-[9.5px] text-ink-3 uppercase hover:text-ink-2 qt:rounded-[3px] qt:border-ring-2 qt:font-sans qt:text-[11.5px] qt:font-semibold qt:tracking-normal qt:normal-case qt:hover:border-ink-4"
          >
            {selecting ? "Cancel" : "Select"}
          </button>
        )
      }
    >
      {items === null ? (
        (skeleton ?? null)
      ) : items.length === 0 ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">{empty}</p>
      ) : (
        <div
          className="flex min-h-full flex-col"
          onKeyDown={(e) => {
            if (e.key === "Escape" && selecting) {
              e.stopPropagation();
              leave();
            }
          }}
        >
          <ul>
            {items.map((h) => {
              const on = picked.has(h.id);
              return (
                <li key={h.id} className="group relative">
                  <button
                    type="button"
                    role={selecting ? "checkbox" : undefined}
                    aria-checked={selecting ? on : undefined}
                    onClick={() => (selecting ? toggle(h.id) : onOpen(h.id))}
                    className={cn(
                      "hit flex w-full items-start gap-2 py-1.5 pr-7 pl-3 text-left",
                      "qt:border-b qt:border-ring/60 qt:py-2.5",
                      !selecting && current === h.id && "bg-ink/[0.06] qt:bg-surface-2",
                      selecting && on && "bg-warn/[0.08]",
                    )}
                  >
                    {/* The box is drawn, not an <input>: a control inside a
                        button is invalid, and the button IS the checkbox
                        (role, aria-checked) — the glyph only shows its state. */}
                    {selecting && (
                      <span
                        aria-hidden
                        className={cn(
                          "mt-[3px] flex h-[12px] w-[12px] shrink-0 items-center justify-center rounded-[2px] border text-[9px] leading-none",
                          on ? "border-warn bg-warn text-surface" : "border-ring-2 text-transparent",
                        )}
                      >
                        ✓
                      </span>
                    )}
                    <span className="flex min-w-0 flex-1 flex-col items-start gap-0.5 qt:gap-1">{row(h)}</span>
                  </button>
                  {/*
                    * DELETE IS A SIBLING OF THE ROW BUTTON, NOT A CHILD OF IT.
                    * A button inside a button is invalid HTML and browsers
                    * resolve it by dropping one of them, so the row reserves
                    * `pr-7` and this sits in the gutter it leaves. Gone while
                    * selecting — the bar is the delete then.
                    */}
                  {!selecting &&
                    (confirming === h.id ? (
                      <div className="absolute inset-0 flex items-center gap-1.5 bg-surface-2 px-3">
                        <span className="mr-auto text-[10px] text-ink-3">Delete this {noun}?</span>
                        <button
                          type="button"
                          onClick={() => {
                            onDiscard(h.id);
                            setConfirming(null);
                          }}
                          className="hit rounded px-1.5 py-0.5 text-[10px] font-semibold text-warn"
                        >
                          Delete
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirming(null)}
                          className="hit rounded px-1.5 py-0.5 text-[10px] text-ink-3"
                        >
                          Keep
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirming(h.id)}
                        title={`Delete this ${noun}`}
                        aria-label={`Delete the ${noun} from ${h.et_label}`}
                        /*
                         * Revealed on hover, but focus-visible brings it back for
                         * the keyboard — an opacity-0 control that only a mouse
                         * can summon is one a keyboard can tab to and not see.
                         */
                        className="hit absolute top-1.5 right-1 rounded px-1 text-[12px] leading-none text-ink-4 opacity-0 group-hover:opacity-100 hover:text-warn focus-visible:opacity-100"
                      >
                        ×
                      </button>
                    ))}
                </li>
              );
            })}
          </ul>

          {/* ---- the bar: what is picked, and the two deletes ---- */}
          {selecting && (
            <div
              role="toolbar"
              aria-label={`Delete ${noun}s`}
              className="sticky bottom-0 mt-auto flex flex-wrap items-center gap-x-1.5 gap-y-1 border-t border-ring bg-surface-2 px-3 py-1.5 text-[10px] qt:text-[11.5px]"
            >
              {ask ? (
                <>
                  <span className="mr-auto text-ink-2">
                    {ask === "all"
                      ? `Delete every ${noun} the collector keeps? ${total} listed here.`
                      : `Delete ${plural(count)}?`}{" "}
                    Not recoverable.
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (ask === "all") onDiscardAll();
                      else onDiscardMany([...picked]);
                      leave();
                    }}
                    className={cn(bar, "font-semibold text-warn")}
                  >
                    Delete
                  </button>
                  <button type="button" onClick={() => setAsk(null)} className={cn(bar, "text-ink-3")}>
                    Keep
                  </button>
                </>
              ) : (
                <>
                  <span className="fig mr-auto text-ink-3">{count} selected</span>
                  <button
                    type="button"
                    onClick={() => setPicked(count === total ? new Set() : new Set(items.map((i) => i.id)))}
                    className={cn(bar, "text-ink-3 hover:text-ink-2")}
                  >
                    {count === total ? "Clear" : "Select all"}
                  </button>
                  <button
                    type="button"
                    disabled={count === 0}
                    onClick={() => setAsk("picked")}
                    className={cn(bar, "font-semibold text-warn")}
                  >
                    Delete{count > 0 ? ` ${count}` : ""}
                  </button>
                  <button type="button" onClick={() => setAsk("all")} className={cn(bar, "font-semibold text-warn")}>
                    Delete all
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </Module>
  );
}
