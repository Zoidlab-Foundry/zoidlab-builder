import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { jwtVerify } from "jose";

// Access gate: requires a valid ZoidLab session cookie, minted only after a
// Nyquest Pro/Teams user is verified via /api/session. Public paths below are
// the ones needed to establish that session.
const SECRET = new TextEncoder().encode(process.env.BUILDER_SESSION_SECRET || "dev-secret-change-me");
// /api/health is an OPEN readiness endpoint (Foundry control-plane health checks) —
// public across the suite, consistent with the other packages and the platform blueprint.
const PUBLIC_PREFIXES = ["/enter", "/gate", "/api/session", "/api/handoff", "/hooks", "/api/health"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookie = req.cookies.get("zb_session")?.value;
  if (cookie) {
    try {
      await jwtVerify(cookie, SECRET);
      return NextResponse.next();
    } catch {
      /* invalid/expired — fall through to gate */
    }
  }
  const url = req.nextUrl.clone();
  url.pathname = "/gate";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logo.svg|logo-hero.png).*)"],
};
