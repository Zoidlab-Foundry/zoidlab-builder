"use client";
import { useEffect, useState } from "react";
import { listWorkflows, deleteWorkflow, renameWorkflow, cloneWorkflow } from "../lib/api";

interface Row {
  id: string;
  name: string;
  updated_at: string;
}

function ago(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  if (!d) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function WorkflowsModal({
  open,
  onClose,
  onOpen,
  onNew,
  currentId,
}: {
  open: boolean;
  onClose: () => void;
  onOpen: (id: string) => void;
  onNew: () => void;
  currentId: string;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const refresh = async () => {
    setLoading(true);
    try { setRows(await listWorkflows()); } catch { setRows([]); }
    setLoading(false);
  };

  useEffect(() => {
    if (open) { setQ(""); setEditing(null); refresh(); }
  }, [open]);

  if (!open) return null;

  const filtered = rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase()));

  const doRename = async (id: string) => {
    const name = editName.trim();
    setEditing(null);
    if (name) { await renameWorkflow(id, name); refresh(); }
  };
  const doClone = async (id: string) => { await cloneWorkflow(id); refresh(); };
  const doDelete = async (id: string, name: string) => {
    if (confirm(`Delete “${name}”? This can't be undone.`)) { await deleteWorkflow(id); refresh(); }
  };

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-20 w-[600px] max-w-[92%] rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="text-[14px] font-semibold text-ink">Workflows</span>
          <span className="text-[11px] text-dim">{rows.length}</span>
          <button
            onClick={() => { onNew(); onClose(); }}
            className="ml-auto rounded-lg bg-cy px-3.5 py-1.5 text-[12px] font-semibold text-bg hover:opacity-90"
          >
            ＋ New workflow
          </button>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="px-5 pt-3">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search workflows…"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-[13px] text-ink outline-none focus:border-cy"
          />
        </div>

        <div className="max-h-[52vh] overflow-y-auto px-3 py-3">
          {loading && <div className="px-2 py-6 text-center text-[12px] text-dim">Loading…</div>}
          {!loading && filtered.length === 0 && (
            <div className="px-2 py-8 text-center text-[12px] text-dim">
              {rows.length === 0 ? "No workflows yet. Create one to get started." : "No matches."}
            </div>
          )}
          {filtered.map((r) => (
            <div
              key={r.id}
              className={`group flex items-center gap-2 rounded-lg px-3 py-2.5 ${r.id === currentId ? "bg-cy/10" : "hover:bg-line/60"}`}
            >
              {editing === r.id ? (
                <input
                  autoFocus
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") doRename(r.id); if (e.key === "Escape") setEditing(null); }}
                  onBlur={() => doRename(r.id)}
                  className="flex-1 rounded border border-cy bg-bg px-2 py-1 text-[13px] text-ink outline-none"
                />
              ) : (
                <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => { onOpen(r.id); onClose(); }}>
                  <span className="truncate text-[13px] text-ink">{r.name}</span>
                  {r.id === currentId && <span className="rounded bg-cy/20 px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-cy">OPEN</span>}
                </button>
              )}
              <span className="shrink-0 text-[11px] tabular-nums text-dim/70">{ago(r.updated_at)}</span>
              <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                <button title="Rename" onClick={() => { setEditing(r.id); setEditName(r.name); }} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-ink">✎</button>
                <button title="Duplicate" onClick={() => doClone(r.id)} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-ink">⧉</button>
                <button title="Delete" onClick={() => doDelete(r.id, r.name)} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-bad">🗑</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
