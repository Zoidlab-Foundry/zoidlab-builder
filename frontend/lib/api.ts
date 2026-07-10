// API helpers. Same-origin: Next rewrites /api/* to the FastAPI backend.
import type { Workflow } from "./store";

export async function fetchModels(): Promise<string[]> {
  try {
    const r = await fetch("/api/models");
    const j = await r.json();
    return j.models || [];
  } catch {
    return [];
  }
}

export async function generateWorkflow(prompt: string, model?: string): Promise<Workflow> {
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, model }),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.detail || "Flowsmith failed");
  }
  return r.json();
}

export async function saveWorkflow(wf: Workflow) {
  const r = await fetch("/api/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(wf),
  });
  if (!r.ok) throw new Error("Save failed");
  return r.json();
}

export async function listWorkflows() {
  const r = await fetch("/api/workflows");
  return (await r.json()).workflows || [];
}

export async function loadWorkflow(id: string): Promise<Workflow> {
  const r = await fetch(`/api/workflows/${id}`);
  if (!r.ok) throw new Error("Load failed");
  return r.json();
}

export async function deleteWorkflow(id: string) {
  await fetch(`/api/workflows/${id}`, { method: "DELETE" });
}

export async function renameWorkflow(id: string, name: string) {
  const r = await fetch(`/api/workflows/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error("Rename failed");
  return r.json();
}

export async function cloneWorkflow(id: string): Promise<{ id: string; name: string }> {
  const r = await fetch(`/api/workflows/${id}/clone`, { method: "POST" });
  if (!r.ok) throw new Error("Clone failed");
  return r.json();
}

export interface RunMeta {
  id: string;
  workflow_id: string;
  workflow_name: string;
  source: string;
  status: string;
  started_at: string;
  ms: number | null;
  tokens: number | null;
}

export interface Stats {
  total: number;
  ok: number;
  failed: number;
  success_rate: number | null;
  tokens: number;
  avg_ms: number;
  by_source: Record<string, number>;
  days: { d: string; n: number; ok: number }[];
}

export async function getStats(): Promise<Stats | null> {
  const r = await fetch("/api/stats");
  return r.ok ? r.json() : null;
}

export async function listRuns(workflowId?: string): Promise<RunMeta[]> {
  const r = await fetch("/api/runs" + (workflowId ? `?workflow_id=${workflowId}` : ""));
  return r.ok ? (await r.json()).runs || [] : [];
}

export async function getRun(id: string): Promise<any> {
  const r = await fetch(`/api/runs/${id}`);
  if (!r.ok) throw new Error("Run not found");
  return r.json();
}

export interface Deployment {
  token: string | null;
  enabled: number;
  created_at?: string;
}

export async function getDeployment(id: string): Promise<Deployment | null> {
  const r = await fetch(`/api/workflows/${id}/deployment`);
  return r.ok ? r.json() : null;
}

export async function deployWorkflow(id: string): Promise<Deployment> {
  const r = await fetch(`/api/workflows/${id}/deploy`, { method: "POST" });
  if (!r.ok) throw new Error("Deploy failed");
  return r.json();
}

export async function undeployWorkflow(id: string) {
  await fetch(`/api/workflows/${id}/deploy`, { method: "DELETE" });
}

export interface VersionMeta {
  id: string;
  name: string;
  label: string | null;
  created_at: string;
  nodes: number;
  edges: number;
}

export async function listVersions(id: string): Promise<VersionMeta[]> {
  const r = await fetch(`/api/workflows/${id}/versions`);
  if (!r.ok) return [];
  return (await r.json()).versions || [];
}

export async function snapshotWorkflow(id: string, label: string) {
  const r = await fetch(`/api/workflows/${id}/snapshot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!r.ok) throw new Error("Snapshot failed");
  return r.json();
}

export async function getVersion(vid: string): Promise<Workflow> {
  const r = await fetch(`/api/versions/${vid}`);
  if (!r.ok) throw new Error("Version not found");
  return r.json();
}

export async function restoreVersion(vid: string): Promise<Workflow> {
  const r = await fetch(`/api/versions/${vid}/restore`, { method: "POST" });
  if (!r.ok) throw new Error("Restore failed");
  return r.json();
}

export type RunEvent = {
  type: "start" | "node" | "done" | "error";
  nodeId?: string;
  status?: "running" | "complete" | "error";
  output?: string;
  ms?: number;
  tokens?: number | null;
  meta?: string;
  error?: string;
  nodes?: string[];
};

// Streams node status events from POST /api/run (SSE over fetch).
export async function runWorkflow(
  workflow: Workflow,
  trigger: Record<string, any>,
  onEvent: (ev: RunEvent) => void
) {
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, trigger }),
  });
  if (!res.body) throw new Error("No response stream");

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as RunEvent);
      } catch {
        /* ignore partial */
      }
    }
  }
}
