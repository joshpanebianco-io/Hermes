/**
 * Which of a stock chart's bars stand in extended hours, and in which half of them.
 *
 * WHY THE TWO HALVES ARE TOLD APART (owner, 2026-11-12, with a screenshot of the chart
 * they trade from: "make the extended hours and pre market shaded colors the same as
 * this for josh colors"). Their chart shades the after-hours blue and the pre-market
 * sand. This chart has no bars overnight, so the evening's last bar and the morning's
 * first are neighbours: shaded as one run, as they used to be, the two could not be
 * two colours. A run now ends where the session changes as well as where it ends.
 *
 * Pure, and apart from the chart so it can be tested without a canvas.
 */

export type ExtKind = "pre" | "post";

export interface ShadeRun {
  /** The first and the last bar of the run, by index, both inside it. */
  from: number;
  to: number;
  kind: ExtKind;
}

/**
 * A bar's half of the extended hours, or null in the regular session.
 *
 * `span` is the collector's own word for the session the bar falls in (scan.py's
 * `sessions`), and it is the answer whenever there is one: it knows a half day's 13:00
 * close. A bar in no span is one the collector has not placed: an overnight print, or
 * the live bar the stream opened since the last poll. That one goes by New York's
 * clock, `hm` as "HH:MM": before 09:30 belongs to the morning, from 16:00 to the
 * evening, and between them it is a regular bar.
 */
export function extKind(span: "pre" | "rth" | "post" | null | undefined, hm: string): ExtKind | null {
  if (span === "rth") return null;
  if (span === "pre" || span === "post") return span;
  // Intl writes midnight as "24:00" on some engines: that is the small hours, not the evening.
  if (hm < "09:30" || hm >= "24:00") return "pre";
  return hm >= "16:00" ? "post" : null;
}

/**
 * The runs to shade, one per extended session, and the bar each regular session opens
 * on after one (where the chart draws its 09:30 hairline).
 */
export function shadeRuns(kinds: ReadonlyArray<ExtKind | null>): { runs: ShadeRun[]; opens: number[] } {
  const runs: ShadeRun[] = [];
  const opens: number[] = [];
  let run: ShadeRun | null = null;
  for (let i = 0; i < kinds.length; i++) {
    const k = kinds[i];
    if (k === null) {
      if (run) opens.push(i);
      run = null;
    } else if (run && run.kind === k) {
      run.to = i;
    } else {
      run = { from: i, to: i, kind: k };
      runs.push(run);
    }
  }
  return { runs, opens };
}
