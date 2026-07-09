"use client";
import { useEffect, useState } from "react";
import { getDeployment, deployWorkflow, undeployWorkflow, type Deployment } from "../lib/api";

export default function DeployModal({
  open,
  onClose,
  workflowId,
  workflowName,
}: {
  open: boolean;
  onClose: () => void;
  workflowId: string;
  workflowName: string;
}) {
  const [dep, setDep] = useState<Deployment | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      setCopied(false);
      getDeployment(workflowId).then(setDep).catch(() => setDep(null));
    }
  }, [open, workflowId]);

  if (!open) return null;

  const live = !!dep?.token && !!dep?.enabled;
  const url = live ? `${location.origin}/hooks/${dep!.token}` : "";
  const curl = live
    ? `curl -X POST ${url} \\\n  -H "Content-Type: application/json" \\\n  -d '{"email": "your input here"}'`
    : "";

  const doDeploy = async () => {
    setBusy(true);
    try { setDep(await deployWorkflow(workflowId)); } finally { setBusy(false); }
  };
  const doDisable = async () => {
    if (!confirm("Disable this webhook? The URL stops working immediately.")) return;
    setBusy(true);
    try { await undeployWorkflow(workflowId); setDep({ token: null, enabled: 0 }); } finally { setBusy(false); }
  };
  const copy = () => {
    navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); });
  };

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-20 w-[600px] max-w-[94%] rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-cy/15 text-[14px] text-cy">⚡</span>
          <span className="text-[14px] font-semibold text-ink">Deploy</span>
          <span className="truncate text-[12px] text-dim">— {workflowName}</span>
          <button onClick={onClose} className="ml-auto rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="p-5">
          {!live ? (
            <>
              <p className="mb-4 text-[13px] leading-relaxed text-dim">
                Deploying gives this workflow a <b className="text-ink">secret webhook URL</b>. Any system that
                POSTs JSON to it triggers a run — the body becomes <code className="rounded bg-bg px-1.5 py-0.5 text-[11px] text-cy">{"{{trigger.*}}"}</code> inside
                the workflow, and the final output is returned in the response.
              </p>
              <p className="mb-5 text-[12px] leading-relaxed text-dim/80">
                Runs are billed to <b className="text-ink">your</b> Nyquest wallet. The workflow always runs its latest saved version.
              </p>
              <button
                onClick={doDeploy}
                disabled={busy}
                className="rounded-lg bg-cy px-5 py-2 text-[13px] font-semibold text-bg hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Deploying…" : "⚡ Deploy as webhook"}
              </button>
            </>
          ) : (
            <>
              <div className="mb-1.5 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-ok" />
                <span className="text-[12px] font-semibold uppercase tracking-wider text-ok">Live</span>
                <span className="text-[11px] text-dim/70">POST JSON to trigger · latest saved version runs</span>
              </div>
              <div className="mb-3 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-lg border border-line bg-bg px-3 py-2.5 font-mono text-[12px] text-cy">{url}</code>
                <button onClick={copy} className="shrink-0 rounded-lg border border-line px-3 py-2 text-[12px] text-dim hover:border-cy hover:text-ink">
                  {copied ? "✓ Copied" : "Copy"}
                </button>
              </div>

              <div className="mb-4 rounded-lg border border-line bg-bg p-3">
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-dim">Example</div>
                <pre className="overflow-x-auto whitespace-pre font-mono text-[11px] leading-relaxed text-ink/85">{curl}</pre>
              </div>

              <div className="flex items-center gap-2">
                <button onClick={doDeploy} disabled={busy} className="rounded-lg border border-line px-4 py-1.5 text-[12px] text-dim hover:border-warn hover:text-warn disabled:opacity-50" title="Mints a new URL; the old one stops working">
                  ↻ Rotate URL
                </button>
                <button onClick={doDisable} disabled={busy} className="rounded-lg border border-line px-4 py-1.5 text-[12px] text-dim hover:border-bad hover:text-bad disabled:opacity-50">
                  Disable
                </button>
                <span className="ml-auto text-[11px] text-dim/70">Billed to your Nyquest wallet</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
