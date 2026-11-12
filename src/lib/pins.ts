/**
 * A NAME TAKEN OFF THE PINNED LIST CAN BE PUT BACK, AND NEVER LEAVES IN SILENCE.
 *
 * WHY (owner, 2026-11-11: "also nvidia is not anywhere? i cant see it anywhere", for the
 * third time in two days). A row's star unpins on one click. On the morning of
 * 10 Nov NVDA, pinned since the list was written, came off that way between 09:40 and
 * 10:35 ET: the row went, nothing on screen said so, and the list was a name short
 * until it was traced the next evening. The same morning a browser check pinned GEV
 * by clicking the wrong button in a row, and nothing said that either.
 *
 * So an unpin now does two things. It raises a notice with an Undo (shell/PinUndo),
 * which puts the name back where it sat. And it is remembered here for a week, in
 * this browser, so the Watchlist editor can say "unpinned recently: NVDA, Tue 10:12"
 * to a reader who was looking at another screen when the notice was up.
 *
 * The first half of this file is pure, for the tests; the second touches the window.
 */

/** A name taken off the pinned list: where it sat, and when (epoch ms). */
export interface Unpinned {
  sym: string;
  index: number;
  at: number;
}

/** How many are remembered, and for how long. */
export const KEEP = 8;
export const KEEP_MS = 7 * 24 * 3600 * 1000;

const isUnpinned = (v: unknown): v is Unpinned => {
  const u = v as Partial<Unpinned> | null;
  return typeof u === "object" && u !== null && typeof u.sym === "string" && u.sym.length > 0 && Number.isInteger(u.index) && typeof u.at === "number";
};

/** What storage holds, as a list: newest first, nothing older than a week, nothing malformed. Pure. */
export function readUnpins(raw: string | null, now: number): Unpinned[] {
  if (!raw) return [];
  try {
    const got: unknown = JSON.parse(raw);
    if (!Array.isArray(got)) return [];
    return got
      .filter(isUnpinned)
      .filter((u) => now - u.at < KEEP_MS && u.at <= now + 60_000)
      .sort((a, b) => b.at - a.at)
      .slice(0, KEEP);
  } catch {
    return [];
  }
}

/** The list with one more unpin: newest first, a name once, no more than KEEP. Pure. */
export function withUnpin(list: readonly Unpinned[], u: Unpinned): Unpinned[] {
  return [u, ...list.filter((x) => x.sym !== u.sym)].slice(0, KEEP);
}

/** The list without a name that has been pinned again. Pure. */
export function withoutUnpin(list: readonly Unpinned[], sym: string): Unpinned[] {
  return list.filter((x) => x.sym !== sym);
}

/**
 * The pinned list with a name back in it: at the place it left, or at the end when
 * the list is shorter than it was. A name already on the list is left where it is. Pure.
 */
export function putBack(symbols: readonly string[], u: Pick<Unpinned, "sym" | "index">): string[] {
  if (symbols.includes(u.sym)) return [...symbols];
  const at = Math.max(0, Math.min(u.index, symbols.length));
  return [...symbols.slice(0, at), u.sym, ...symbols.slice(at)];
}

/* -------------------------------------------------------------------------- */
/* The window's half                                                           */
/* -------------------------------------------------------------------------- */

const KEY = "nt.unpinned";

/** Raised with the `Unpinned` as its detail when a star takes a name off the list. */
export const UNPINNED_EVENT = "hermes:unpinned";
/** Raised after the pinned list changes by any hand, so a page can read it again. */
export const PINS_EVENT = "hermes:pins";

/** The names unpinned in this browser over the last week, newest first. */
export function recentUnpins(): Unpinned[] {
  try {
    return readUnpins(window.localStorage.getItem(KEY), Date.now());
  } catch {
    return [];
  }
}

function store(list: Unpinned[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* the notice still shows; only the week's memory is lost */
  }
}

/** A star took this name off the list: remember it, and say so. */
export function noteUnpinned(u: Unpinned): void {
  store(withUnpin(recentUnpins(), u));
  window.dispatchEvent(new CustomEvent<Unpinned>(UNPINNED_EVENT, { detail: u }));
  window.dispatchEvent(new Event(PINS_EVENT));
}

/** This name is pinned again: it is no longer one to offer back. */
export function notePinned(sym: string): void {
  const was = recentUnpins();
  if (was.some((x) => x.sym === sym)) store(withoutUnpin(was, sym));
  window.dispatchEvent(new Event(PINS_EVENT));
}

/** Put an unpinned name back where it was. Null on success, or why not. */
export async function restorePin(u: Pick<Unpinned, "sym" | "index">): Promise<string | null> {
  try {
    const got = (await (await fetch("/api/scanner/watchlist", { cache: "no-store" })).json()) as { symbols?: string[]; error?: string };
    if (!got.symbols) return got.error ?? "could not read the list";
    if (!got.symbols.includes(u.sym)) {
      const r = await fetch("/api/scanner/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: putBack(got.symbols, u) }),
      });
      const after = (await r.json()) as { error?: string; rejected?: string[] };
      if (!r.ok || after.error) return after.error ?? `HTTP ${r.status}`;
      if (after.rejected?.includes(u.sym)) return `${u.sym} was refused: the list is full`;
    }
    notePinned(u.sym);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : "request failed";
  }
}
