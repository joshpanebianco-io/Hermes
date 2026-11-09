/** The named query parameters of a request, re-encoded; everything else stays behind. */
export function wideParams(url: string, names: readonly string[]): string {
  const from = new URL(url).searchParams;
  const out = new URLSearchParams();
  for (const n of names) {
    const v = from.get(n);
    if (v !== null && v !== "") out.set(n, v);
  }
  return out.toString();
}
