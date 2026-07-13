"use client";
import { useEffect, useState } from "react";
import { listWorkflows, deleteWorkflow, renameWorkflow, cloneWorkflow, listOrgs, moveWorkflow, type OrgSummary } from "../lib/api";

interface Row {
  id: string;
  name: string;
  updated_at: string;
  org_id?: string | null;
  role?: string;
}

const RANK: Record<string, number> = { viewer: 1, editor: 2, admin: 3, owner: 4 };

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
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [moving, setMoving] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try { setRows(await listWorkflows()); } catch { setRows([]); }
    setLoading(false);
  };

  useEffect(() => {
    if (open) { setQ(""); setEditing(null); setMoving(null); refresh(); listOrgs().then(setOrgs).catch(() => {}); }
  }, [open]);

  const editableOrgs = orgs.filter((o) => RANK[o.role] >= RANK.editor);
  const orgName = (id?: string | null) => orgs.find((o) => o.id === id)?.name || "Org";
  const doMove = async (id: string, orgId: string | null) => {
    setMoving(null);
    try { await moveWorkflow(id, orgId); refresh(); } catch (e: any) { alert(e.message); }
  };

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
                  {r.org_id && <span className="rounded bg-vi/15 px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-ind" title={`Shared in ${orgName(r.org_id)} · your role: ${r.role}`}>⛬ {orgName(r.org_id)}{r.role && r.role !== "owner" ? ` · ${r.role}` : ""}</span>}
                </button>
              )}
              <span className="shrink-0 text-[11px] tabular-nums text-dim/70">{ago(r.updated_at)}</span>
              <div className="relative flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                {(editableOrgs.length > 0 || r.org_id) && RANK[r.role || "owner"] >= RANK.editor && (
                  <button title="Move to org / personal" onClick={() => setMoving(moving === r.id ? null : r.id)} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-ink">⇄</button>
                )}
                <button title="Rename" onClick={() => { setEditing(r.id); setEditName(r.name); }} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-ink">✎</button>
                <button title="Duplicate" onClick={() => doClone(r.id)} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-ink">⧉</button>
                <button title="Delete" onClick={() => doDelete(r.id, r.name)} className="rounded px-1.5 py-1 text-[12px] text-dim hover:bg-panel hover:text-bad">🗑</button>
                {moving === r.id && (
                  <div className="absolute right-0 top-8 z-10 w-44 rounded-lg border border-line bg-panel p-1 shadow-xl">
                    <div className="px-2 py-1 text-[9px] font-semibold uppercase tracking-wider text-dim">Move to</div>
                    {r.org_id && <button onClick={() => doMove(r.id, null)} className="block w-full rounded px-2 py-1.5 text-left text-[12px] text-ink hover:bg-line/60">Personal (private)</button>}
                    {editableOrgs.filter((o) => o.id !== r.org_id).map((o) => (
                      <button key={o.id} onClick={() => doMove(r.id, o.id)} className="block w-full rounded px-2 py-1.5 text-left text-[12px] text-ink hover:bg-line/60">⛬ {o.name}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
