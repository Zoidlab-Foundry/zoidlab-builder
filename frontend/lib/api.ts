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
