import type { NoteJob } from "@/types/terminal";

/**
 * Follow a generation to its end.
 *
 * WHY THE PAGE POLLS. A report or a game plan takes one to five minutes on a
 * free model, and the POST used to be held open for the whole of it — so the
 * browser's fetch, the proxy's 290s and the collector's own budget all had to
 * outlast the model, and whichever gave up first turned a note that was still
 * being written into "the collector did not answer in time" (2026-10-27: a
 * 332s brief, stored a minute after the page had reported it failed). Now the
 * POST answers at once with the job the collector started, and this asks
 * after it every few seconds until it is no longer running. No request is
 * ever as long as the generation, and a reload in the middle finds the job in
 * the feed and picks it back up (useReport, useStockPlan).
 */

/** What every feed a job rides in on carries: the job, and the proxy's offline block. */
export interface JobFeed {
  job?: NoteJob | null;
  offline?: { reason: string; api: string };
}

/** How often to ask. Local and cheap; the clock on screen ticks by the second regardless. */
export const POLL_MS = 2500;

/**
 * Unanswered polls in a row before the page stops asking — about twenty
 * seconds of a dead collector or a dead dev server. One miss is a hiccup and
 * is not surfaced; the job is still running upstream either way, and the
 * next poll usually finds it.
 */
export const MAX_MISSES = 8;

/** The reason landed when the page's own server could not be reached at all. */
export const NO_SERVER = "the page could not reach its own server";

/**
 * Poll `url` until the job it describes is no longer running.
 *
 * Resolves with the feed that settled it — the note as `latest`, which is
 * what the POST used to answer with once the model was done, or the failed
 * envelope when the collector lost the job — or with the proxy's offline feed
 * once MAX_MISSES polls in a row have come back offline. Resolves null when
 * `alive()` says the caller has moved on, or when the page's own server could
 * not be reached MAX_MISSES times.
 */
export async function followJob<F extends JobFeed>(url: string, alive: () => boolean): Promise<F | null> {
  let misses = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, POLL_MS));
    if (!alive()) return null;
    const next = await fetch(url, { cache: "no-store" })
      .then((r) => r.json() as Promise<F>)
      .catch((): null => null);
    if (!alive()) return null;
    if (next === null || next.offline) {
      if (++misses >= MAX_MISSES) return next;
      continue;
    }
    misses = 0;
    if (next.job?.state === "running") continue;
    return next;
  }
}
