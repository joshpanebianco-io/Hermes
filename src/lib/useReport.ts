"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReportAsset, ReportFeed, ReportSession } from "@/types/terminal";
import { NO_SERVER, followJob } from "./jobs";
import { oneOf, usePersisted } from "./usePersisted";

/**
 * The report tab's state, owned above the tab switch.
 *
 * WHY IT IS NOT IN THE PANEL. The panel unmounts when you leave the tab, and a
 * generation takes two to three minutes on a free model — long enough that
 * switching to the terminal while it runs is the normal thing to do. With the
 * state inside the panel that abandoned the request: the fetch was cancelled,
 * the working state died with the component, and returning to the tab showed
 * the previous report as though nothing had been asked for. Hoisting it here
 * means the promise is owned by something that stays mounted for the life of
 * the page.
 *
 * `seq` GUARDS THE LANDING, not the request. An abandoned generation is still
 * spending tokens upstream and its answer is still worth having, so nothing is
 * aborted — but if two are somehow in flight, only the newest is allowed to
 * write. The same rule the terminal poll uses. Opening a past call has its own
 * guard (`openSeq`): two quick clicks used to let the slower answer land last,
 * showing report A under B's highlight.
 *
 * AN OFFLINE ANSWER IS NEWS, NOT A FEED (review, 2026-10-13). The proxy turns
 * a dead or slow collector into a body with `config.enabled: false` and an
 * empty history, and storing that whole meant the panel announced "no key is
 * set" and Past calls emptied to "Nothing yet" — for a generation that had
 * merely timed out. `land` keeps the report and the history the page already
 * holds and attaches the reason, which the panel prints.
 *
 * THE GENERATION IS A JOB, NOT A REQUEST (2026-10-27). The POST answers at
 * once with the job the collector started, and `follow` asks after it every
 * few seconds until it is done (src/lib/jobs.ts says why). The feed carries
 * the running job, so a page that loads or refreshes mid-generation resumes
 * following it, clock and all, rather than showing the old note as though
 * nothing had been asked for.
 */

/** Fold an answer into what the page holds; an offline answer only adds its reason. */
function land(prev: ReportFeed | null, next: ReportFeed): ReportFeed {
  if (!next.offline || !prev) return next;
  return { ...prev, offline: next.offline };
}

export interface ReportController {
  pick: ReportSession | "auto";
  setPick: (v: ReportSession | "auto") => void;
  book: ReportAsset;
  setBook: (v: ReportAsset) => void;
  feed: ReportFeed | null;
  busy: boolean;
  /** The stored report being viewed, when it is not simply the latest. */
  viewing: string | null;
  generate: () => void;
  open: (id: string) => void;
  /** Delete one stored report. Permanent — the panel asks first. */
  discard: (id: string) => void;
  /** Delete several in one trip. Permanent — the list asks first and says how many. */
  discardMany: (ids: string[]) => void;
  /** Delete every stored report the collector keeps, not only the rows listed. */
  discardAll: () => void;
  /** Ask the collector again — the offline state's way back. */
  retry: () => void;
  /**
   * When the running generation was asked for, as an epoch ms. Owned here and
   * not in the panel's loader for the same reason `busy` is: the panel
   * unmounts on a tab switch, and a clock that restarted from zero on the way
   * back would be lying about how long you have waited.
   */
  startedAt: number | null;
}

export function useReport(initial: ReportFeed | null): ReportController {
  const [feed, setFeed] = useState<ReportFeed | null>(initial);
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [pick, setPick] = usePersisted<ReportSession | "auto">(
    "report.session",
    "auto",
    oneOf("auto", "asia", "london", "ny"),
  );
  const [book, setBook] = usePersisted<ReportAsset>(
    "report.asset",
    "all",
    oneOf("all", "NQ", "ES", "GC"),
  );
  const seq = useRef(0);
  const openSeq = useRef(0);
  /** The job being followed, so a feed that carries it is not followed twice. */
  const following = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/report", { cache: "no-store" });
      const next = (await r.json()) as ReportFeed;
      setFeed((prev) => land(prev, next));
    } catch {
      /* the route handler returns an offline body rather than throwing */
    }
  }, []);

  useEffect(() => {
    if (!initial) void refresh();
  }, [initial, refresh]);

  /**
   * Follow a job to its end and land what it wrote. `mine` is the generation
   * number taken when the job was asked for; a newer press, or a reload that
   * found a different job, makes this one stop quietly.
   */
  const follow = useCallback((id: string, mine: number) => {
    following.current = id;
    void (async () => {
      const alive = () => mine === seq.current;
      const next = await followJob<ReportFeed>(`/api/report/job/${encodeURIComponent(id)}`, alive);
      if (!alive()) return;
      following.current = null;
      if (next) {
        // Done, lost, or the proxy offline for too long: `land` keeps the
        // page's report under an offline answer and takes the note otherwise.
        setFeed((prev) => ({ ...land(prev, next), job: null }));
        if (!next.offline) {
          // The new report is what is on screen now: drop a past call that
          // was opened while it was being written, and any open still in
          // flight, or the highlight and the page would disagree.
          setViewing(null);
          openSeq.current += 1;
        }
      } else {
        setFeed((prev) => prev && { ...prev, job: null, offline: { reason: NO_SERVER, api: "" } });
      }
      setBusy(false);
      setStartedAt(null);
    })();
  }, []);

  const generate = useCallback(() => {
    setBusy(true);
    setStartedAt(Date.now());
    setViewing(null);
    const mine = ++seq.current;
    void (async () => {
      const next = await fetch(`/api/report?session=${pick}&asset=${book}`, {
        method: "POST",
        cache: "no-store",
      })
        .then((r) => r.json() as Promise<ReportFeed>)
        .catch((): null => null);
      if (mine !== seq.current) return;
      if (next?.job) {
        // Started — or joined, if one was already being written. The feed it
        // rode in on is the old note plus the job; the note comes by following.
        follow(next.job.id, mine);
        setFeed((prev) => land(prev, next));
        return;
      }
      setFeed((prev) => (next ? land(prev, next) : prev && { ...prev, offline: { reason: NO_SERVER, api: "" } }));
      setBusy(false);
      setStartedAt(null);
    })();
  }, [pick, book, follow]);

  /*
   * A page that loaded, refreshed or was retried while a report was being
   * written: the feed carries the job, so pick it up — busy, with the clock
   * from when it was actually asked for — instead of showing the old note as
   * though nothing had been asked for.
   */
  const job = feed?.job;
  useEffect(() => {
    if (!job || job.state !== "running" || following.current === job.id) return;
    setBusy(true);
    setStartedAt(Date.parse(job.started_utc ?? "") || Date.now());
    setViewing(null);
    follow(job.id, ++seq.current);
  }, [job, follow]);

  const open = useCallback((id: string) => {
    setViewing(id);
    const mine = ++openSeq.current;
    void (async () => {
      try {
        const r = await fetch(`/api/report/${encodeURIComponent(id)}`, {
          cache: "no-store",
        });
        const next = (await r.json()) as ReportFeed;
        if (mine !== openSeq.current) return;
        setFeed((f) => (next.offline ? land(f, next) : f ? { ...f, latest: next.latest, offline: undefined } : next));
      } catch {
        /* same */
      }
    })();
  }, []);

  /*
   * The DELETE hands back the refreshed list and latest in one response, so the
   * whole feed is replaced rather than spliced locally — the server is the only
   * thing that knows what "latest" is once the newest report is the one that
   * went.
   *
   * `viewing` is cleared when the report being READ is the one deleted, which
   * drops the panel back to whatever is now latest. Deleting some other row
   * leaves your place alone; re-pointing the reader because an unrelated line
   * item went would be the panel moving under you.
   */
  const discard = useCallback((id: string) => {
    void (async () => {
      try {
        const r = await fetch(`/api/report/${encodeURIComponent(id)}`, {
          method: "DELETE",
          cache: "no-store",
        });
        const next = (await r.json()) as ReportFeed;
        if (next.offline) {
          setFeed((prev) => land(prev, next));
          return;
        }
        setViewing((v) => (v === id ? null : v));
        setFeed(next);
      } catch {
        /* same */
      }
    })();
  }, []);


  /*
   * SEVERAL AT ONCE, OR ALL — one DELETE on the collection, not one per row.
   * A loop of single deletes lands N feeds in whatever order the network
   * chooses and the list flickers through states nobody asked for; the
   * collector does the lot and hands back one list. `viewing` clears when
   * the report being read is among those gone — with "all" it always is.
   */
  const discardSet = useCallback((qs: string, gone: (id: string) => boolean) => {
    void (async () => {
      try {
        const r = await fetch(`/api/report?${qs}`, { method: "DELETE", cache: "no-store" });
        const next = (await r.json()) as ReportFeed;
        if (next.offline) {
          setFeed((prev) => land(prev, next));
          return;
        }
        setViewing((v) => (v !== null && gone(v) ? null : v));
        setFeed(next);
      } catch {
        /* same */
      }
    })();
  }, []);
  const discardMany = useCallback(
    (ids: string[]) =>
      discardSet(ids.map((id) => `ids=${encodeURIComponent(id)}`).join("&"), (v) => ids.includes(v)),
    [discardSet],
  );
  const discardAll = useCallback(() => discardSet("all=1", () => true), [discardSet]);

  const retry = useCallback(() => void refresh(), [refresh]);

  return {
    pick, setPick, book, setBook, feed, busy, viewing, generate, open,
    discard, discardMany, discardAll, retry, startedAt,
  };
}
