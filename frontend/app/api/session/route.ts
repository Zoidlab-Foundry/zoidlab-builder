import { NextResponse } from "next/server";
import { verifyAndMint, issueSession, takeCode } from "../../../lib/handoff";

const COOKIE = "zb_session";
// Shared across every *.zoidlab.ai app so one sign-in covers the whole suite.
const COOKIE_DOMAIN = process.env.SESSION_COOKIE_DOMAIN || ".zoidlab.ai";

// POST { code } (Phase C handoff) or { token } (direct) — mint a session.
export async function POST(req: Request) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    /* no body */
  }

  let claims;
  if (body.code) {
    claims = takeCode(String(body.code));
    if (!claims) return NextResponse.json({ error: "invalid_or_expired_code" }, { status: 401 });
  } else if (body.token) {
    const res = await verifyAndMint(String(body.token));
    if (!res.claims) return NextResponse.json({ error: res.error }, { status: res.status });
    claims = res.claims;
  } else {
    return NextResponse.json({ error: "missing token" }, { status: 400 });
  }

  const jwt = await issueSession(claims);
  const res = NextResponse.json({ ok: true, user: { email: claims.email, name: claims.name, tier: claims.tier } });
  res.cookies.set(COOKIE, jwt, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    domain: COOKIE_DOMAIN,
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}

// DELETE — log out.
export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, "", { path: "/", domain: COOKIE_DOMAIN, maxAge: 0 });
  return res;
}
