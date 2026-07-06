"use client";
import { useEffect, useState } from "react";
import { generateWorkflow } from "../lib/api";
import type { Workflow } from "../lib/store";

const EXAMPLES = [
  "A restaurant reservation concierge: greet the guest, extract date/party size, confirm availability, and reply.",
  "Classify an incoming support email as billing, bug, or sales, then draft a tailored response.",
  "Summarize a document, then decide if it needs legal review; if yes, flag it, otherwise approve.",
  "Take a topic, research talking points with an LLM, then write a 5-bullet meeting brief.",
];

export default function Flowsmith({
  open,
  onClose,
  onGenerated,
}: {
  open: boolean;
  onClose: () => void;
  onGenerated: (wf: Workflow) => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) { setError(null); setBusy(false); }
  }, [open]);

  if (!open) return null;

  const go = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const wf = await generateWorkflow(prompt.trim());
      onGenerated(wf);
      onClose();
    } catch (e: any) {
      setError(e?.message || "Something went wrong. Try rephrasing.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="absolute inset-0 z-30 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="mt-24 w-[620px] max-w-[92%] rounded-2xl border border-line bg-panel p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-vi/20 text-[15px] text-ind">✦</span>
          <div className="text-[14px] font-semibold text-ink">Flowsmith</div>
          <div className="text-[12px] text-dim">— describe a workflow, get a graph</div>
          <button onClick={onClose} className="ml-auto rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <textarea
          autoFocus
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") go(); }}
          placeholder="e.g. Build a workflow that reads a customer message, classifies the intent, and drafts a reply…"
          className="h-28 w-full resize-none rounded-xl border border-line bg-bg px-3.5 py-3 text-[13px] leading-relaxed text-ink outline-none focus:border-vi"
        />

        {error && <div className="mt-2 text-[12px] text-warn">{error}</div>}

        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex, i) => (
            <button
              key={i}
              onClick={() => setPrompt(ex)}
              className="rounded-full border border-line px-2.5 py-1 text-[11px] text-dim hover:border-ind/60 hover:text-ink"
            >
              {ex.split(":")[0].split(",")[0]}
            </button>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <span className="text-[11px] text-dim/70">⌘/Ctrl + Enter to forge</span>
          <button
            onClick={go}
            disabled={busy || !prompt.trim()}
            className="rounded-lg bg-gradient-to-r from-cy to-vi px-5 py-2 text-[12px] font-semibold text-bg transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? "Forging…" : "✦ Forge workflow"}
          </button>
        </div>
      </div>
    </div>
  );
}
