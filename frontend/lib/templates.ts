// Starter templates — real, runnable workflows. Each is self-contained (a prompt
// node injects sample input) so it runs the moment you open it. Selecting one
// instantiates a fresh workflow the user can edit.
export interface Template {
  slug: string;
  name: string;
  description: string;
  glyph: string;
  accent: string;
  nodes: { id: string; type: string; position: { x: number; y: number }; data: Record<string, any> }[];
  edges: { id: string; source: string; target: string; sourceHandle?: string | null }[];
}

const SAMPLE_EMAIL =
  "Subject: Double charged this month\n\nHi — I just noticed my card was billed twice for my Pro subscription this month. Can you refund the extra charge? Thanks, Dana";

const SAMPLE_GUEST =
  "Hi! I'd love to book a table for 4 this Friday around 7pm under the name Alex. Do you have anything by the window?";

const SAMPLE_CLAUSE =
  "The Provider shall indemnify and hold harmless the Client against any and all claims arising from data breaches, with liability capped at fees paid in the preceding 12 months. This clause survives termination.";

export const TEMPLATES: Template[] = [
  {
    slug: "support-triage",
    name: "Support Email Triage",
    description: "Classify an incoming email as billing / bug / sales and draft a tailored reply.",
    glyph: "✉",
    accent: "#4fd1c5",
    nodes: [
      { id: "start", type: "start", position: { x: 60, y: 200 }, data: {} },
      { id: "email", type: "prompt", position: { x: 300, y: 200 }, data: { template: SAMPLE_EMAIL } },
      { id: "classify", type: "llm", position: { x: 560, y: 200 }, data: { model: "anthropic/claude-haiku-4.5", system: "Reply with exactly one lowercase word — billing, bug, or sales — classifying this support email.", prompt: "{{nodes.email.output}}", temperature: 0, max_tokens: 5 } },
      { id: "route", type: "switch", position: { x: 820, y: 200 }, data: { mode: "contains", cases: "billing\nbug\nsales" } },
      { id: "billing", type: "llm", position: { x: 1090, y: 60 }, data: { model: "anthropic/claude-sonnet-5", system: "You are a billing specialist. Write a warm, specific reply that resolves the customer's billing issue.", prompt: "{{nodes.email.output}}", max_tokens: 400 } },
      { id: "bug", type: "llm", position: { x: 1090, y: 210 }, data: { model: "anthropic/claude-sonnet-5", system: "You are a support engineer. Acknowledge the bug and give clear next steps.", prompt: "{{nodes.email.output}}", max_tokens: 400 } },
      { id: "sales", type: "llm", position: { x: 1090, y: 360 }, data: { model: "anthropic/claude-sonnet-5", system: "You are a sales rep. Reply enthusiastically and propose a quick demo.", prompt: "{{nodes.email.output}}", max_tokens: 400 } },
      { id: "end", type: "end", position: { x: 1360, y: 210 }, data: {} },
    ],
    edges: [
      { id: "e1", source: "start", target: "email" },
      { id: "e2", source: "email", target: "classify" },
      { id: "e3", source: "classify", target: "route" },
      { id: "e4", source: "route", target: "billing", sourceHandle: "billing" },
      { id: "e5", source: "route", target: "bug", sourceHandle: "bug" },
      { id: "e6", source: "route", target: "sales", sourceHandle: "sales" },
      { id: "e7", source: "billing", target: "end" },
      { id: "e8", source: "bug", target: "end" },
      { id: "e9", source: "sales", target: "end" },
    ],
  },
  {
    slug: "restaurant-concierge",
    name: "Restaurant Concierge",
    description: "Read a guest message, extract the booking details, and compose a confirmation email.",
    glyph: "◷",
    accent: "#7c5cfc",
    nodes: [
      { id: "hook", type: "webhook", position: { x: 60, y: 160 }, data: { path: "/hook/reservations" } },
      { id: "msg", type: "prompt", position: { x: 320, y: 160 }, data: { template: SAMPLE_GUEST } },
      { id: "concierge", type: "llm", position: { x: 580, y: 160 }, data: { model: "anthropic/claude-sonnet-5", system: "You are a warm restaurant concierge. Extract the date, time, and party size from the guest message, then write a friendly confirmation.", prompt: "{{nodes.msg.output}}", max_tokens: 400 } },
      { id: "confirm", type: "email", position: { x: 840, y: 160 }, data: { to: "guest@example.com", subject: "Your reservation at Zoid Bistro", body: "{{nodes.concierge.output}}" } },
      { id: "end", type: "end", position: { x: 1100, y: 160 }, data: {} },
    ],
    edges: [
      { id: "e1", source: "hook", target: "msg" },
      { id: "e2", source: "msg", target: "concierge" },
      { id: "e3", source: "concierge", target: "confirm" },
      { id: "e4", source: "confirm", target: "end" },
    ],
  },
  {
    slug: "doc-review",
    name: "Document Review",
    description: "Summarize a document, decide if it needs legal review, then flag or approve it.",
    glyph: "❡",
    accent: "#818cf8",
    nodes: [
      { id: "start", type: "start", position: { x: 60, y: 200 }, data: {} },
      { id: "doc", type: "prompt", position: { x: 300, y: 200 }, data: { template: SAMPLE_CLAUSE } },
      { id: "summary", type: "summarizer", position: { x: 560, y: 200 }, data: { model: "anthropic/claude-sonnet-5", length: "short" } },
      { id: "assess", type: "llm", position: { x: 820, y: 200 }, data: { model: "anthropic/claude-haiku-4.5", system: "Decide if this document needs legal review. Reply YES or NO, then a one-line reason.", prompt: "{{nodes.doc.output}}", temperature: 0, max_tokens: 60 } },
      { id: "gate", type: "decision", position: { x: 1080, y: 200 }, data: { mode: "contains", value: "YES" } },
      { id: "flag", type: "llm", position: { x: 1330, y: 90 }, data: { model: "anthropic/claude-sonnet-5", system: "Draft a short note flagging this document for legal review, citing the concern.", prompt: "Summary: {{nodes.summary.output}}\n\nAssessment: {{nodes.assess.output}}", max_tokens: 250 } },
      { id: "approve", type: "llm", position: { x: 1330, y: 320 }, data: { model: "anthropic/claude-sonnet-5", system: "Draft a brief note stating the document is approved with no legal concerns.", prompt: "Summary: {{nodes.summary.output}}", max_tokens: 200 } },
      { id: "end", type: "end", position: { x: 1600, y: 200 }, data: {} },
    ],
    edges: [
      { id: "e1", source: "start", target: "doc" },
      { id: "e2", source: "doc", target: "summary" },
      { id: "e3", source: "summary", target: "assess" },
      { id: "e4", source: "assess", target: "gate" },
      { id: "e5", source: "gate", target: "flag", sourceHandle: "true" },
      { id: "e6", source: "gate", target: "approve", sourceHandle: "false" },
      { id: "e7", source: "flag", target: "end" },
      { id: "e8", source: "approve", target: "end" },
    ],
  },
  {
    slug: "meeting-brief",
    name: "Meeting Brief",
    description: "Turn a topic into researched talking points, then a crisp 5-bullet brief.",
    glyph: "✦",
    accent: "#22d3ee",
    nodes: [
      { id: "start", type: "start", position: { x: 60, y: 160 }, data: {} },
      { id: "topic", type: "prompt", position: { x: 300, y: 160 }, data: { template: "Q3 product roadmap planning meeting" } },
      { id: "research", type: "llm", position: { x: 560, y: 160 }, data: { model: "anthropic/claude-sonnet-5", system: "List 6 concise, concrete talking points for a meeting on the given topic.", prompt: "{{nodes.topic.output}}", max_tokens: 400 } },
      { id: "brief", type: "llm", position: { x: 820, y: 160 }, data: { model: "anthropic/claude-sonnet-5", system: "Turn these talking points into a crisp meeting brief: a title line, then exactly 5 bullets.", prompt: "{{nodes.research.output}}", max_tokens: 400 } },
      { id: "end", type: "end", position: { x: 1080, y: 160 }, data: {} },
    ],
    edges: [
      { id: "e1", source: "start", target: "topic" },
      { id: "e2", source: "topic", target: "research" },
      { id: "e3", source: "research", target: "brief" },
      { id: "e4", source: "brief", target: "end" },
    ],
  },
];
