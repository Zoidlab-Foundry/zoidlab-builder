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
  dynamicOutputs?: boolean;  // outputs derived from config (e.g. Switch cases)
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
      { key: "fallback", label: "Fallback model", type: "select", options: [], hint: "Optional. Used if the primary model errors." },
      { key: "timeout_s", label: "Timeout (s)", type: "number", min: 0, max: 600, hint: "0 = no limit." },
      { key: "retries", label: "Retries", type: "number", default: 0, min: 0, max: 5, hint: "Retry on failure, with backoff." },
    ],
  },
  {
    type: "model",
    label: "Model",
    category: "AI Models",
    accent: "#7c5cfc",
    glyph: "◇",
    description: "Picks a model (or Auto). Downstream AI nodes can use {{vars.model}}.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "model", label: "Model", type: "select", options: [], default: "auto", hint: "Auto lets the Nyquest relay pick the best model per request." },
      { key: "var", label: "Store as", type: "text", default: "model", hint: "Referenced downstream as {{vars.<name>}} — e.g. an LLM node's model." },
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
      { key: "timeout_s", label: "Timeout (s)", type: "number", min: 0, max: 600, hint: "0 = no limit." },
      { key: "retries", label: "Retries", type: "number", default: 0, min: 0, max: 5, hint: "Retry on failure, with backoff." },
    ],
  },
  {
    type: "rag_query",
    label: "RAG Query",
    category: "Foundry",
    accent: "#22d3ee",
    glyph: "📚",
    description: "Ask a deployed ZoidLab RAG knowledge base. Returns a grounded, cited answer.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "endpoint", label: "RAG endpoint URL", type: "text", placeholder: "https://rag.zoidlab.ai/api/rag-endpoint/<token>/query", hint: "From a knowledge base's Deploy tab." },
      { key: "question", label: "Question", type: "textarea", default: "{{previous.output}}", placeholder: "Supports {{expressions}}. Empty = the incoming text." },
    ],
  },
  {
    type: "memory_recall",
    label: "Memory Recall",
    category: "Foundry",
    accent: "#818cf8",
    glyph: "🧠",
    description: "Recall relevant memories from a deployed ZoidLab MemoryMaker store.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "endpoint", label: "Recall endpoint URL", type: "text", placeholder: "https://memorymaker.zoidlab.ai/api/memory-endpoint/<token>/recall", hint: "From a store's Deploy tab." },
      { key: "query", label: "Query", type: "textarea", default: "{{previous.output}}", placeholder: "Supports {{expressions}}. Empty = the incoming text." },
    ],
  },
  {
    type: "prompt_run",
    label: "Prompt Run",
    category: "Foundry",
    accent: "#22d3ee",
    glyph: "❝",
    description: "Run a deployed ZoidLab Prompter prompt with variables. Returns the model output.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "endpoint", label: "Prompt endpoint URL", type: "text", placeholder: "https://prompter.zoidlab.ai/api/prompt-endpoint/<token>/run", hint: "From a prompt's Deploy tab." },
      { key: "variables", label: "Variables (JSON)", type: "textarea", default: "{}", placeholder: '{"customer_message": "{{previous.output}}"}' },
    ],
  },
  {
    type: "merge",
    label: "Merge",
    category: "Logic",
    accent: "#f4b860",
    glyph: "⋈",
    description: "Waits for every incoming branch, then combines their outputs.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "mode", label: "Mode", type: "select", options: ["combine", "collect"], default: "combine", hint: "combine = join text; collect = JSON array." },
      { key: "separator", label: "Separator", type: "text", default: "\\n\\n", hint: "For combine mode." },
    ],
  },
  {
    type: "approval",
    label: "Approval",
    category: "Human",
    accent: "#f4b860",
    glyph: "⏸",
    description: "Pauses for a human decision, then routes approved / rejected.",
    hasInput: true,
    outputs: [
      { id: "approved", label: "approved", color: "#22c55e" },
      { id: "rejected", label: "rejected", color: "#ef4444" },
    ],
    fields: [
      { key: "message", label: "Prompt", type: "textarea", default: "Approve to continue?", hint: "Shown to the approver. Supports {{expressions}}." },
      { key: "timeout_s", label: "Wait timeout (s)", type: "number", default: 300, min: 5, max: 3600 },
      { key: "on_timeout", label: "On timeout", type: "select", options: ["reject", "approve"], default: "reject" },
      { key: "auto", label: "Unattended runs", type: "select", options: ["reject", "approve"], default: "reject", hint: "What webhook/scheduled runs do (no human present)." },
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
  {
    type: "webhook",
    label: "Webhook",
    category: "Flow",
    accent: "#4fd1c5",
    glyph: "⇥",
    description: "Inbound trigger. Starts the workflow with the request payload. The public webhook URL is generated for you when you deploy (Deploy → webhook) — it isn't configurable here.",
    hasInput: false,
    outputs: [{ id: null }],
    fields: [],
  },
  {
    type: "summarizer",
    label: "Summarizer",
    category: "AI Utilities",
    accent: "#7c5cfc",
    glyph: "❡",
    description: "Condenses the incoming text with a model.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-sonnet-5", hint: "From the Nyquest relay." },
      { key: "length", label: "Length", type: "select", options: ["one line", "short", "detailed"], default: "short" },
    ],
  },
  {
    type: "switch",
    label: "Switch",
    category: "Logic",
    accent: "#f4b860",
    glyph: "⋔",
    description: "Multi-way branch. Routes to the first matching case, else default.",
    hasInput: true,
    dynamicOutputs: true,
    outputs: [],
    fields: [
      { key: "mode", label: "Match", type: "select", options: ["contains", "equals"], default: "contains" },
      { key: "cases", label: "Cases (one per line)", type: "textarea", default: "billing\nbug\nsales", hint: "Each line becomes an output handle. A 'default' handle catches the rest." },
    ],
  },
  {
    type: "foreach",
    label: "For Each",
    category: "Logic",
    accent: "#f4b860",
    glyph: "⟳",
    description: "Runs a prompt over each item in a list and collects the results.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "over", label: "List", type: "text", default: "{{previous.output}}", hint: "An expression resolving to a JSON array (or newline list)." },
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-haiku-4.5" },
      { key: "prompt", label: "Per-item prompt", type: "textarea", default: "Process this item: {{item}}", hint: "Use {{item}} for the current element." },
      { key: "max_tokens", label: "Max tokens / item", type: "number", default: 300, min: 1, max: 4000 },
    ],
  },
  {
    type: "variable",
    label: "Variable",
    category: "Data",
    accent: "#818cf8",
    glyph: "𝑥",
    description: "Sets a variable other nodes can read via {{vars.name}}.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "name", label: "Name", type: "text", placeholder: "customerName" },
      { key: "value", label: "Value", type: "textarea", default: "{{previous.output}}", hint: "Supports {{expressions}}." },
    ],
  },
  {
    type: "classifier",
    label: "Classifier",
    category: "AI Utilities",
    accent: "#7c5cfc",
    glyph: "◎",
    description: "Classifies the input and routes to the matching label's output.",
    hasInput: true,
    dynamicOutputs: true,
    outputs: [],
    fields: [
      { key: "labels", label: "Labels (one per line)", type: "textarea", default: "positive\nnegative", hint: "Each label becomes an output handle, plus a 'default' catch-all." },
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-haiku-4.5" },
      { key: "prompt", label: "Input override", type: "textarea", placeholder: "Optional. Defaults to the upstream node's output." },
    ],
  },
  {
    type: "translator",
    label: "Translator",
    category: "AI Utilities",
    accent: "#7c5cfc",
    glyph: "文",
    description: "Translates the incoming text into a target language.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "language", label: "Target language", type: "text", default: "Spanish" },
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-haiku-4.5" },
    ],
  },
  {
    type: "extractor",
    label: "Extractor",
    category: "AI Utilities",
    accent: "#7c5cfc",
    glyph: "⟐",
    description: "Pulls structured fields out of unstructured text as JSON.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "fields", label: "Fields (one per line)", type: "textarea", default: "name\ndate\namount", hint: "name: optional description — each becomes a JSON key." },
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-haiku-4.5" },
    ],
  },
  {
    type: "jsonpath",
    label: "JSON Path",
    category: "Data",
    accent: "#818cf8",
    glyph: "{}",
    description: "Extracts a field from JSON input via a dot path (a.b.0.c).",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "path", label: "Path", type: "text", placeholder: "user.email", hint: "Dot-separated keys; numbers index arrays. Empty = whole object." },
    ],
  },
  {
    type: "delay",
    label: "Delay",
    category: "Logic",
    accent: "#f4b860",
    glyph: "◔",
    description: "Pauses the flow before continuing (max 120s).",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "seconds", label: "Seconds", type: "number", default: 2, min: 0, max: 120 },
    ],
  },
  {
    type: "slack",
    label: "Slack",
    category: "Integrations",
    accent: "#22d3ee",
    glyph: "＃",
    description: "Posts a message to a Slack channel via incoming webhook.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "webhook_url", label: "Webhook URL", type: "text", placeholder: "{{secrets.SLACK_WEBHOOK}}", hint: "Store it in ⚿ Secrets and reference it. Empty = dry-run." },
      { key: "message", label: "Message", type: "textarea", default: "{{previous.output}}" },
    ],
  },
  {
    type: "discord",
    label: "Discord",
    category: "Integrations",
    accent: "#22d3ee",
    glyph: "❖",
    description: "Posts a message to a Discord channel via webhook.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "webhook_url", label: "Webhook URL", type: "text", placeholder: "{{secrets.DISCORD_WEBHOOK}}", hint: "Store it in ⚿ Secrets and reference it. Empty = dry-run." },
      { key: "message", label: "Message", type: "textarea", default: "{{previous.output}}" },
    ],
  },
  {
    type: "nyquest_image",
    label: "Image",
    category: "Nyquest",
    accent: "#2dd4bf",
    glyph: "✲",
    description: "Generates an image from a prompt via Nyquest (Imagen). Output is the image URL.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "prompt", label: "Prompt", type: "textarea", default: "{{previous.output}}", placeholder: "A teal robot logo, flat vector on dark…", hint: "Supports {{expressions}}. Defaults to the upstream output." },
      { key: "model", label: "Model", type: "select", options: [
        "imagen-4.0-fast-generate-001",
        "imagen-4.0-generate-001",
        "imagen-4.0-ultra-generate-001",
        "google/gemini-2.5-flash-image",
      ], default: "imagen-4.0-fast-generate-001", hint: "Native Nyquest image models. Billed to your Nyquest wallet." },
      { key: "aspect_ratio", label: "Aspect ratio", type: "select", options: ["1:1", "16:9", "9:16", "4:3", "3:4"], default: "1:1" },
      { key: "timeout_s", label: "Timeout (s)", type: "number", default: 120, min: 0, max: 300, hint: "0 = no limit." },
      { key: "retries", label: "Retries", type: "number", default: 0, min: 0, max: 3, hint: "Retry on failure, with backoff." },
    ],
  },
  {
    type: "nyquest_speech",
    label: "Speech",
    category: "Nyquest",
    accent: "#2dd4bf",
    glyph: "🔊",
    description: "Text-to-speech via Nyquest (Gemini / OpenAI voices). Output is the audio URL.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "text", label: "Text", type: "textarea", default: "{{previous.output}}", placeholder: "The words to speak…", hint: "Supports {{expressions}}. Defaults to the upstream output." },
      { key: "model", label: "Model", type: "select", options: [
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
        "openai/gpt-audio-mini",
        "openai/gpt-audio",
      ], default: "gemini-2.5-flash-preview-tts", hint: "Native Nyquest TTS models. Billed to your Nyquest wallet." },
      { key: "voice", label: "Voice", type: "select", options: [
        "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda",
      ], default: "Kore", hint: "Gemini voices. Leave as-is for OpenAI models (they use their own default)." },
      { key: "timeout_s", label: "Timeout (s)", type: "number", default: 150, min: 0, max: 300, hint: "0 = no limit." },
      { key: "retries", label: "Retries", type: "number", default: 0, min: 0, max: 3 },
    ],
  },
  {
    type: "nyquest_music",
    label: "Music",
    category: "Nyquest",
    accent: "#2dd4bf",
    glyph: "♪",
    description: "Generates an instrumental clip from a prompt via Nyquest (Google Lyria). Output is the audio URL.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "prompt", label: "Prompt", type: "textarea", default: "{{previous.output}}", placeholder: "calm ambient synth pads, slow tempo…", hint: "Describe the music. Supports {{expressions}}." },
      { key: "model", label: "Model", type: "select", options: [
        "lyria-3-clip-preview",
        "lyria-3-pro-preview",
      ], default: "lyria-3-clip-preview", hint: "Native Nyquest music models. Billed to your Nyquest wallet." },
      { key: "timeout_s", label: "Timeout (s)", type: "number", default: 180, min: 0, max: 300, hint: "0 = no limit." },
      { key: "retries", label: "Retries", type: "number", default: 0, min: 0, max: 3 },
    ],
  },
  {
    type: "nyquest_agent",
    label: "Agent",
    category: "Nyquest",
    accent: "#2dd4bf",
    glyph: "◆",
    description: "Runs a Nyquest multi-step agent (plans, uses tools) toward a goal. Output is the final answer.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "goal", label: "Goal", type: "textarea", default: "{{previous.output}}", placeholder: "Research X and summarize the top 3 findings…", hint: "What the agent should accomplish. Supports {{expressions}}." },
      { key: "model", label: "Planner model", type: "select", options: [], default: "auto", hint: "Auto lets Nyquest pick. Loaded from the relay." },
      { key: "max_steps", label: "Max steps", type: "number", default: 6, min: 1, max: 20, hint: "Caps how many plan/tool steps the agent may take (bounds cost & time)." },
      { key: "timeout_s", label: "Timeout (s)", type: "number", default: 300, min: 10, max: 600, hint: "Overall wall-clock cap for the run." },
    ],
  },
  {
    type: "nyquest_video",
    label: "Video",
    category: "Nyquest",
    accent: "#2dd4bf",
    glyph: "▶",
    description: "Generates an ~8s video from a prompt via Nyquest (Google Veo). Async; output is the video URL.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "prompt", label: "Prompt", type: "textarea", default: "{{previous.output}}", placeholder: "A drone shot gliding over neon-lit rain-soaked streets at night…", hint: "Describe the shot. Supports {{expressions}}." },
      { key: "model", label: "Model", type: "select", options: [
        "veo-3.1-fast-generate-preview",
        "veo-3.1-generate-preview",
      ], default: "veo-3.1-fast-generate-preview", hint: "Veo Fast ≈ $1.44/clip, Veo 3.1 ≈ $3.60/clip. Billed to your Nyquest wallet." },
      { key: "aspect_ratio", label: "Aspect ratio", type: "select", options: ["16:9", "9:16"], default: "16:9" },
      { key: "timeout_s", label: "Timeout (s)", type: "number", default: 300, min: 30, max: 600, hint: "How long to wait for the async job before giving up." },
    ],
  },
  {
    type: "guardrail",
    label: "Guardrail",
    category: "AI Utilities",
    accent: "#7c5cfc",
    glyph: "🛡",
    description: "Checks the input against a policy with an LLM, then routes allow / block.",
    hasInput: true,
    outputs: [
      { id: "allow", label: "allow", color: "#22c55e" },
      { id: "block", label: "block", color: "#ef4444" },
    ],
    fields: [
      { key: "policy", label: "Policy", type: "textarea", default: "Block any message that contains personal data (SSNs, credit-card or account numbers, home addresses) or hateful / harassing content.", hint: "Plain-English rules. Supports {{expressions}}." },
      { key: "model", label: "Model", type: "select", options: [], default: "anthropic/claude-haiku-4.5" },
      { key: "input", label: "Input override", type: "textarea", placeholder: "Optional. Defaults to the upstream node's output." },
    ],
  },
  {
    type: "datastore",
    label: "Data Store",
    category: "Data",
    accent: "#818cf8",
    glyph: "🗄",
    description: "Persistent key/value memory that survives across runs (set / get / append / delete).",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "op", label: "Operation", type: "select", options: ["get", "set", "append", "delete"], default: "get", hint: "get reads; set overwrites; append adds a line; delete clears." },
      { key: "key", label: "Key", type: "text", placeholder: "last_processed_id", hint: "Scoped to this workflow. Supports {{expressions}}." },
      { key: "value", label: "Value (set / append)", type: "textarea", default: "{{previous.output}}", hint: "What to store. Supports {{expressions}}." },
      { key: "separator", label: "Append separator", type: "text", default: "\\n", hint: "Joins appended values (append mode)." },
      { key: "default", label: "Default (get)", type: "textarea", placeholder: "Returned when the key isn't set yet." },
    ],
  },
  {
    type: "email",
    label: "Email",
    category: "Integrations",
    accent: "#22d3ee",
    glyph: "✉",
    description: "Composes an email from the flow. Dry-run until a sender is configured.",
    hasInput: true,
    outputs: [{ id: null }],
    fields: [
      { key: "to", label: "To", type: "text", placeholder: "{{trigger.email}}" },
      { key: "subject", label: "Subject", type: "text", placeholder: "Re: your request" },
      { key: "body", label: "Body", type: "textarea", default: "{{previous.output}}" },
    ],
  },
];

export const CATEGORIES = ["Flow", "AI Models", "AI Utilities", "Nyquest", "Prompts", "Logic", "Human", "Data", "Integrations"];

export const defByType = (t: string) => NODE_DEFS.find((d) => d.type === t);

export function defaultData(t: string): Record<string, any> {
  const def = defByType(t);
  const data: Record<string, any> = {};
  def?.fields.forEach((f) => {
    if (f.default !== undefined) data[f.key] = f.default;
  });
  return data;
}
