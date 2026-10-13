/**
 * Keep the previous payload's blocks wherever the new one says the same thing.
 *
 * WHY. Every poll is a fresh `JSON.parse`, so every block arrives as a new
 * object even when nothing in it moved — and a memoised panel compares props
 * by reference, so it re-rendered anyway. The calendar refreshes every ten
 * minutes, the curve every thirty, the Fed diary hourly; re-rendering them
 * every twenty seconds was work with nothing to show for it. Comparing each
 * top-level block's serialisation costs a few milliseconds per poll and lets
 * the panels whose data did not change skip the render entirely.
 *
 * `seen` holds the previous serialisations so each poll stringifies the new
 * payload once, not both.
 */
export function shareUnchanged<T extends object>(prev: T, next: T, seen: Map<string, string>): T {
  const out = { ...next } as Record<string, unknown>;
  const was = prev as Record<string, unknown>;
  for (const [k, v] of Object.entries(next)) {
    const s = serial(v);
    if (s === null) continue;
    // The first poll after the server's render has nothing in `seen` yet.
    const before = seen.has(k) ? seen.get(k) : k in was ? serial(was[k]) : null;
    if (before === s && k in was) out[k] = was[k];
    seen.set(k, s);
  }
  return out as T;
}

function serial(v: unknown): string | null {
  try {
    return JSON.stringify(v) ?? "";
  } catch {
    return null;
  }
}
