import { NextResponse } from "next/server";
import { SignJWT } from "jose";

const SECRET = new TextEncoder().encode(process.env.BUILDER_SESSION_SECRET || "dev-secret-change-me");
const NYQUEST = (process.env.NYQUEST_API || "https://api.nyquest.ai").replace(/\/$/, "");
const PRO_TIERS = (process.env.PRO_TIERS || "pro,teams").split(",").map((t) => t.trim().toLowerCase());
const COOKIE = "zb_session";

// POST { token } — verify a Nyquest token, gate on Pro/Teams, mint a session.
export async function POST(req: Request) {
  let token = "";
  try {
    token = (await req.json()).token || "";
  } catch {
    /* no body */
  }
  if (!token) return NextResponse.json({ error: "missing token" }, { status: 400 });

  let user: any;
  try {
    const r = await fetch(`${NYQUEST}/user/me`, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) return NextResponse.json({ error: "invalid_nyquest_session" }, { status: 401 });
    user = await r.json();
  } catch {
    return NextResponse.json({ error: "nyquest_unreachable" }, { status: 502 });
  }

  const tier = String(user?.tier || "").toLowerCase();
  if (!PRO_TIERS.includes(tier)) {
    return NextResponse.json({ error: "pro_required", tier }, { status: 403 });
  }

  const jwt = await new SignJWT({ sub: user.id, email: user.email, name: user.name, tier })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("30d")
    .sign(SECRET);

  const res = NextResponse.json({ ok: true, user: { email: user.email, name: user.name, tier } });
  res.cookies.set(COOKIE, jwt, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}

// DELETE — log out.
export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}
