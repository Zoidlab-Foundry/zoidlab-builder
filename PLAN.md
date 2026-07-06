# ZoidLab · AI Workflow Builder — Project Plan

**Status:** Phase-1 vertical slice **live** at https://builder.zoidlab.ai · **Updated:** 2026-07-06

---

## 1. Vision

The visual orchestration platform for Nyquest. Users build complete AI workflows by
dragging components onto a canvas, connecting them, configuring, testing, and deploying to
production in one click. Everything compiles to a standardized **workflow DAG** executed by
the Nyquest runtime.

Design philosophy: **no-code** for business users, **low-code** for developers,
**full-code** extensibility for engineers.

The benchmark is not to match LangFlow / Flowise / n8n — it's to **surpass** them by
combining visual orchestration, enterprise governance, multi-model AI, and AI-assisted
workflow generation into one platform that extends the rest of the Nyquest ecosystem.

## 2. What a workflow is

A Directed Acyclic Graph of **Nodes** connected by **Edges**. Each node exposes inputs,
outputs, configuration, execution status, logging, and metrics. Data flows along edges;
`{{expressions}}` reference upstream outputs, trigger payloads, and variables.

```
Start → Webhook → Prompt → LLM → Decision → LLM → Email → End
```

The canonical JSON schema (`backend/schema.py`) is the contract the whole platform — canvas,
executor, versioning, deployment — reads and writes.

## 3. Architecture

**Frontend** — Next.js · React · TypeScript · React Flow (canvas) · TailwindCSS · Zustand ·
(ShadCN, Framer Motion, React Query to layer in).
**Backend** — FastAPI · Python · execution engine. Target infra: PostgreSQL · Redis · Celery ·
Docker · K8s-ready. Storage: Postgres · MinIO · vector-DB abstraction · Redis cache.

**Current lean implementation (prototype):** FastAPI + SQLite + in-process DAG executor;
Next.js + React Flow + Zustand + Tailwind. Migrates to the full infra in later phases without
touching callers (all persistence behind `db.py`; execution behind `executor.py`).

**LLM access:** all model nodes route through the **Nyquest relay** (OpenAI-compatible,
`https://api.nyquest.ai/v1`, ~200 models) — one gateway, every model, unified cost/routing.

## 4. Feature surface (from the base spec)

- **Canvas** — infinite pan/zoom, grid, snap, minimap, undo/redo, copy/paste, multi-select,
  alignment, groups, comments, search, auto-arrange, dark/light, keyboard shortcuts.
- **Node library** — AI Models (OpenAI, Claude, Gemini, Llama, Mistral, Qwen, DeepSeek, Grok,
  OpenRouter, Ollama, Custom API), Prompts, Logic (If/Switch/Loop/Merge/Approval/Retry…),
  Data (Variable/JSON/CSV/DB/Memory/Vector/File/Media…), Integrations (REST/GraphQL/Webhook/
  Slack/Discord/Teams/GitHub/Jira/Salesforce/Drive/S3/Email/Twilio/SSH/SNMP/Grafana/
  Cloudflare…), AI Utilities (Embedding/Retriever/Summarizer/Vision/OCR/STT/TTS/Classify/
  Extract/Function-calling/Reranker/Guardrails/Eval/Compression/Splicer), Human Interaction
  (Approval/Review/Chat/Notification/Form/Manual/Pause/Resume).
- **Node configuration** — per-node panel; everything configurable without code (model, temp,
  tokens, tools, memory, retry, timeout, fallback, caching, cost tracking, logging…).
- **Variable system** — global/local/secret/env/runtime vars + full expression language.
- **Execution** — manual, scheduled/cron, webhook, REST, email/Slack/Teams triggers, DB/queue
  events, future MCP triggers.
- **Testing mode** — live node highlighting (green running / yellow waiting / red failed /
  blue complete) with per-node time, tokens, cost, output, logs.
- **Live debugger** — pause, inspect variables/prompt/response, step, replay, compare runs.
- **Versioning** — every save = version + author + diff + deploy status; rollback; branches later.
- **Templates** — Restaurant Concierge, Help Desk, Support, Sales Agent, Doc Review, Email
  Classifier, Resume Reviewer, Legal Intake, Medical Scheduler, Policy Checker, Network
  Troubleshooting, Meeting Summarizer, KB Chat.
- **Deployment** — one click to REST API / Webhook / Embedded Widget / Worker / Scheduled Job /
  Internal or Customer Agent / Chatbot / Public API.
- **Monitoring** — executions, success/failure, runtime, cost, tokens, model usage, latency,
  retries, top workflows.
- **Security** — RBAC, projects, orgs, secrets vault, encrypted credentials, audit logs, API
  keys, approval chains, dev/test/prod separation.
- **Flowsmith (AI assist)** — user describes a workflow in plain English; AI builds the graph,
  wires connections, generates prompts, configures variables. A defining feature.

## 5. Nyquest integration

Not a standalone product — the **orchestration layer** for all Nyquest capabilities, each
exposed as a native workflow node: AI Concierge, Compression Engine, Splicer, Governance &
Policy Engine, MCP Connector Framework, RAG Builder, Prompt Studio, Agent Marketplace, Memory
Studio, Evaluation Lab. Every new Nyquest capability automatically becomes a node.

## 6. Roadmap

**Phase 1 — Foundation (2–3 wks):** auth + projects, React Flow canvas, node/edge system, basic
library, save/load, JSON schema, manual execution, execution logs, dark/light, auto-save.
*Deliverable: visually create, save, load, execute simple workflows.*

**Phase 2 — Core automation (3–4 wks):** LLM nodes (OpenAI/Claude/Gemini/Ollama), prompt
templates, variables + expression engine, logic nodes, REST/Webhook, human approval, live
execution viz, retry/timeout. *Deliverable: production-capable AI workflows.*

**Phase 3 — Enterprise (4–6 wks):** secrets vault, RBAC/orgs, versioning/rollback, cron
scheduling, API deployment, monitoring dashboard, cost/token analytics, audit logs, templates.
*Deliverable: enterprise-ready platform for customer deployments.*

**Phase 4 — AI-native (4–6 wks):** Flowsmith generates workflows from natural language,
auto-optimization + quality analysis + performance recommendations, multi-agent orchestration,
native Nyquest nodes. *Deliverable: an AI development environment, not just a visual automation tool.*

## 7. Current status (prototype vertical slice — DONE)

Live at **builder.zoidlab.ai** (behind an interim password gate). Delivered:

- React Flow canvas (dark Nyquest palette), draggable **node library**, per-node **config panel**.
- Node types: **Start · Prompt · LLM (via Nyquest relay) · Decision · HTTP · End**.
- JSON DAG schema; **save / load / list** workflows (SQLite).
- In-process executor streaming **live node status over SSE**; canvas highlights running →
  complete/error with per-node output, timing, tokens.
- `{{expression}}` template engine (previous.output, trigger.*, nodes.*, now, workflow.*).
- Runs on zoidberg: `zoidlab-builder-api` (:8200) + `zoidlab-builder-web` (:3100), exposed via
  the `mcp-zoidberg` Cloudflare tunnel. Repo: **256kMagic/zoidlab-builder** (private).

## 8. Decisions locked

- Prototype = **vertical slice** first, grow into the full plan node-by-node.
- Infra = **lean** (SQLite + in-process) now; Postgres/Redis/Celery in Phase 3.
- Hosting = **builder.zoidlab.ai** via existing tunnel; auth = interim Basic Auth now,
  **Cloudflare Access** once a zoidlab.ai-zone-scoped CF token is available.
- LLM = always through the **Nyquest relay/gateway**, not providers directly.

## 9. Immediate next steps

1. ~~**Flowsmith** — NL → workflow generation (the defining feature).~~ ✅ shipped
2. ~~Integrated right-click context menus + instructional tour.~~ ✅ shipped
3. Workflow list / open picker in the UI (backend already supports it).
4. Broaden node library + starter templates.
5. Versioning + rollback.
5. Cloudflare Access hardening.

## 10. Success criteria

A new customer can: sign in → create a project → describe a workflow in plain English → have
AI generate it → refine by drag-and-drop → test with live debugging → deploy as API / chatbot /
scheduled job / background service → monitor health, cost, and performance from one dashboard.
