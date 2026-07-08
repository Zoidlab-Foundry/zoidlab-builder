"use client";
import { useEffect, useState } from "react";
import { listVersions, getVersion, restoreVersion, snapshotWorkflow, type VersionMeta } from "../lib/api";
import type { Workflow } from "../lib/store";
import { defByType } from "../lib/catalog";

function ago(iso: string): string {
  const d = new Date(iso).getTime();
  if (!d) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

interface Diff {
  willAdd: string[];    // in this version, not on canvas → restore adds them
  willRemove: string[]; // on canvas, not in this version → restore removes them
  willChange: string[]; // same node, different config
}

function diffGraphs(version: Workflow, current: { nodes: any[] }): Diff {
  const vById = new Map(version.nodes.map((n) => [n.id, n]));
  const cById = new Map(current.nodes.map((n) => [n.id, n]));
  const label = (n: any) => defByType(n.type || n.data?.nodeType)?.label || n.type || "node";
  const willAdd: string[] = [];
  const willRemove: string[] = [];
  const willChange: string[] = [];
  for (const [id, n] of cById) if (!vById.has(id)) willRemove.push(label(n));
  for (const [id, n] of vById) {
    if (!cById.has(id)) { willAdd.push(label(n)); continue; }
    if (JSON.stringify(n.data) !== JSON.stringify(cById.get(id).data)) willChange.push(label(n));
  }
  return { willAdd, willRemove, willChange };
}

export default function HistoryModal({
  open,
  onClose,
  workflowId,
  current,
  onRestore,
}: {
  open: boolean;
  onClose: () => void;
  workflowId: string;
  current: { nodes: any[]; edges: any[] };
  onRestore: (wf: Workflow) => void;
}) {
  const [versions, setVersions] = useState<VersionMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try { setVersions(await listVersions(workflowId)); } catch { setVersions([]); }
    setLoading(false);
  };

  useEffect(() => {
    if (open) { setSel(null); setDiff(null); refresh(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workflowId]);

  if (!open) return null;

  const selectVersion = async (id: string) => {
    setSel(id);
    setDiff(null);
    try {
      const v = await getVersion(id);
      setDiff(diffGraphs(v, current));
    } catch { setDiff(null); }
  };

  const saveVersion = async () => {
    const label = prompt("Name this version (optional):", "") ?? "";
    setSaving(true);
    try { await snapshotWorkflow(workflowId, label); await refresh(); }
    finally { setSaving(false); }
  };

  const doRestore = async (id: string) => {
    if (!confirm("Restore this version? Your current canvas will be replaced (and saved to history first).")) return;
    const wf = await restoreVersion(id);
    onRestore(wf);
    onClose();
  };

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-16 w-[620px] max-w-[94%] rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="text-[14px] font-semibold text-ink">Version history</span>
          <span className="text-[12px] text-dim">{versions.length}</span>
          <button onClick={saveVersion} disabled={saving} className="ml-auto rounded-lg bg-cy px-3.5 py-1.5 text-[12px] font-semibold text-bg hover:opacity-90 disabled:opacity-50">
            {saving ? "Saving…" : "＋ Save version"}
          </button>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="max-h-[58vh] overflow-y-auto px-3 py-3">
          {loading && <div className="px-2 py-6 text-center text-[12px] text-dim">Loading…</div>}
          {!loading && versions.length === 0 && (
            <div className="px-2 py-8 text-center text-[12px] text-dim">
              No versions yet. They're captured automatically as you edit, or hit “Save version”.
            </div>
          )}
          {versions.map((v, i) => (
            <div key={v.id} className={`rounded-lg ${sel === v.id ? "bg-cy/10" : "hover:bg-line/60"}`}>
              <button className="flex w-full items-center gap-2 px-3 py-2.5 text-left" onClick={() => selectVersion(v.id)}>
                <span className={`h-2 w-2 shrink-0 rounded-full ${v.label ? "bg-cy" : "bg-dim/50"}`} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-ink">
                    {v.label || "Auto-save"}
                    {i === 0 && <span className="ml-2 rounded bg-cy/20 px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-cy">LATEST</span>}
                  </div>
                  <div className="text-[10px] text-dim/70">{v.nodes} nodes · {v.edges} edges</div>
                </div>
                <span className="shrink-0 text-[11px] tabular-nums text-dim/70">{ago(v.created_at)}</span>
              </button>

              {sel === v.id && (
                <div className="border-t border-line px-3 py-2.5">
                  {diff ? (
                    <div className="flex flex-col gap-1 text-[11px]">
                      {diff.willAdd.length === 0 && diff.willRemove.length === 0 && diff.willChange.length === 0 ? (
                        <span className="text-dim">Identical to your current canvas.</span>
                      ) : (
                        <span className="text-dim/70">Restoring would:</span>
                      )}
                      {diff.willAdd.length > 0 && <span className="text-ok">+ add {diff.willAdd.length}: {diff.willAdd.join(", ")}</span>}
                      {diff.willRemove.length > 0 && <span className="text-bad">− remove {diff.willRemove.length}: {diff.willRemove.join(", ")}</span>}
                      {diff.willChange.length > 0 && <span className="text-warn">~ change config on {diff.willChange.length}: {diff.willChange.join(", ")}</span>}
                    </div>
                  ) : (
                    <div className="text-[11px] text-dim">Comparing…</div>
                  )}
                  <button onClick={() => doRestore(v.id)} className="mt-2.5 rounded-lg border border-cy/40 bg-cy/10 px-3.5 py-1.5 text-[12px] font-semibold text-cy hover:bg-cy/20">
                    ⟲ Restore this version
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
