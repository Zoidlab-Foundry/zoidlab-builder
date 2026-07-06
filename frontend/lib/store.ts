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
