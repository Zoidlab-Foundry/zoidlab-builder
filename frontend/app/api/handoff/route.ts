import { NextResponse } from "next/server";
import { verifyAndMint, putCode } from "../../../lib/handoff";

// Cross-origin: the Nyquest app POSTs the user's token here and gets back a
// short-lived one-time code, so the token never enters a URL.
const ORIGIN = process.env.NYQUEST_APP_ORIGIN || "https://app.nyquest.ai";

function cors(res: NextResponse) {
  res.headers.set("Access-Control-Allow-Origin", ORIGIN);
  res.headers.set("Vary", "Origin");
  return res;
}

export async function OPTIONS() {
  const res = new NextResponse(null, { status: 204 });
  res.headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.headers.set("Access-Control-Allow-Headers", "Content-Type");
  return cors(res);
}

export async function POST(req: Request) {
  let token = "";
  try {
    token = (await req.json()).token || "";
  } catch {
    /* no body */
  }
  const res = await verifyAndMint(token);
  if (!res.claims) return cors(NextResponse.json({ error: res.error }, { status: res.status }));
  return cors(NextResponse.json({ code: putCode(res.claims) }));
}
