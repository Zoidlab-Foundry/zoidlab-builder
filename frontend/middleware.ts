import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Interim access gate (HTTP Basic Auth). Replace with Cloudflare Access
// once a zoidlab.ai-scoped token is available. Credentials from env.
const USER = process.env.BUILDER_USER || "zoid";
const PASS = process.env.BUILDER_PASS || "changeme";

export function middleware(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (auth?.startsWith("Basic ")) {
    try {
      const [u, p] = atob(auth.slice(6)).split(":");
      if (u === USER && p === PASS) return NextResponse.next();
    } catch {
      /* fallthrough */
    }
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="ZoidLab Builder", charset="UTF-8"' },
  });
}

export const config = {
  // gate everything except Next's static assets
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
