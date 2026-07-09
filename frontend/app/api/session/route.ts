import { NextResponse } from "next/server";
import { SignJWT } from "jose";

const SECRET = new TextEncoder().encode(process.env.BUILDER_SESSION_SECRET || "dev-secret-change-me");
const NYQUEST = (process.env.NYQUEST_API || "https://api.nyquest.ai").replace(/\/$/, "");
const PRO_TIERS = (process.env.PRO_TIERS || "pro,teams").split(",").map((t) => t.trim().toLowerCase());
const COOKIE = "zb_session";
const KEY_NAME = "ZoidLab Builder";

// Mint a durable per-user relay key so the user's own Nyquest wallet is billed.
// Revokes prior ZoidLab keys first so repeat logins don't pile up keys.
async function mintRelayKey(token: string): Promise<string> {
  try {
    const listRes = await fetch(`${NYQUEST}/user/api-keys`, { headers: { Authorization: `Bearer ${token}` } });
    if (listRes.ok) {
      const raw = await listRes.json();
      const keys = Array.isArray(raw) ? raw : raw.keys || raw.data || [];
      for (const k of keys) {
        if (String(k.name || "").startsWith(KEY_NAME)) {
          await fetch(`${NYQUEST}/user/api-keys/${k.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
        }
      }
    }
  } catch {
    /* best-effort revoke */
  }
  const mint = await fetch(`${NYQUEST}/user/api-keys`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: KEY_NAME }),
  });
  if (!mint.ok) return "";
  const j = await mint.json();
  return j.key || "";
}

// POST { token } — verify a Nyquest token, gate on Pro/Teams, mint the user's
// own relay key, and store it in the (signed, httpOnly) session.
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

  const relayKey = await mintRelayKey(token);
  if (!relayKey) return NextResponse.json({ error: "key_mint_failed" }, { status: 502 });

  const jwt = await new SignJWT({ sub: user.id, email: user.email, name: user.name, tier, rk: relayKey })
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

// DELETE — log out (does not revoke the relay key; the user keeps it).
export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}
