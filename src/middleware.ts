import { NextResponse, type NextRequest } from "next/server";

/**
 * WRITES COME FROM THIS PAGE OR NOWHERE.
 *
 * The routes behind /api spend model calls (a brief, a plan, a question to
 * Hermes), delete history and replace the watchlist. CORS keeps another
 * website from READING their answers, not from SENDING the request: a form
 * post or a no-cors fetch from any page open in the same browser arrives here
 * like the terminal's own. A browser always says which page a write came
 * from, so one that names a different origin is refused before a route runs
 * (audit, 2026-10-14). Reads pass untouched — they change nothing.
 */
export function middleware(req: NextRequest) {
  if (req.method === "GET" || req.method === "HEAD" || req.method === "OPTIONS") return;
  const origin = req.headers.get("origin");
  if (origin && origin !== req.nextUrl.origin && !sameDesk(origin, req.nextUrl.port)) {
    return new NextResponse("cross-origin write refused", { status: 403 });
  }
}

/** localhost and 127.0.0.1 are the same desk — the page may be opened as either. */
function sameDesk(origin: string, port: string): boolean {
  try {
    const u = new URL(origin);
    return (u.hostname === "localhost" || u.hostname === "127.0.0.1") && u.port === port;
  } catch {
    return false;
  }
}

export const config = { matcher: "/api/:path*" };
