"""Flowsmith — turns a plain-English description into a workflow DAG.
Calls the relay with a schema-constrained system prompt, extracts JSON,
validates node types, and auto-lays-out the graph left-to-right."""
import re
import json
import uuid
from collections import deque
from llm import chat, DEFAULT_MODEL

VALID_TYPES = {"start", "prompt", "llm", "decision", "http", "end", "webhook", "summarizer",
               "switch", "foreach", "variable", "email", "model", "classifier", "translator",
               "extractor", "jsonpath", "delay", "slack", "discord", "merge", "approval",
               "nyquest_image", "nyquest_speech", "nyquest_music", "nyquest_agent",
               "nyquest_video"}

CATALOG_DOC = """Available node types (use "type" and "data" exactly as shown):
- start   entry point.            data: {}
- prompt  render a template.      data: {"template": "...  use {{previous.output}}, {{trigger.x}}"}
- llm     call a model.           data: {"model":"anthropic/claude-sonnet-5","system":"...","temperature":0.7,"max_tokens":1024}
- decision  branch true/false.    data: {"mode":"contains|equals|not_empty","value":"..."}  -> two edges, sourceHandle "true" and "false"
- switch  multi-way branch on text. data: {"mode":"contains","cases":"a\\nb\\nc"} -> one edge per case (sourceHandle = case) + "default"
- merge   wait for all incoming branches then combine. data: {"mode":"combine|collect"}
- approval  pause for a human decision. data: {"message":"...","auto":"reject"} -> two edges, sourceHandle "approved" and "rejected"
- classifier  LLM classify + route. data: {"labels":"a\\nb\\nc","model":"anthropic/claude-haiku-4.5"} -> one edge per label (sourceHandle = label) + "default"
- summarizer  condense input.     data: {"model":"...","length":"one line|short|detailed"}
- translator  translate input.    data: {"language":"Spanish","model":"..."}
- extractor  text -> JSON fields. data: {"fields":"name\\ndate\\namount","model":"..."}
- jsonpath  pick field from JSON. data: {"path":"a.b.0.c"}
- variable  set {{vars.NAME}}.    data: {"name":"x","value":"{{previous.output}}"}
- delay   pause the flow.         data: {"seconds":5}
- http    REST call.              data: {"method":"GET|POST|PUT|DELETE","url":"https://...","headers":{},"body":"..."}
- slack   post via webhook.       data: {"webhook_url":"{{secrets.SLACK_WEBHOOK}}","message":"{{previous.output}}"}
- discord post via webhook.       data: {"webhook_url":"{{secrets.DISCORD_WEBHOOK}}","message":"{{previous.output}}"}
- nyquest_image  generate an image (Nyquest/Imagen). data: {"prompt":"a teal robot logo, flat vector","model":"imagen-4.0-fast-generate-001","aspect_ratio":"1:1"} -> output is the image URL
- nyquest_speech  text-to-speech (Nyquest). data: {"text":"{{previous.output}}","model":"gemini-2.5-flash-preview-tts","voice":"Kore"} -> output is the audio URL
- nyquest_music  generate an instrumental clip (Nyquest/Lyria). data: {"prompt":"calm ambient synth","model":"lyria-3-clip-preview"} -> output is the audio URL
- nyquest_agent  run a multi-step Nyquest agent (plans + tools) toward a goal. data: {"goal":"{{previous.output}}","model":"auto","max_steps":6} -> output is the agent's final answer
- nyquest_video  generate an ~8s video (Nyquest/Veo, async). data: {"prompt":"drone shot over neon streets","model":"veo-3.1-fast-generate-preview","aspect_ratio":"16:9"} -> output is the video URL. PRICEY (~$1.44+) — only use when the user explicitly asks for video.
- email   compose an email.       data: {"to":"...","subject":"...","body":"{{previous.output}}"}
- webhook inbound trigger.        data: {"path":"/hook/name"}
- end     terminal output.        data: {}"""

EXAMPLE = """{"name":"Support Email Triage","nodes":[
{"id":"n1","type":"start","data":{}},
{"id":"n2","type":"llm","data":{"model":"anthropic/claude-sonnet-5","system":"You are a support triage assistant. Classify the email as billing, bug, or sales, then write a warm, specific reply.","prompt":"Incoming email:\\n{{trigger.email}}","temperature":0.3,"max_tokens":700}},
{"id":"n3","type":"end","data":{}}],
"edges":[{"id":"e1","source":"n1","target":"n2","sourceHandle":null},{"id":"e2","source":"n2","target":"n3","sourceHandle":null}]}"""

SYSTEM = f"""You are Flowsmith, the ZoidLab workflow builder. Turn the user's plain-English request into a runnable workflow.

{CATALOG_DOC}

Output rules:
- Reply with ONE JSON object and nothing else — no markdown fences, no commentary.
- Shape: {{"name":"short title","nodes":[{{"id":"n1","type":"start","data":{{}}}}],"edges":[{{"id":"e1","source":"n1","target":"n2","sourceHandle":null}}]}}
- Include exactly one "start" and at least one "end".
- Use ONLY the node types and the EXACT data keys listed above. Do NOT invent keys
  (no "label", "input", "system_prompt", "cases", "output_variable", "condition") or node types.
- llm nodes: "model" MUST be a full relay id with a provider prefix like "anthropic/claude-sonnet-5"
  or "openai/gpt-5" — never a bare name like "gpt-4". Put instructions in "system" and the input in "prompt".
- Prefer simple linear flows. For branching use ONLY "decision" nodes (mode/value), and give each
  decision exactly two edges — sourceHandle "true" and "false". There is no switch/router node.
- Write REAL, useful prompt/system text — not placeholders. Short ids (n1, n2…) and (e1, e2…).

Here is a complete valid example:
{EXAMPLE}"""


def _extract_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    a = t.find("{")
    if a == -1:
        raise ValueError("model did not return JSON")
    # raw_decode parses the first complete JSON object and ignores any
    # trailing prose / second object the model may append.
    obj, _ = json.JSONDecoder().raw_decode(t[a:])
    return obj


ALLOWED = {
    "start": [], "end": [],
    "prompt": ["template"],
    "llm": ["model", "system", "prompt", "temperature", "max_tokens"],
    "decision": ["mode", "value"],
    "switch": ["mode", "cases"],
    "merge": ["mode", "separator"],
    "approval": ["message", "timeout_s", "on_timeout", "auto"],
    "classifier": ["labels", "model", "prompt"],
    "summarizer": ["model", "length"],
    "translator": ["language", "model"],
    "extractor": ["fields", "model"],
    "jsonpath": ["path"],
    "variable": ["name", "value"],
    "delay": ["seconds"],
    "foreach": ["over", "model", "prompt", "max_tokens"],
    "http": ["method", "url", "headers", "body"],
    "slack": ["webhook_url", "message"],
    "discord": ["webhook_url", "message"],
    "nyquest_image": ["prompt", "model", "aspect_ratio"],
    "nyquest_speech": ["text", "model", "voice"],
    "nyquest_music": ["prompt", "model"],
    "nyquest_agent": ["goal", "model", "max_steps"],
    "nyquest_video": ["prompt", "model", "aspect_ratio"],
    "email": ["to", "subject", "body"],
    "webhook": ["path"],
    "model": ["model", "var"],
}
ALIASES = {
    "system_prompt": "system", "systemprompt": "system", "instructions": "system",
    "user": "prompt", "user_prompt": "prompt", "input": "prompt", "query": "prompt",
    "text": "template", "content": "template",
    "condition": "value", "expression": "value",
}


def _normalize(node: dict) -> dict:
    """Coerce a model-generated node onto the strict schema: map field aliases,
    drop unknown keys, and fix invalid llm models."""
    t = node.get("type", "prompt")
    raw = node.get("data") or {}
    mapped: dict = {}
    for k, v in raw.items():
        mapped[ALIASES.get(str(k).lower(), k)] = v

    allowed = ALLOWED.get(t, [])
    data = {k: mapped[k] for k in allowed if k in mapped}

    if t == "llm":
        m = str(data.get("model", ""))
        if "/" not in m:  # bare names like "gpt-4" aren't valid relay ids
            data["model"] = DEFAULT_MODEL
    if t == "prompt" and "template" not in data:
        data["template"] = mapped.get("prompt") or mapped.get("template") or "{{previous.output}}"
    node["data"] = data
    return node


def _layout(wf: dict) -> None:
    nodes = {n["id"]: n for n in wf["nodes"]}
    adj: dict[str, list] = {}
    indeg = {nid: 0 for nid in nodes}
    for e in wf["edges"]:
        adj.setdefault(e["source"], []).append(e["target"])
        if e["target"] in indeg:
            indeg[e["target"]] += 1
    depth = {nid: 0 for nid in nodes}
    q = deque([nid for nid in nodes if indeg.get(nid, 0) == 0] or list(nodes)[:1])
    seen = set(q)
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            depth[v] = max(depth[v], depth[u] + 1)
            if v not in seen:
                seen.add(v)
                q.append(v)
    col: dict[int, list] = {}
    for nid, d in depth.items():
        col.setdefault(d, []).append(nid)
    for d, ids in col.items():
        for i, nid in enumerate(ids):
            nodes[nid]["position"] = {"x": 80 + d * 270, "y": 140 + i * 140}


async def generate(prompt: str, model: str | None = None) -> dict:
    text, _ = await chat(
        model or DEFAULT_MODEL,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2500,
    )
    wf = _extract_json(text)

    wf.setdefault("name", "Generated workflow")
    wf["id"] = "wf_" + uuid.uuid4().hex[:8]
    nodes = wf.get("nodes") or []
    for i, n in enumerate(nodes):
        n.setdefault("id", f"n{i + 1}")
        n.setdefault("data", {})
        if n.get("type") not in VALID_TYPES:
            n["type"] = "prompt"
        _normalize(n)
    for i, e in enumerate(wf.get("edges") or []):
        e.setdefault("id", f"e{i + 1}")
        e.setdefault("sourceHandle", None)

    if not any(n["type"] == "start" for n in nodes):
        raise ValueError("generated workflow has no start node")
    _layout(wf)
    return wf
