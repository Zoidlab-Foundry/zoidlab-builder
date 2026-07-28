"""Builder assistant manifest — what the in-app assistant knows and may do.

Builder already has two AI surfaces: the ✦ Flowsmith copilot (natural language -> a draft
workflow on the canvas) and the guided Tour. The assistant INTEGRATES with them rather than
duplicating: its one write capability routes to Flowsmith's own endpoint, and everything
canvas-native (running a workflow via SSE, deploying, schedules, secrets, orgs) stays in the
UI where it belongs. No deletes.
"""
from foundry_common.assistant import cap, page

MANIFEST = {
    "app": "Builder",
    "description": (
        "The AI Workflow Builder is the Foundry's orchestration studio and its control room: "
        "drag nodes onto a canvas, connect them into a runnable graph, and compose the other "
        "Foundry apps as native steps (RAG Query, Memory Recall, Prompt Run, Vision Run, "
        "Voice Simulation, MCP Tool Call, Swarm Run) alongside LLM, logic, HTTP and approval "
        "nodes. The canvas has its own ✦ Flowsmith button that drafts a whole workflow from a "
        "sentence, a Guide tour, and a Run button that streams live node status. Workflows can "
        "be versioned, deployed as webhooks and scheduled."
    ),
    "base_url": "http://127.0.0.1:8200",
    "pages": [
        page("/", "Canvas", "The workflow editor: node library, canvas, config panel, run stream, "
                            "plus Workflows / History / Runs / Deploy / Secrets / Orgs modals.",
             assists={"flowsmith": "the Flowsmith copilot button"}),
    ],
    "capabilities": [
        cap("list_workflows", "GET", "/api/workflows", risk="read",
            desc="The user's workflows (and org-shared ones they can access)."),
        cap("get_workflow", "GET", "/api/workflows/{wid}", risk="read",
            desc="One workflow's nodes and edges.", params={"wid": "workflow id"}),
        cap("list_runs", "GET", "/api/runs", risk="read",
            desc="Recent workflow runs with status, tokens and cost."),
        cap("get_run", "GET", "/api/runs/{rid}", risk="read",
            desc="One run: per-node events, output, tokens and cost.", params={"rid": "run id"}),
        cap("list_models", "GET", "/api/models", risk="read",
            desc="Models available on the relay for LLM nodes."),
        cap("generate_workflow", "POST", "/api/generate", risk="write",
            desc="Ask Flowsmith to draft a workflow from a natural-language description. "
                 "Returns a draft graph the user reviews and saves on the canvas — it does not "
                 "run anything. Running, deploying, scheduling, secrets and orgs stay in the UI.",
            params={"prompt": "what the workflow should do", "model": "model id (optional)"}),
    ],
}
