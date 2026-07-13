"use client";
import { useEffect, useState } from "react";
import { analyzeWorkflow, optimizeWorkflow, type Analysis } from "../lib/api";
import type { Workflow } from "../lib/store";

const SEV: Record<string, { color: string; bg: string; label: string }> = {
  high: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", label: "HIGH" },
  medium: { color: "#f4b860", bg: "rgba(244,184,96,0.12)", label: "MED" },
  low: { color: "#8aa0c6", bg: "rgba(138,160,198,0.10)", label: "LOW" },
};

function scoreColor(s: number) {
  return s >= 80 ? "#22c55e" : s >= 55 ? "#f4b860" : "#ef4444";
}

export default function OptimizeModal({
  open, onClose, getWorkflow, onApply, onFocusNode,
}: {
  open: boolean;
  onClose: () => void;
  getWorkflow: () => Workflow;
  onApply: (wf: Workflow) => void;
  onFocusNode: (id: string) => void;
}) {
  const [a, setA] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState<string[] | null>(null);
  const [err, setErr] = useState("");

  const run = async () => {
    setLoading(true); setErr(""); setApplied(null);
    try { setA(await analyzeWorkflow(getWorkflow())); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { if (open) run(); }, [open]);

  const apply = async () => {
    setApplying(true); setErr("");
    try {
      const res = await optimizeWorkflow(getWorkflow());
      if (res.count > 0) { onApply(res.workflow); setApplied(res.applied); setTimeout(run, 150); }
      else setApplied([]);
    } catch (e: any) { setErr(e.message); } finally { setApplying(false); }
  };

  if (!open) return null;
  const fixable = a?.summary.fixable ?? 0;

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-12 flex max-h-[85vh] w-[720px] max-w-[95%] flex-col rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-vi/15 text-[14px] text-ind">⚡</span>
          <span className="text-[14px] font-semibold text-ink">Optimizer</span>
          <span className="text-[11px] text-dim">quality · performance · auto-fix</span>
          <button onClick={run} className="ml-auto rounded-md px-2 py-1 text-[12px] text-dim hover:bg-line hover:text-ink" title="Re-analyze">↻</button>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        {err && <div className="mx-5 mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[12px] text-bad">{err}</div>}
        {loading && !a && <div className="px-5 py-10 text-center text-[12px] text-dim">Analyzing…</div>}

        {a && (
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {/* score + summary */}
            <div className="flex items-center gap-5">
              <div className="relative grid h-20 w-20 shrink-0 place-items-center">
                <svg viewBox="0 0 36 36" className="h-20 w-20 -rotate-90">
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="3" />
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke={scoreColor(a.score)} strokeWidth="3"
                    strokeDasharray={`${a.score} 100`} strokeLinecap="round" />
                </svg>
                <div className="absolute text-center"><div className="text-[20px] font-semibold tabular-nums text-ink">{a.score}</div><div className="-mt-1 text-[8px] uppercase tracking-wider text-dim">score</div></div>
              </div>
              <div className="flex-1">
                <div className="text-[13px] text-ink">{a.summary.issues} issue{a.summary.issues !== 1 ? "s" : ""} found{a.summary.high ? ` · ${a.summary.high} high-severity` : ""}</div>
                <div className="mt-0.5 text-[12px] text-dim">{a.summary.runs_analyzed > 0 ? `Performance analyzed from ${a.summary.runs_analyzed} recent run(s).` : "Run this workflow to unlock performance recommendations."}</div>
                {fixable > 0 && (
                  <button onClick={apply} disabled={applying} className="mt-2.5 rounded-lg bg-vi/20 px-4 py-1.5 text-[12.5px] font-semibold text-ind hover:bg-vi/30 disabled:opacity-50">
                    {applying ? "Applying…" : `⚡ Apply ${fixable} safe fix${fixable !== 1 ? "es" : ""}`}
                  </button>
                )}
              </div>
            </div>

            {applied && (
              <div className="mt-3 rounded-lg border border-ok/30 bg-ok/5 px-3 py-2 text-[12px] text-ok">
                {applied.length ? <>Applied {applied.length} fix{applied.length !== 1 ? "es" : ""} to the canvas:<ul className="mt-1 list-disc pl-4 text-[11.5px] text-ok/90">{applied.map((x, i) => <li key={i}>{x}</li>)}</ul></> : "Nothing to auto-fix — the safe hardening is already in place."}
              </div>
            )}

            {/* performance recommendations */}
            {a.recommendations.length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Performance · from real runs</div>
                <div className="flex flex-col gap-1.5">
                  {a.recommendations.map((p, i) => (
                    <button key={i} onClick={() => p.node_id && (onFocusNode(p.node_id), onClose())}
                      className="rounded-lg border border-vi/25 bg-vi/[0.06] px-3 py-2 text-left hover:border-vi/50">
                      <div className="text-[12.5px] font-medium text-ink">{p.title}</div>
                      <div className="mt-0.5 text-[11.5px] text-dim">{p.detail}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* quality checks */}
            <div className="mt-4">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Quality checks</div>
              {a.checks.length === 0 && <div className="rounded-lg border border-ok/30 bg-ok/5 px-3 py-3 text-[12px] text-ok">✓ No issues — this workflow is clean.</div>}
              <div className="flex flex-col gap-1.5">
                {a.checks.map((c, i) => (
                  <button key={i} disabled={!c.node_id} onClick={() => c.node_id && (onFocusNode(c.node_id), onClose())}
                    className={`flex items-start gap-2.5 rounded-lg border border-line bg-panel2 px-3 py-2 text-left ${c.node_id ? "hover:border-cy/50" : ""}`}>
                    <span className="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide" style={{ color: SEV[c.severity].color, background: SEV[c.severity].bg }}>{SEV[c.severity].label}</span>
                    <span className="min-w-0 flex-1">
                      <span className="text-[12.5px] font-medium text-ink">{c.title}{c.fixable && <span className="ml-1.5 text-[10px] text-ind">auto-fixable</span>}</span>
                      <span className="mt-0.5 block text-[11.5px] leading-snug text-dim">{c.detail}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-line bg-panel2/50 px-3 py-2 text-[10.5px] leading-relaxed text-dim/80">
              Auto-fix applies only <b className="text-dim">safe, behavior-preserving</b> changes (timeouts, retries, a fallback route, a missing End). Model swaps and prompt edits change output quality, so they stay as recommendations for you to apply.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
