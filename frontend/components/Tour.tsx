"use client";
import { useEffect, useLayoutEffect, useState } from "react";
import { TOUR_STEPS } from "../lib/tour";

const CARD_W = 320;

export default function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = TOUR_STEPS[i];
  const last = i === TOUR_STEPS.length - 1;

  useEffect(() => {
    if (open) setI(0);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const measure = () => {
      const el = step.target ? (document.querySelector(step.target) as HTMLElement | null) : null;
      setRect(el ? el.getBoundingClientRect() : null);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [open, i, step]);

  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" || e.key === "Enter") setI((n) => Math.min(n + 1, TOUR_STEPS.length - 1));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(n - 1, 0));
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open, onClose]);

  if (!open) return null;

  const pad = 8;
  const spot = rect
    ? { left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }
    : null;

  // callout placement
  let cardStyle: React.CSSProperties = {};
  if (!spot || step.placement === "center") {
    cardStyle = { left: "50%", top: "42%", transform: "translate(-50%,-50%)" };
  } else {
    const p = step.placement || "bottom";
    const cx = Math.min(Math.max(spot.left + spot.width / 2 - CARD_W / 2, 16), window.innerWidth - CARD_W - 16);
    if (p === "bottom") cardStyle = { left: cx, top: spot.top + spot.height + 14 };
    else if (p === "top") cardStyle = { left: cx, top: Math.max(spot.top - 180, 16) };
    else if (p === "right") cardStyle = { left: Math.min(spot.left + spot.width + 14, window.innerWidth - CARD_W - 16), top: Math.max(spot.top, 16) };
    else cardStyle = { left: Math.max(spot.left - CARD_W - 14, 16), top: Math.max(spot.top, 16) };
  }

  const next = () => (last ? onClose() : setI((n) => n + 1));

  return (
    <div className="fixed inset-0 z-[60]">
      {/* click-catcher so the app can't be used mid-tour */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* spotlight — huge box-shadow dims everything except the target */}
      {spot ? (
        <div
          className="pointer-events-none absolute rounded-xl transition-all duration-300"
          style={{
            left: spot.left, top: spot.top, width: spot.width, height: spot.height,
            boxShadow: "0 0 0 9999px rgba(10,11,16,.74)",
            outline: "2px solid #4fd1c5", outlineOffset: 2,
          }}
        />
      ) : (
        <div className="pointer-events-none absolute inset-0" style={{ background: "rgba(10,11,16,.74)" }} />
      )}

      {/* callout card */}
      <div className="absolute w-[320px] rounded-2xl border border-cy/30 bg-panel p-4 shadow-2xl" style={cardStyle}>
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[10px] font-semibold tracking-wider text-cy">
            {i + 1} / {TOUR_STEPS.length}
          </span>
        </div>
        <div className="mb-1.5 text-[15px] font-semibold text-ink">{step.title}</div>
        <p className="mb-4 text-[13px] leading-relaxed text-dim">{step.body}</p>

        <div className="flex items-center gap-1.5">
          {TOUR_STEPS.map((_, k) => (
            <span key={k} className="h-1.5 rounded-full transition-all" style={{ width: k === i ? 16 : 6, background: k === i ? "#4fd1c5" : "#3a3d4c" }} />
          ))}
          <div className="ml-auto flex items-center gap-2">
            {i > 0 && (
              <button onClick={() => setI((n) => n - 1)} className="rounded-lg px-3 py-1.5 text-[12px] text-dim hover:text-ink">
                Back
              </button>
            )}
            <button onClick={next} className="rounded-lg bg-cy px-4 py-1.5 text-[12px] font-semibold text-bg hover:opacity-90">
              {last ? "Done" : "Next"}
            </button>
          </div>
        </div>

        {!last && (
          <button onClick={onClose} className="absolute right-3 top-3 text-[11px] text-dim/70 hover:text-ink">
            Skip
          </button>
        )}
      </div>
    </div>
  );
}
