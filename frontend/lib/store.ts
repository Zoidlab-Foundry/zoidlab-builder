import { create } from "zustand";
import {
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from "@xyflow/react";
import { defaultData, defByType } from "./catalog";

export type WFNodeData = { nodeType: string; config: Record<string, any> };
export type WFNode = Node<WFNodeData>;

export interface Workflow {
  id: string;
  name: string;
  nodes: { id: string; type: string; position: { x: number; y: number }; data: Record<string, any> }[];
  edges: { id: string; source: string; target: string; sourceHandle?: string | null }[];
}

export type NodeRun = {
  status: "running" | "complete" | "error";
  output?: string;
  ms?: number;
  tokens?: number | null;
  meta?: string;
  error?: string;
};

let idc = 1;
const nid = () => `n${Date.now().toString(36)}${idc++}`;

interface State {
  workflowId: string;
  name: string;
  nodes: WFNode[];
  edges: Edge[];
  selectedId: string | null;
  models: string[];
  running: boolean;
  runStatus: Record<string, NodeRun>;
  finalOutput: string | null;

  setName: (n: string) => void;
  setModels: (m: string[]) => void;
  onNodesChange: (c: NodeChange[]) => void;
  onEdgesChange: (c: EdgeChange[]) => void;
  onConnect: (c: Connection) => void;
  addNode: (type: string, pos: { x: number; y: number }) => void;
  updateConfig: (id: string, patch: Record<string, any>) => void;
  select: (id: string | null) => void;
  deleteNode: (id: string) => void;
  deleteEdge: (id: string) => void;
  duplicateNode: (id: string) => void;
  copyNode: (id: string) => void;
  pasteNode: (pos: { x: number; y: number }) => void;
  autoArrange: () => void;
  clipboard: WFNodeData | null;

  setRunning: (b: boolean) => void;
  setNodeRun: (id: string, r: NodeRun) => void;
  clearRun: () => void;
  setFinalOutput: (s: string | null) => void;
  animateFrom: (sourceId: string, on: boolean) => void;
  clearEdgeAnim: () => void;

  toWorkflow: () => Workflow;
  loadWorkflow: (wf: Workflow) => void;
  reset: () => void;
}

const starter = (): { nodes: WFNode[]; edges: Edge[] } => {
  const s: WFNode = { id: "start", type: "wf", position: { x: 80, y: 220 }, data: { nodeType: "start", config: defaultData("start") } };
  const e: WFNode = { id: "end", type: "wf", position: { x: 720, y: 220 }, data: { nodeType: "end", config: {} } };
  return { nodes: [s, e], edges: [] };
};

export const useStore = create<State>((set, get) => ({
  workflowId: "wf_" + Math.random().toString(36).slice(2, 9),
  name: "Untitled workflow",
  ...starter(),
  selectedId: null,
  models: [],
  running: false,
  runStatus: {},
  finalOutput: null,

  setName: (n) => set({ name: n }),
  setModels: (m) => set({ models: m }),

  onNodesChange: (c) => set({ nodes: applyNodeChanges(c, get().nodes) as WFNode[] }),
  onEdgesChange: (c) => set({ edges: applyEdgeChanges(c, get().edges) }),
  onConnect: (c) =>
    set({ edges: addEdge({ ...c, animated: false }, get().edges) }),

  addNode: (type, pos) => {
    const node: WFNode = { id: nid(), type: "wf", position: pos, data: { nodeType: type, config: defaultData(type) } };
    set({ nodes: [...get().nodes, node], selectedId: node.id });
  },

  updateConfig: (id, patch) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, config: { ...n.data.config, ...patch } } } : n
      ),
    }),

  select: (id) => set({ selectedId: id }),

  deleteNode: (id) =>
    set({
      nodes: get().nodes.filter((n) => n.id !== id),
      edges: get().edges.filter((e) => e.source !== id && e.target !== id),
      selectedId: null,
    }),

  deleteEdge: (id) => set({ edges: get().edges.filter((e) => e.id !== id) }),

  clipboard: null,

  duplicateNode: (id) => {
    const src = get().nodes.find((n) => n.id === id);
    if (!src) return;
    const copy: WFNode = {
      id: nid(),
      type: "wf",
      position: { x: src.position.x + 40, y: src.position.y + 40 },
      data: { nodeType: src.data.nodeType, config: { ...src.data.config } },
    };
    set({ nodes: [...get().nodes, copy], selectedId: copy.id });
  },

  copyNode: (id) => {
    const src = get().nodes.find((n) => n.id === id);
    if (src) set({ clipboard: { nodeType: src.data.nodeType, config: { ...src.data.config } } });
  },

  pasteNode: (pos) => {
    const clip = get().clipboard;
    if (!clip) return;
    const node: WFNode = { id: nid(), type: "wf", position: pos, data: { nodeType: clip.nodeType, config: { ...clip.config } } };
    set({ nodes: [...get().nodes, node], selectedId: node.id });
  },

  autoArrange: () => {
    const { nodes, edges } = get();
    const adj: Record<string, string[]> = {};
    const indeg: Record<string, number> = {};
    nodes.forEach((n) => (indeg[n.id] = 0));
    edges.forEach((e) => {
      (adj[e.source] ||= []).push(e.target);
      if (e.target in indeg) indeg[e.target]++;
    });
    const depth: Record<string, number> = {};
    nodes.forEach((n) => (depth[n.id] = 0));
    const q = nodes.filter((n) => indeg[n.id] === 0).map((n) => n.id);
    const seen = new Set(q);
    while (q.length) {
      const u = q.shift()!;
      for (const v of adj[u] || []) {
        depth[v] = Math.max(depth[v], depth[u] + 1);
        if (!seen.has(v)) { seen.add(v); q.push(v); }
      }
    }
    const col: Record<number, string[]> = {};
    nodes.forEach((n) => ((col[depth[n.id]] ||= []).push(n.id)));
    const pos: Record<string, { x: number; y: number }> = {};
    Object.entries(col).forEach(([d, ids]) =>
      ids.forEach((id, i) => (pos[id] = { x: 80 + Number(d) * 270, y: 120 + i * 140 }))
    );
    set({ nodes: nodes.map((n) => ({ ...n, position: pos[n.id] || n.position })) });
  },

  setRunning: (b) => set({ running: b }),
  setNodeRun: (id, r) => set({ runStatus: { ...get().runStatus, [id]: r } }),
  clearRun: () => set({ runStatus: {}, finalOutput: null }),
  setFinalOutput: (s) => set({ finalOutput: s }),
  animateFrom: (sourceId, on) =>
    set({ edges: get().edges.map((e) => (e.source === sourceId ? { ...e, animated: on } : e)) }),
  clearEdgeAnim: () => set({ edges: get().edges.map((e) => ({ ...e, animated: false })) }),

  toWorkflow: () => {
    const { workflowId, name, nodes, edges } = get();
    return {
      id: workflowId,
      name,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.nodeType,
        position: n.position,
        data: n.data.config,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? null,
      })),
    };
  },

  loadWorkflow: (wf) =>
    set({
      workflowId: wf.id,
      name: wf.name,
      selectedId: null,
      runStatus: {},
      finalOutput: null,
      nodes: wf.nodes.map((n) => ({
        id: n.id,
        type: "wf",
        position: n.position || { x: 0, y: 0 },
        data: { nodeType: n.type, config: n.data || {} },
      })),
      edges: wf.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? undefined,
      })),
    }),

  reset: () =>
    set({
      workflowId: "wf_" + Math.random().toString(36).slice(2, 9),
      name: "Untitled workflow",
      selectedId: null,
      runStatus: {},
      finalOutput: null,
      ...starter(),
    }),
}));

export { defByType };
