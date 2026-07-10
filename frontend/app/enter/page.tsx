"use client";
import { useEffect, useState } from "react";

// Handoff landing: the Nyquest app links here with the user's token in the URL
// fragment (#t=…). We exchange it for a ZoidLab session, then bounce to the app.
export default function Enter() {
  const [state, setState] = useState<"working" | "no-token" | "not-pro" | "failed">("working");

  useEffect(() => {
    const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    const search = new URLSearchParams(location.search);
    const code = hash.get("c") || search.get("c");
    const token = hash.get("t") || search.get("t");
    const body = code ? { code } : token ? { token } : null;
    if (!body) { setState("no-token"); return; }
    fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        if (r.ok) {
          history.replaceState(null, "", "/");
          location.href = "/";
        } else {
          const j = await r.json().catch(() => ({}));
          setState(j.error === "pro_required" ? "not-pro" : "failed");
        }
      })
      .catch(() => setState("failed"));
  }, []);

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg text-center">
      <div className="max-w-sm px-6">
        {state === "working" && (
          <>
            <div className="mx-auto mb-4 h-6 w-6 animate-spin rounded-full border-2 border-line border-t-cy" />
            <p className="text-[13px] text-dim">Signing you in with Nyquest…</p>
          </>
        )}
        {state === "not-pro" && (
          <>
            <p className="mb-2 text-[15px] font-semibold text-ink">ZoidLab is a Pro workspace</p>
            <p className="text-[13px] leading-relaxed text-dim">Your Nyquest account isn’t on a Pro or Teams plan. Upgrade at <a className="text-cy" href="https://app.nyquest.ai/pricing">app.nyquest.ai/pricing</a> to get in.</p>
          </>
        )}
        {(state === "failed" || state === "no-token") && (
          <>
            <p className="mb-2 text-[15px] font-semibold text-ink">Couldn’t sign you in</p>
            <p className="text-[13px] leading-relaxed text-dim">Open ZoidLab from your Nyquest app to get a fresh link, or <a className="text-cy" href="https://app.nyquest.ai">sign in to Nyquest</a> first.</p>
          </>
        )}
      </div>
    </div>
  );
}
