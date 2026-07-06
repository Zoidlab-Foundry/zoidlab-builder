"use client";
import { useEffect, useRef, useState } from "react";

// Extensible menu model — add an action = add an item. Items with a `submenu`
// expand to the side on hover. A `{ divider: true }` renders a separator.
export type MenuItem =
  | { divider: true }
  | {
      label: string;
      icon?: string;
      shortcut?: string;
      danger?: boolean;
      disabled?: boolean;
      submenu?: MenuItem[];
      onClick?: () => void;
    };

export interface MenuState {
  x: number;
  y: number;
  items: MenuItem[];
}

export default function ContextMenu({ menu, onClose }: { menu: MenuState | null; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [openSub, setOpenSub] = useState<number | null>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [menu, onClose]);

  if (!menu) return null;

  // clamp to viewport
  const x = Math.min(menu.x, window.innerWidth - 230);
  const y = Math.min(menu.y, window.innerHeight - 40 - menu.items.length * 32);

  const renderItems = (items: MenuItem[], nested = false) => (
    <div
      className={`min-w-[190px] overflow-visible rounded-xl border border-line bg-panel py-1 shadow-2xl ${nested ? "" : ""}`}
      style={{ boxShadow: "0 12px 40px rgba(0,0,0,.5)" }}
    >
      {items.map((it, i) => {
        if ("divider" in it) return <div key={i} className="my-1 h-px bg-line" />;
        const hasSub = !!it.submenu?.length;
        return (
          <div key={i} className="relative" onMouseEnter={() => nested || setOpenSub(hasSub ? i : null)}>
            <button
              disabled={it.disabled}
              onClick={() => {
                if (it.disabled) return;
                if (hasSub) return;
                it.onClick?.();
                onClose();
              }}
              className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12.5px] transition-colors
                ${it.disabled ? "cursor-default text-dim/40" : it.danger ? "text-bad hover:bg-bad/10" : "text-ink hover:bg-line"}`}
            >
              <span className="w-4 text-center text-[13px] opacity-80">{it.icon || ""}</span>
              <span className="flex-1">{it.label}</span>
              {it.shortcut && <span className="text-[10px] tabular-nums text-dim/60">{it.shortcut}</span>}
              {hasSub && <span className="text-[10px] text-dim">▸</span>}
            </button>
            {hasSub && openSub === i && (
              <div className="absolute left-full top-0 -ml-1 pl-1">{renderItems(it.submenu!, true)}</div>
            )}
          </div>
        );
      })}
    </div>
  );

  return (
    <div ref={ref} className="fixed z-50" style={{ left: x, top: y }}>
      {renderItems(menu.items)}
    </div>
  );
}
