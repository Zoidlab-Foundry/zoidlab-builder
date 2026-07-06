// Node catalog: drives the library palette AND the config panel.
// Adding a node type to the platform starts here (backend nodes.py executes it).

export type FieldType = "text" | "textarea" | "number" | "select" | "slider" | "headers";

export interface Field {
  key: string;
  label: string;
  type: FieldType;
  placeholder?: string;
  default?: any;
  options?: string[];       // for select
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
}

export interface NodeDef {
  type: string;
  label: string;
  category: string;
  accent: string;           // hex used for the node's rail + handles
  glyph: string;            // single-char / emoji mark
  description: string;
  hasInput: boolean;
  outputs: { id: string | null; label?: string; color?: string }[];
  fields: Field[];
}

export const NODE_DEFS: NodeDef[] = [
  {
    type: "start",
    label: "Start",
    category: "Flow",
    accent: "#4fd1c5",
    glyph: "▸",
    description: "Entry point. Carries the trigger payload into the workflow.",
    hasInput: false,
    outputs: [{ id: null }],
    fields: [
      { key: "trigger", label: "Trigger", type: "select", options: ["Manual", "Webhook", "Schedule"], default: "Manual", hint: "How this workflow starts (prototype runs all manually)." },
    ],
  },
  {
    type: "prompt",
    label: "Prompt",
    category: "Prompts",
    accent: "#818cf8",
    glyph: "❝",
    description: "Renders a template with {{variables}} into text for the next node.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "template", label: "Template", type: "textarea", default: "Summarize the following in one sentence:\n\n{{previous.output}}", placeholder: "Write a prompt. Use {{previous.output}}, {{trigger.x}}…" },
    ],
  },
  {
    type: "llm",
    label: "LLM",
    category: "AI Models",
    accent: "#7c5cfc",
    glyph: "✦",
    description: "Calls a model through the Nyquest relay. Input is the upstream text.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "model", label: "Model", type: "select", options: [], default: "claude-sonnet-5", hint: "Loaded live from the Nyquest relay." },
      { key: "system", label: "System prompt", type: "textarea", placeholder: "Optional. You are a helpful assistant…" },
      { key: "prompt", label: "User prompt override", type: "textarea", placeholder: "Optional. Defaults to the upstream node's output." },
      { key: "temperature", label: "Temperature", type: "slider", min: 0, max: 2, step: 0.1, default: 0.7 },
      { key: "max_tokens", label: "Max tokens", type: "number", default: 1024, min: 1, max: 32000 },
    ],
  },
  {
    type: "decision",
    label: "Decision",
    category: "Logic",
    accent: "#f4b860",
    glyph: "◈",
    description: "Branches true / false based on the incoming text.",
    hasInput: true,
    outputs: [
      { id: "true", label: "true", color: "#22c55e" },
      { id: "false", label: "false", color: "#ef4444" },
    ],
    fields: [
      { key: "mode", label: "Condition", type: "select", options: ["contains", "equals", "not_empty"], default: "contains" },
      { key: "value", label: "Value", type: "text", placeholder: "yes", hint: "Compared against the incoming text. Supports {{expressions}}." },
    ],
  },
  {
    type: "http",
    label: "HTTP Request",
    category: "Integrations",
    accent: "#22d3ee",
    glyph: "⇄",
    description: "Calls a REST endpoint. Response becomes this node's output.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "method", label: "Method", type: "select", options: ["GET", "POST", "PUT", "DELETE"], default: "GET" },
      { key: "url", label: "URL", type: "text", placeholder: "https://api.example.com/v1/thing" },
      { key: "headers", label: "Headers", type: "headers" },
      { key: "body", label: "Body", type: "textarea", placeholder: "Optional. Supports {{expressions}}." },
    ],
  },
  {
    type: "end",
    label: "End",
    category: "Flow",
    accent: "#4fd1c5",
    glyph: "■",
    description: "Terminates the workflow and captures the final output.",
    hasInput: true,
    outputs: [],
    fields: [],
  },
];

export const CATEGORIES = ["Flow", "AI Models", "Prompts", "Logic", "Integrations"];

export const defByType = (t: string) => NODE_DEFS.find((d) => d.type === t);

export function defaultData(t: string): Record<string, any> {
  const def = defByType(t);
  const data: Record<string, any> = {};
  def?.fields.forEach((f) => {
    if (f.default !== undefined) data[f.key] = f.default;
  });
  return data;
}
