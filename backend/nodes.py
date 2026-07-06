"""Node execution + the {{expression}} template engine.

Template paths resolve against the run context:
  {{trigger.x}} {{vars.x}} {{previous.output}} {{nodes.<id>.output}}
  {{now}} {{today}} {{workflow.id}} {{workflow.name}}
"""
import re
import json
import httpx
from llm import chat, DEFAULT_MODEL

_EXPR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def resolve(path, ctx):
    cur = ctx
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def render(template, ctx):
    if not isinstance(template, str):
        return template

    def sub(m):
        val = resolve(m.group(1).strip(), ctx)
        if val is None:
            return ""
        return val if isinstance(val, str) else json.dumps(val)

    return _EXPR.sub(sub, template)


def _as_text(v):
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v)


async def exec_node(node, ctx):
    """Run one node. Returns a dict with at least {output}; may add
    {tokens, cost, branch, meta}. `ctx['previous']['output']` is this node's input."""
    t = node["type"]
    data = node.get("data") or {}
    incoming = ctx["previous"]["output"]

    if t == "start":
        return {"output": ctx.get("trigger") or {}, "meta": "trigger received"}

    if t == "end":
        return {"output": incoming, "meta": "workflow output"}

    if t == "prompt":
        template = data.get("template", "")
        return {"output": render(template, ctx), "meta": "rendered"}

    if t == "llm":
        model = data.get("model") or DEFAULT_MODEL
        system = render(data.get("system", ""), ctx)
        # user message: explicit prompt template if given, else the upstream output
        user = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user or "(no input)"})
        text, usage = await chat(
            model, messages,
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 1024)),
        )
        return {
            "output": text,
            "tokens": usage.get("total_tokens"),
            "meta": f"{model} · {usage.get('total_tokens', '?')} tok",
        }

    if t == "decision":
        mode = data.get("mode", "contains")
        value = render(str(data.get("value", "")), ctx)
        subject = _as_text(incoming)
        if mode == "contains":
            hit = value.lower() in subject.lower()
        elif mode == "equals":
            hit = subject.strip().lower() == value.strip().lower()
        elif mode == "not_empty":
            hit = bool(subject.strip())
        else:
            hit = bool(value)
        return {"output": incoming, "branch": "true" if hit else "false",
                "meta": f"{mode} → {'true' if hit else 'false'}"}

    if t == "http":
        method = (data.get("method") or "GET").upper()
        url = render(data.get("url", ""), ctx)
        headers = data.get("headers") or {}
        body = render(data.get("body", ""), ctx) if data.get("body") else None
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.request(method, url, headers=headers,
                                content=body.encode() if body else None)
        try:
            out = r.json()
        except Exception:
            out = r.text
        return {"output": out, "meta": f"{method} {r.status_code}"}

    # unknown node type: pass through so the graph still runs
    return {"output": incoming, "meta": f"passthrough ({t})"}
