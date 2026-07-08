import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { jwtVerify } from "jose";

const SECRET = new TextEncoder().encode(process.env.BUILDER_SESSION_SECRET || "dev-secret-change-me");

export async function GET() {
  const c = (await cookies()).get("zb_session")?.value;
  if (!c) return NextResponse.json({ error: "no_session" }, { status: 401 });
  try {
    const { payload } = await jwtVerify(c, SECRET);
    return NextResponse.json({ email: payload.email, name: payload.name, tier: payload.tier });
  } catch {
    return NextResponse.json({ error: "invalid_session" }, { status: 401 });
  }
}
