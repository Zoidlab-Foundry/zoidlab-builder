"use client";
import { useEffect, useState } from "react";
import { listAudit, listOrgs, type AuditEntry, type OrgSummary } from "../lib/api";

function ago(iso: string): string {
  const d = new Date(iso).getTime();
  if (!d) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const ICON: Record<string, string> = {
  created: "✚", deleted: "🗑", moved: "→", deployed: "⚡", undeployed: "⏻",
  scheduled: "⏱", version_restored: "⟲", invited: "✉", role_changed: "⇅", removed: "✕", renamed: "✎",
};

export default function AuditModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [scope, setScope] = useState<string>("");   // "" = mine, else org id
  const [loading, setLoading] = useState(false);

  const refresh = async (s: string) => {
    setLoading(true);
    setRows(await listAudit(s || undefined));
    setLoading(false);
  };
  useEffect(() => { if (open) { setScope(""); refresh(""); listOrgs().then(setOrgs); } }, [open]);

  if (!open) return null;
  const adminOrgs = orgs.filter((o) => o.role === "admin" || o.role === "owner");

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-12 flex max-h-[85vh] w-[680px] max-w-[95%] flex-col rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-cy/15 text-[14px] text-cy">❋</span>
          <span className="text-[14px] font-semibold text-ink">Audit log</span>
          <select value={scope} onChange={(e) => { setScope(e.target.value); refresh(e.target.value); }}
            className="ml-3 rounded-md border border-line bg-panel2 px-2 py-1 text-[12px] text-ink">
            <option value="">My activity</option>
            {adminOrgs.map((o) => <option key={o.id} value={o.id}>{o.name} (org)</option>)}
          </select>
          <button onClick={() => refresh(scope)} className="ml-auto rounded-md px-2 py-1 text-[12px] text-dim hover:bg-line hover:text-ink">↻</button>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {loading && <div className="py-8 text-center text-[12px] text-dim">Loading…</div>}
          {!loading && rows.length === 0 && <div className="py-10 text-center text-[12px] text-dim">No audit entries yet.</div>}
          {rows.map((a) => (
            <div key={a.id} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-line/40">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-panel2 text-[13px] text-dim">{ICON[a.action] || "•"}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] text-ink">
                  <b className="font-medium">{a.action.replace(/_/g, " ")}</b> {a.entity_type}
                  {a.details?.name ? ` "${a.details.name}"` : ""}
                  {a.details?.role ? ` → ${a.details.role}` : ""}
                  {a.details?.email ? ` (${a.details.email})` : ""}
                </span>
                <span className="text-[10.5px] text-dim/70">{(a.actor_user_id || "system").slice(0, 12)} · {a.entity_id?.slice(0, 16)}</span>
              </span>
              <span className="shrink-0 text-[11px] tabular-nums text-dim/70">{ago(a.created_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
