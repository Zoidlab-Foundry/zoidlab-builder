"use client";
import { useEffect, useState } from "react";
import {
  listOrgs, createOrg, getOrg, renameOrg, deleteOrg,
  addMember, updateMember, removeMember, type OrgSummary, type Role,
} from "../lib/api";

const ROLES: Role[] = ["viewer", "editor", "admin", "owner"];
const RANK: Record<Role, number> = { viewer: 1, editor: 2, admin: 3, owner: 4 };

export default function OrgsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [sel, setSel] = useState<any | null>(null);
  const [newName, setNewName] = useState("");
  const [invEmail, setInvEmail] = useState("");
  const [invRole, setInvRole] = useState<Role>("viewer");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => setOrgs(await listOrgs());
  useEffect(() => { if (open) { setSel(null); setErr(""); refresh(); } }, [open]);

  const openOrg = async (oid: string) => { setErr(""); try { setSel(await getOrg(oid)); } catch (e: any) { setErr(e.message); } };

  async function create() {
    if (!newName.trim()) return;
    setBusy(true); setErr("");
    try { const o = await createOrg(newName.trim()); setNewName(""); await refresh(); openOrg(o.id); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function invite() {
    if (!invEmail.trim() || !sel) return;
    setBusy(true); setErr("");
    try { await addMember(sel.id, invEmail.trim(), invRole); setInvEmail(""); openOrg(sel.id); refresh(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function changeRole(mid: string, role: Role) {
    setErr("");
    try { await updateMember(sel.id, mid, role); openOrg(sel.id); }
    catch (e: any) { setErr(e.message); }
  }
  async function kick(mid: string) {
    setErr("");
    try { await removeMember(sel.id, mid); openOrg(sel.id); refresh(); }
    catch (e: any) { setErr(e.message); }
  }
  async function rename() {
    const n = prompt("Rename organization", sel.name);
    if (!n) return;
    try { await renameOrg(sel.id, n); openOrg(sel.id); refresh(); } catch (e: any) { setErr(e.message); }
  }
  async function destroy() {
    if (!confirm(`Delete "${sel.name}"? Its workflows return to their owners' personal space.`)) return;
    try { await deleteOrg(sel.id); setSel(null); refresh(); } catch (e: any) { setErr(e.message); }
  }

  if (!open) return null;
  const myRole: Role = sel?.role || "viewer";
  const canAdmin = sel && RANK[myRole] >= RANK.admin;
  const isOwner = myRole === "owner";

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-12 flex max-h-[85vh] w-[680px] max-w-[95%] flex-col rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-vi/15 text-[14px] text-ind">⛬</span>
          <span className="text-[14px] font-semibold text-ink">Organizations</span>
          {sel && <button onClick={() => setSel(null)} className="ml-2 text-[12px] text-cy hover:underline">← all orgs</button>}
          <button onClick={onClose} className="ml-auto rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        {err && <div className="mx-5 mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[12px] text-bad">{err}</div>}

        {!sel ? (
          <div className="flex min-h-0 flex-col overflow-y-auto p-4">
            <div className="mb-3 flex gap-2">
              <input value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()}
                placeholder="New organization name" className="flex-1 rounded-lg border border-line bg-panel2 px-3 py-2 text-[13px] text-ink outline-none focus:border-cy" />
              <button onClick={create} disabled={busy || !newName.trim()} className="rounded-lg bg-vi/20 px-4 py-2 text-[13px] font-medium text-ind hover:bg-vi/30 disabled:opacity-50">Create</button>
            </div>
            {orgs.length === 0 && <div className="py-10 text-center text-[12px] text-dim">No organizations yet. Create one to share workflows with a team.</div>}
            {orgs.map((o) => (
              <button key={o.id} onClick={() => openOrg(o.id)} className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-line/60">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-panel2 text-[13px] font-semibold text-ind">{o.name[0]?.toUpperCase()}</span>
                <span className="min-w-0 flex-1"><span className="block truncate text-[13px] text-ink">{o.name}</span><span className="text-[11px] text-dim">{o.members} member{o.members > 1 ? "s" : ""} · {o.workflows} workflow{o.workflows === 1 ? "" : "s"}</span></span>
                <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wide text-dim">{o.role}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="flex min-h-0 flex-col overflow-y-auto p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-[16px] font-semibold text-ink">{sel.name}</span>
              <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wide text-dim">you: {myRole}</span>
              {isOwner && <button onClick={rename} className="ml-auto text-[11px] text-dim hover:text-ink">Rename</button>}
              {isOwner && <button onClick={destroy} className="text-[11px] text-dim hover:text-bad">Delete</button>}
            </div>

            {canAdmin && (
              <div className="mb-4 rounded-xl border border-line bg-panel2 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Invite by email</div>
                <div className="flex gap-2">
                  <input value={invEmail} onChange={(e) => setInvEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && invite()}
                    placeholder="teammate@company.com" className="flex-1 rounded-lg border border-line bg-panel px-3 py-1.5 text-[13px] text-ink outline-none focus:border-cy" />
                  <select value={invRole} onChange={(e) => setInvRole(e.target.value as Role)} className="rounded-lg border border-line bg-panel px-2 py-1.5 text-[12px] text-ink">
                    {ROLES.filter((r) => r !== "owner").map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button onClick={invite} disabled={busy || !invEmail.trim()} className="rounded-lg bg-vi/20 px-3 py-1.5 text-[12px] font-medium text-ind hover:bg-vi/30 disabled:opacity-50">Invite</button>
                </div>
                <div className="mt-1.5 text-[10.5px] text-dim/70">They join automatically the next time they sign in with that email.</div>
              </div>
            )}

            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Members ({sel.members.length})</div>
            <div className="flex flex-col gap-1">
              {sel.members.map((m: any) => (
                <div key={m.id} className="flex items-center gap-2.5 rounded-lg border border-line bg-panel2 px-3 py-2">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel text-[11px] text-dim">{(m.email || m.user_id || "?")[0]?.toUpperCase()}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] text-ink">{m.email || m.user_id || "(unknown)"}</span>
                    {m.status === "pending" && <span className="text-[10px] text-warn">pending — joins on next sign-in</span>}
                  </span>
                  {canAdmin && m.role !== "owner" ? (
                    <select value={m.role} onChange={(e) => changeRole(m.id, e.target.value as Role)}
                      className="rounded-md border border-line bg-panel px-1.5 py-1 text-[11px] text-ink">
                      {ROLES.filter((r) => r !== "owner" || isOwner).map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  ) : (
                    <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wide text-dim">{m.role}</span>
                  )}
                  {canAdmin && m.role !== "owner" && <button onClick={() => kick(m.id)} className="text-[12px] text-dim hover:text-bad" title="Remove">✕</button>}
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-lg border border-line bg-panel2/50 px-3 py-2 text-[10.5px] leading-relaxed text-dim/80">
              <b className="text-dim">Roles:</b> viewer (read + run) · editor (+ edit/version/deploy) · admin (+ manage members) · owner (+ rename/delete org).
              Move a workflow into this org from the workflow's ⋯ menu.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
