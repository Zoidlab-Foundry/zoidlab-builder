"use client";
import { TEMPLATES, type Template } from "../lib/templates";

export default function NewWorkflowModal({
  open,
  onClose,
  onBlank,
  onTemplate,
}: {
  open: boolean;
  onClose: () => void;
  onBlank: () => void;
  onTemplate: (t: Template) => void;
}) {
  if (!open) return null;

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-16 w-[680px] max-w-[94%] rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="text-[14px] font-semibold text-ink">New workflow</span>
          <span className="text-[12px] text-dim">— start blank or from a template</span>
          <button onClick={onClose} className="ml-auto rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="grid max-h-[64vh] grid-cols-2 gap-3 overflow-y-auto p-5">
          <button
            onClick={onBlank}
            className="flex flex-col items-start gap-2 rounded-xl border border-dashed border-line bg-panel2 p-4 text-left transition-colors hover:border-cy/60"
          >
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-line text-[16px] text-dim">＋</span>
            <div>
              <div className="text-[13px] font-semibold text-ink">Blank workflow</div>
              <div className="mt-0.5 text-[11px] leading-snug text-dim">Start from an empty canvas with a Start and End node.</div>
            </div>
          </button>

          {TEMPLATES.map((t) => (
            <button
              key={t.slug}
              onClick={() => onTemplate(t)}
              className="group flex flex-col items-start gap-2 rounded-xl border border-line bg-panel2 p-4 text-left transition-colors hover:border-cy/60"
            >
              <span className="grid h-8 w-8 place-items-center rounded-lg text-[16px]" style={{ background: `${t.accent}22`, color: t.accent }}>
                {t.glyph}
              </span>
              <div>
                <div className="text-[13px] font-semibold text-ink">{t.name}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-dim">{t.description}</div>
              </div>
              <span className="mt-1 text-[10px] font-medium text-dim/70">{t.nodes.length} nodes · runnable</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
