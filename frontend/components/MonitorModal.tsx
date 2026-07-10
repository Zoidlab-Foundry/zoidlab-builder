"use client";
import { useEffect, useState } from "react";
import { getStats, listRuns, getRun, type Stats, type RunMeta } from "../lib/api";

function ago(iso: string): string {
  const d = new Date(iso).getTime();
  if (!d) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
const fmtMs = (ms: number | null) => (ms == null ? "—" : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);
const fmtTok = (t: number) => (t >= 1000 ? `${(t / 1000).toFixed(1)}k` : String(t));

const STATUS_COLOR: Record<string, string> = { complete: "#22c55e", error: "#ef4444", running: "#f4b860" };

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel2 p-3.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">{label}</div>
      <div className="mt-1 text-[22px] font-semibold tabular-nums text-ink">{value}</div>
      {sub && <div className="text-[11px] text-dim/70">{sub}</div>}
    </div>
  );
}

export default function MonitorModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState<any | null>(null);

  const refresh = async () => {
    setLoading(true);
    const [s, r] = await Promise.all([getStats(), listRuns()]);
    setStats(s);
    setRuns(r);
    setLoading(false);
  };
  useEffect(() => {
    if (open) { setSel(null); refresh(); }
  }, [open]);

  if (!open) return null;

  const maxDay = Math.max(1, ...(stats?.days || []).map((d) => d.n));

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-12 flex max-h-[85vh] w-[760px] max-w-[95%] flex-col rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-cy/15 text-[14px] text-cy">◷</span>
          <span className="text-[14px] font-semibold text-ink">Monitoring</span>
          {sel && <button onClick={() => setSel(null)} className="ml-2 text-[12px] text-cy hover:underline">← all runs</button>}
          <button onClick={refresh} className="ml-auto rounded-md px-2 py-1 text-[12px] text-dim hover:bg-line hover:text-ink" title="Refresh">↻</button>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        {!sel ? (
          <div className="flex min-h-0 flex-col">
            {/* stat tiles */}
            <div className="grid grid-cols-4 gap-3 px-5 pt-4">
              <Tile label="Runs" value={String(stats?.total ?? 0)} sub={stats ? `${stats.failed} failed` : ""} />
              <Tile label="Success" value={stats?.success_rate != null ? `${stats.success_rate}%` : "—"} sub={stats ? `${stats.ok} ok` : ""} />
              <Tile label="Tokens" value={fmtTok(stats?.tokens ?? 0)} sub="total" />
              <Tile label="Avg runtime" value={fmtMs(stats?.avg_ms ?? 0)} sub="per run" />
            </div>

            {/* 14-day activity */}
            {stats && stats.days.length > 0 && (
              <div className="px-5 pt-4">
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Activity</div>
                <div className="flex items-end gap-1.5" style={{ height: 44 }}>
                  {stats.days.map((d) => (
                    <div key={d.d} className="flex-1" title={`${d.d}: ${d.n} runs, ${d.ok} ok`}>
                      <div className="w-full rounded-sm bg-cy/70" style={{ height: Math.max(3, (d.n / maxDay) * 40) }} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* runs list */}
            <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
              <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Recent runs</div>
              {loading && <div className="px-2 py-6 text-center text-[12px] text-dim">Loading…</div>}
              {!loading && runs.length === 0 && (
                <div className="px-2 py-8 text-center text-[12px] text-dim">No runs yet. Hit ▸ Run or trigger a deployed webhook.</div>
              )}
              {runs.map((r) => (
                <button key={r.id} onClick={() => getRun(r.id).then(setSel).catch(() => {})}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-line/60">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] || "#565b6e" }} />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{r.workflow_name}</span>
                  <span className="shrink-0 rounded bg-line px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-dim">{r.source}</span>
                  <span className="w-14 shrink-0 text-right text-[11px] tabular-nums text-dim">{fmtMs(r.ms)}</span>
                  <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-dim">{r.tokens ? fmtTok(r.tokens) : "—"}</span>
                  <span className="w-16 shrink-0 text-right text-[11px] tabular-nums text-dim/70">{ago(r.started_at)}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* run detail */
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_COLOR[sel.status] || "#565b6e" }} />
              <span className="text-[15px] font-semibold text-ink">{sel.workflow_name}</span>
              <span className="rounded bg-line px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-dim">{sel.source}</span>
              <span className="ml-auto text-[11px] text-dim">{fmtMs(sel.ms)} · {sel.tokens ? fmtTok(sel.tokens) + " tok" : "—"} · {ago(sel.started_at)}</span>
            </div>

            {sel.error && (
              <div className="mb-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[12px] text-bad">{sel.error}</div>
            )}

            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Node timeline</div>
            <div className="mb-4 flex flex-col gap-1">
              {(sel.events || []).filter((e: any) => e.type === "node" && e.status !== "running").map((e: any, i: number) => (
                <div key={i} className="flex items-center gap-2.5 rounded-lg border border-line bg-panel2 px-3 py-2">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: STATUS_COLOR[e.status] || "#565b6e" }} />
                  <span className="w-24 shrink-0 truncate text-[12px] text-ink">{e.nodeId}</span>
                  <span className="min-w-0 flex-1 truncate text-[11px] text-dim">{e.error || e.meta || ""}</span>
                  <span className="shrink-0 text-[11px] tabular-nums text-dim/70">{e.ms != null ? fmtMs(e.ms) : ""}{e.tokens ? ` · ${e.tokens}t` : ""}</span>
                </div>
              ))}
            </div>

            {sel.output && (
              <>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Output</div>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-bg p-3 font-mono text-[12px] leading-relaxed text-ink/90">{sel.output}</pre>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
