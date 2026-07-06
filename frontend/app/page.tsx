"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useReactFlow,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useStore } from "../lib/store";
import { fetchModels, saveWorkflow, runWorkflow } from "../lib/api";
import { defByType } from "../lib/catalog";
import WorkflowNode from "../components/WorkflowNode";
import NodeLibrary from "../components/NodeLibrary";
import ConfigPanel from "../components/ConfigPanel";

const nodeTypes: NodeTypes = { wf: WorkflowNode };

function Builder() {
  const s = useStore();
  const { screenToFlowPosition } = useReactFlow();
  const wrap = useRef<HTMLDivElement>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    fetchModels().then((m) => s.setModels(m));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2600);
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/zoidlab");
      if (!type) return;
      const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      s.addNode(type, { x: pos.x - 105, y: pos.y - 24 });
    },
    [screenToFlowPosition, s]
  );

  const onSave = async () => {
    try {
      await saveWorkflow(s.toWorkflow());
      flash("Workflow saved");
    } catch {
      flash("Save failed");
    }
  };

  const onRun = async () => {
    if (s.running) return;
    s.clearRun();
    s.clearEdgeAnim();
    s.setRunning(true);
    const wf = s.toWorkflow();
    try {
      await runWorkflow(wf, {}, (ev) => {
        if (ev.type === "node" && ev.nodeId) {
          if (ev.status === "running") s.animateFrom(ev.nodeId, true);
          s.setNodeRun(ev.nodeId, {
            status: ev.status!,
            output: ev.output,
            ms: ev.ms,
            tokens: ev.tokens,
            meta: ev.meta,
            error: ev.error,
          });
        } else if (ev.type === "done") {
          s.setFinalOutput(ev.output ?? null);
        } else if (ev.type === "error") {
          flash(ev.error || "Run error");
        }
      });
    } catch (e: any) {
      flash("Run failed: " + (e?.message || "unknown"));
    } finally {
      s.setRunning(false);
      s.clearEdgeAnim();
    }
  };

  return (
    <div className="flex h-screen w-screen flex-col bg-bg">
      {/* top bar */}
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line bg-panel2 px-4">
        <div className="flex items-center gap-2 text-[15px] font-light tracking-[0.2em] text-ink">
          ZOID<span className="font-bold text-cy">LAB</span>
          <span className="ml-1 rounded bg-vi/15 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-ind">BUILDER</span>
        </div>
        <input
          value={s.name}
          onChange={(e) => s.setName(e.target.value)}
          className="w-64 rounded-lg border border-transparent bg-transparent px-2 py-1 text-[13px] text-ink outline-none hover:border-line focus:border-cy"
        />
        <div className="ml-auto flex items-center gap-2">
          <span className="mr-1 text-[11px] text-dim">{s.models.length ? `${s.models.length} models` : "connecting…"}</span>
          <button onClick={onSave} className="rounded-lg border border-line px-4 py-1.5 text-[12px] font-medium text-dim hover:border-cy hover:text-ink">
            Save
          </button>
          <button
            onClick={onRun}
            disabled={s.running}
            className="rounded-lg bg-cy px-5 py-1.5 text-[12px] font-semibold text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {s.running ? "Running…" : "▸ Run"}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <NodeLibrary />

        <div className="relative min-w-0 flex-1" ref={wrap} onDrop={onDrop} onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}>
          <ReactFlow
            nodes={s.nodes}
            edges={s.edges}
            nodeTypes={nodeTypes}
            onNodesChange={s.onNodesChange}
            onEdgesChange={s.onEdgesChange}
            onConnect={s.onConnect}
            onNodeClick={(_, n) => s.select(n.id)}
            onPaneClick={() => s.select(null)}
            defaultEdgeOptions={{ style: { stroke: "#3a3d4c", strokeWidth: 2 } }}
            fitView
            proOptions={{ hideAttribution: true }}
            minZoom={0.2}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#2a2d3a" />
            <Controls className="!bg-panel" />
            <MiniMap
              pannable zoomable
              nodeColor={(n) => defByType((n.data as any)?.nodeType)?.accent || "#3a3d4c"}
              maskColor="rgba(20,22,31,0.7)"
            />
          </ReactFlow>

          {s.finalOutput != null && (
            <div className="absolute bottom-4 left-4 right-4 z-10 max-h-40 overflow-auto rounded-xl border border-cy/30 bg-panel/95 p-3 backdrop-blur">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-cy">Workflow output</div>
              <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-ink/90">{s.finalOutput}</pre>
            </div>
          )}

          {toast && (
            <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-full border border-line bg-panel px-4 py-2 text-[12px] text-ink shadow-lg">
              {toast}
            </div>
          )}
        </div>

        <ConfigPanel />
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <ReactFlowProvider>
      <Builder />
    </ReactFlowProvider>
  );
}
