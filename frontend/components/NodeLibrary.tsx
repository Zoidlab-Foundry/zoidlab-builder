"use client";
import { NODE_DEFS, CATEGORIES } from "../lib/catalog";

export default function NodeLibrary() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-panel2">
      <div className="border-b border-line px-4 py-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-dim">Node Library</div>
        <div className="mt-1 text-[11px] text-dim/70">Drag onto the canvas</div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {CATEGORIES.map((cat) => {
          const defs = NODE_DEFS.filter((d) => d.category === cat);
          if (!defs.length) return null;
          return (
            <div key={cat} className="mb-4">
              <div className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-dim/70">{cat}</div>
              <div className="flex flex-col gap-1.5">
                {defs.map((d) => (
                  <div
                    key={d.type}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("application/zoidlab", d.type);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    className="group flex cursor-grab items-center gap-2.5 rounded-lg border border-line bg-panel px-2.5 py-2 transition-colors hover:border-cy/50 active:cursor-grabbing"
                  >
                    <span
                      className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-[13px]"
                      style={{ background: `${d.accent}22`, color: d.accent }}
                    >
                      {d.glyph}
                    </span>
                    <div className="min-w-0">
                      <div className="text-[12px] font-medium leading-tight text-ink">{d.label}</div>
                      <div className="truncate text-[10px] leading-tight text-dim/70">{d.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
