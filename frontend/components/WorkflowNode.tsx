"use client";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { defByType } from "../lib/catalog";
import { useStore } from "../lib/store";

const isImageUrl = (v: any) =>
  typeof v === "string" &&
  /^https?:\/\/\S+/.test(v) &&
  (/\.(png|jpe?g|webp|gif|avif)(\?|$)/i.test(v) || /\/image\/|imagen/i.test(v));

const isAudioUrl = (v: any) =>
  typeof v === "string" &&
  /^https?:\/\/\S+/.test(v) &&
  (/\.(mp3|wav|ogg|m4a|flac)(\?|$)/i.test(v) || /\/(audio|music)\//i.test(v));

const isVideoUrl = (v: any) =>
  typeof v === "string" &&
  /^https?:\/\/\S+/.test(v) &&
  (/\.(mp4|webm|mov|m4v)(\?|$)/i.test(v) || /\/video\//i.test(v));

const STATUS_RING: Record<string, string> = {
  running: "#f4b860",   // yellow — active
  complete: "#22c55e",  // green — done
  error: "#ef4444",     // red — failed
};

export default function WorkflowNode({ id, data, selected }: NodeProps) {
  const nodeType = (data as any).nodeType as string;
  const config = (data as any).config as Record<string, any>;
  const def = defByType(nodeType);
  const run = useStore((s) => s.runStatus[id]);
  if (!def) return null;

  const ring = run ? STATUS_RING[run.status] : selected ? def.accent : "#2a2d3a";
  const pulsing = run?.status === "running";

  // Switch/Classifier derive their output handles from configured cases/labels.
  const parseCases = (v: any) => String(v || "").split("\n").map((s) => s.trim()).filter(Boolean);
  const outs = def.dynamicOutputs
    ? [...parseCases(config.cases ?? config.labels).map((v) => ({ id: v, label: v, color: "#818cf8" })), { id: "default", label: "default", color: "#9aa0b0" }]
    : def.outputs;

  // a compact subtitle from the most salient config field
  const subtitle =
    nodeType === "llm" ? config.model || "model" :
    nodeType === "model" ? `${config.var || "model"} = ${config.model || "auto"}` :
    nodeType === "summarizer" ? `${config.model || "model"} · ${config.length || "short"}` :
    nodeType === "decision" ? `${config.mode || "contains"} "${config.value || ""}"` :
    nodeType === "switch" ? `${parseCases(config.cases).length} cases` :
    nodeType === "classifier" ? `${parseCases(config.labels).length} labels` :
    nodeType === "translator" ? `→ ${config.language || "Spanish"}` :
    nodeType === "extractor" ? `${parseCases(config.fields).length} fields` :
    nodeType === "jsonpath" ? (config.path || "(root)") :
    nodeType === "delay" ? `${config.seconds ?? 2}s` :
    nodeType === "merge" ? (config.mode || "combine") :
    nodeType === "approval" ? "human decision" :
    nodeType === "slack" || nodeType === "discord" ? (config.webhook_url ? "webhook set" : "dry-run") :
    nodeType === "foreach" ? `over ${config.over || "list"}` :
    nodeType === "variable" ? `${config.name || "name"} =` :
    nodeType === "nyquest_image" ? `${config.model || "imagen"} · ${config.aspect_ratio || "1:1"}` :
    nodeType === "nyquest_speech" ? `${config.model || "tts"}${config.voice ? " · " + config.voice : ""}` :
    nodeType === "nyquest_music" ? (config.model || "lyria") :
    nodeType === "nyquest_agent" ? `${config.model || "auto"} · ≤${config.max_steps ?? 6} steps` :
    nodeType === "nyquest_video" ? `${config.model || "veo"} · ${config.aspect_ratio || "16:9"}` :
    nodeType === "guardrail" ? "allow / block" :
    nodeType === "datastore" ? `${config.op || "get"} ${config.key || "key"}` :
    nodeType === "email" ? `to ${config.to || "…"}` :
    nodeType === "webhook" ? (config.path || "/hook") :
    nodeType === "http" ? `${config.method || "GET"} ${config.url ? "·" : ""} ${(config.url || "").slice(0, 22)}` :
    nodeType === "prompt" ? (config.template || "").slice(0, 40) + "…" :
    def.description.slice(0, 40);

  const minHeight = outs.length > 2 ? 30 + outs.length * 22 : undefined;

  return (
    <div
      style={{ borderColor: ring, boxShadow: pulsing ? `0 0 0 3px ${ring}33` : selected ? `0 0 0 2px ${def.accent}44` : "none", minHeight }}
      className="relative w-[210px] rounded-xl border bg-panel transition-shadow"
    >
      {def.hasInput && (
        <Handle type="target" position={Position.Left} style={{ background: def.accent }} />
      )}

      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <span
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-[15px]"
          style={{ background: `${def.accent}22`, color: def.accent }}
        >
          {def.glyph}
        </span>
        <div className="min-w-0">
          <div className="text-[13px] font-semibold leading-tight text-ink">{def.label}</div>
          <div className="truncate text-[10px] leading-tight text-dim">{subtitle}</div>
        </div>
        {run && (
          <span
            className="ml-auto h-2 w-2 shrink-0 rounded-full"
            style={{ background: STATUS_RING[run.status] || "#2a2d3a" }}
          />
        )}
      </div>

      {run?.status === "complete" && (run.meta || run.output) && (
        <div className="border-t border-line px-3 py-1.5">
          {run.meta && <div className="text-[9px] uppercase tracking-wider text-cy">{run.meta}</div>}
          {run.output && isImageUrl(run.output) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={run.output} alt="generated" className="mt-1 w-full rounded-md border border-line" />
          ) : run.output && isVideoUrl(run.output) ? (
            <video controls preload="metadata" src={run.output} className="nodrag mt-1 w-full rounded-md border border-line" style={{ background: "#000" }} />
          ) : run.output && isAudioUrl(run.output) ? (
            <audio controls src={run.output} className="nodrag mt-1 w-full" style={{ height: 32 }} />
          ) : run.output ? (
            <div className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-dim">{run.output}</div>
          ) : null}
        </div>
      )}
      {run?.status === "error" && (
        <div className="border-t border-line px-3 py-1.5 text-[10px] leading-snug text-bad">
          {run.error}
        </div>
      )}

      {/* outputs */}
      {outs.length <= 1 &&
        outs.map((o) => (
          <Handle key={o.id || "out"} type="source" position={Position.Right} style={{ background: def.accent }} />
        ))}
      {outs.length > 1 &&
        outs.map((o, i) => (
          <Handle
            key={o.id}
            id={o.id || undefined}
            type="source"
            position={Position.Right}
            style={{ top: 20 + i * 22, background: o.color || def.accent }}
          >
            <span className="pointer-events-none absolute right-3 -top-1.5 text-[9px]" style={{ color: o.color }}>
              {o.label}
            </span>
          </Handle>
        ))}
    </div>
  );
}
