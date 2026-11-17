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
 * THE SAME ANSWER HOWEVER OFTEN IT IS ASKED (2026-11-16). This runs inside a state
 * updater, and React's strict mode (on under `next dev`) runs an updater twice and
 * keeps the second answer. It used to remember "the last poll's serialisations" in
 * a map the caller owned and wrote to it as it compared: the first run wrote the new
 * poll in, so the second found every block equal to itself and handed the OLD ones
 * back. The poll landed (the status rail's time moved) and nothing on the page did:
 * the Futures Bias card, the prices and every panel fed by the poll stood at the
 * page's first paint. It showed whenever another update reached the shell just
 * before the poll's reply, which the market context's own 20-second poll did.
 *
 * So it now compares the new block with the block ON SCREEN (`prev`), and keeps
 * nothing between calls but each block's own serialisation, stored against the
 * block itself: asked twice, it reads the same two strings and says the same thing.
 * A payload is still stringified once, however often it is compared.
 */
export function shareUnchanged<T extends object>(prev: T, next: T): T {
  const out = { ...next } as Record<string, unknown>;
  const was = prev as Record<string, unknown>;
  for (const [k, v] of Object.entries(next)) {
    if (!(k in was) || was[k] === v) continue;
    const s = serial(v);
    if (s !== null && s === serial(was[k])) out[k] = was[k];
  }
  return out as T;
}

/** A block's serialisation, kept with the block and dropped with it. */
const SERIAL = new WeakMap<object, string | null>();

function serial(v: unknown): string | null {
  const held = typeof v === "object" && v !== null;
  if (held && SERIAL.has(v)) return SERIAL.get(v) ?? null;
  let s: string | null;
  try {
    s = JSON.stringify(v) ?? "";
  } catch {
    s = null;
  }
  if (held) SERIAL.set(v, s);
  return s;
}
