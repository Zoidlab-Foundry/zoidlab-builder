"use client";
import { useStore } from "../lib/store";
import { defByType, type Field } from "../lib/catalog";

export default function ConfigPanel() {
  const selectedId = useStore((s) => s.selectedId);
  const node = useStore((s) => s.nodes.find((n) => n.id === s.selectedId));
  const models = useStore((s) => s.models);
  const run = useStore((s) => (selectedId ? s.runStatus[selectedId] : undefined));
  const updateConfig = useStore((s) => s.updateConfig);
  const deleteNode = useStore((s) => s.deleteNode);

  if (!node) {
    return (
      <aside data-tour="config" className="flex w-80 shrink-0 flex-col border-l border-line bg-panel2">
        <div className="flex flex-1 items-center justify-center p-8 text-center text-[12px] leading-relaxed text-dim/70">
          Select a node to configure it.<br />Drag from the library to add nodes, then connect the handles.
        </div>
      </aside>
    );
  }

  const def = defByType(node.data.nodeType)!;
  const cfg = node.data.config;

  const renderField = (f: Field) => {
    const val = cfg[f.key] ?? f.default ?? "";
    const common = "w-full rounded-lg border border-line bg-bg px-3 py-2 text-[13px] text-ink outline-none focus:border-cy";

    if (f.type === "select") {
      let opts: { value: string; label: string }[];
      if (f.key === "model") {
        const base = models.length ? models : (f.options || []);
        // "From Model node" lets an AI node inherit whatever a Model node selected.
        const specials = node.data.nodeType === "model" ? [] : [{ value: "{{vars.model}}", label: "↳ From Model node" }];
        opts = [
          ...specials,
          ...base.map((m) => ({ value: m, label: m === "auto" ? "Auto — Nyquest routes" : m })),
        ];
      } else {
        opts = (f.options || []).map((o) => ({ value: o, label: o }));
      }
      const known = opts.some((o) => o.value === val);
      return (
        <select className={common} value={val} onChange={(e) => updateConfig(node.id, { [f.key]: e.target.value })}>
          {!known && val ? <option value={val}>{val}</option> : null}
          {opts.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      );
    }
    if (f.type === "textarea") {
      return (
        <textarea
          className={`${common} min-h-[92px] resize-y font-mono text-[12px] leading-relaxed`}
          placeholder={f.placeholder}
          value={val}
          onChange={(e) => updateConfig(node.id, { [f.key]: e.target.value })}
        />
      );
    }
    if (f.type === "number") {
      return (
        <input
          type="number" className={common} value={val} min={f.min} max={f.max}
          onChange={(e) => updateConfig(node.id, { [f.key]: Number(e.target.value) })}
        />
      );
    }
    if (f.type === "slider") {
      return (
        <div className="flex items-center gap-3">
          <input
            type="range" min={f.min} max={f.max} step={f.step} value={val}
            onChange={(e) => updateConfig(node.id, { [f.key]: Number(e.target.value) })}
            className="flex-1 accent-cy"
          />
          <span className="w-9 text-right font-mono text-[12px] tabular-nums text-cy">{Number(val).toFixed(1)}</span>
        </div>
      );
    }
    if (f.type === "headers") {
      const text = typeof val === "object" ? JSON.stringify(val, null, 2) : val || "";
      return (
        <textarea
          className={`${common} min-h-[70px] resize-y font-mono text-[12px]`}
          placeholder={'{ "Authorization": "Bearer …" }'}
          value={text}
          onChange={(e) => {
            try { updateConfig(node.id, { [f.key]: JSON.parse(e.target.value || "{}") }); }
            catch { updateConfig(node.id, { [f.key]: e.target.value }); }
          }}
        />
      );
    }
    return (
      <input className={common} placeholder={f.placeholder} value={val}
        onChange={(e) => updateConfig(node.id, { [f.key]: e.target.value })} />
    );
  };

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-line bg-panel2">
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <span className="grid h-7 w-7 place-items-center rounded-lg text-[15px]" style={{ background: `${def.accent}22`, color: def.accent }}>
          {def.glyph}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-ink">{def.label}</div>
          <div className="truncate text-[10px] text-dim/70">{node.id}</div>
        </div>
        {node.data.nodeType !== "start" && node.data.nodeType !== "end" && (
          <button onClick={() => deleteNode(node.id)} className="rounded-md px-2 py-1 text-[11px] text-dim hover:bg-line hover:text-bad" title="Delete node">✕</button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <p className="mb-4 text-[11px] leading-relaxed text-dim">{def.description}</p>
        <div className="flex flex-col gap-4">
          {def.fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">{f.label}</label>
              {renderField(f)}
              {f.hint && <div className="mt-1 text-[10px] leading-snug text-dim/60">{f.hint}</div>}
            </div>
          ))}
          {!def.fields.length && <div className="text-[12px] text-dim/60">No configuration for this node.</div>}
        </div>

        {run && (
          <div className="mt-6 rounded-lg border border-line bg-panel p-3">
            <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider">
              <span className="text-dim">Last run</span>
              <span style={{ color: run.status === "error" ? "#ef4444" : run.status === "complete" ? "#22c55e" : "#f4b860" }}>
                {run.status}{run.ms != null ? ` · ${run.ms}ms` : ""}{run.tokens ? ` · ${run.tokens} tok` : ""}
              </span>
            </div>
            <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink/90">
              {run.error || run.output || "(no output)"}
            </pre>
          </div>
        )}
      </div>
    </aside>
  );
}
