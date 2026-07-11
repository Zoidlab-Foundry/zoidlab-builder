"""Node execution + the {{expression}} template engine.

Template paths resolve against the run context:
  {{trigger.x}} {{vars.x}} {{previous.output}} {{nodes.<id>.output}}
  {{now}} {{today}} {{workflow.id}} {{workflow.name}}
"""
import re
import json
import asyncio
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
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        system = render(data.get("system", ""), ctx)
        # user message: explicit prompt template if given, else the upstream output
        user = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user or "(no input)"})
        temp = float(data.get("temperature", 0.7))
        max_t = int(data.get("max_tokens", 1024))
        used = model
        try:
            text, usage = await chat(model, messages, temperature=temp, max_tokens=max_t)
        except Exception:
            fb = render(str(data.get("fallback") or ""), ctx).strip()
            if fb and fb != model:
                text, usage = await chat(fb, messages, temperature=temp, max_tokens=max_t)
                used = fb + " (fallback)"
            else:
                raise
        return {
            "output": text,
            "tokens": usage.get("total_tokens"),
            "meta": f"{used} · {usage.get('total_tokens', '?')} tok",
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

    if t == "webhook":
        return {"output": ctx.get("trigger") or {}, "meta": "webhook trigger"}

    if t == "model":
        var = data.get("var") or "model"
        m = render(str(data.get("model") or "auto"), ctx) or "auto"
        ctx["vars"][var] = m
        # transparent inline node: pass input through so it can sit mid-flow
        return {"output": incoming if incoming is not None else m, "meta": f"{var} = {m}"}

    if t == "variable":
        name = data.get("name") or "var"
        val = render(data.get("value", ""), ctx)
        ctx["vars"][name] = val
        return {"output": val, "meta": f"set {name}"}

    if t == "summarizer":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        guide = {
            "one line": "in a single sentence",
            "short": "in 2-3 sentences",
            "detailed": "in a thorough paragraph",
        }.get(data.get("length", "short"), "briefly")
        out, usage = await chat(
            model,
            [{"role": "system", "content": f"Summarize the user's text {guide}. Output only the summary."},
             {"role": "user", "content": _as_text(incoming) or "(no input)"}],
            temperature=0.3, max_tokens=600,
        )
        return {"output": out, "tokens": usage.get("total_tokens"), "meta": f"summarized · {model}"}

    if t == "email":
        to = render(data.get("to", ""), ctx)
        envelope = {
            "to": to,
            "subject": render(data.get("subject", ""), ctx),
            "body": render(data.get("body", ""), ctx),
        }
        # dry-run: the builder composes the message; wire a sender to deliver it
        return {"output": envelope, "meta": f"composed → {to or '(no recipient)'} · dry-run"}

    if t == "switch":
        mode = data.get("mode", "contains")
        cases = [c.strip() for c in str(data.get("cases", "")).splitlines() if c.strip()]
        subject = _as_text(incoming)
        matched = "default"
        for c in cases:
            if (mode == "equals" and subject.strip().lower() == c.lower()) or \
               (mode != "equals" and c.lower() in subject.lower()):
                matched = c
                break
        return {"output": incoming, "branch": matched, "meta": f"→ {matched}"}

    if t == "foreach":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        raw = render(data.get("over", ""), ctx) if data.get("over") else incoming
        items = None
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                items = parsed if isinstance(parsed, list) else None
            except Exception:
                items = None
        if items is None:
            items = [ln for ln in _as_text(raw).splitlines() if ln.strip()]
        items = items[:20]  # bound the fan-out
        results = []
        for it in items:
            local = dict(ctx)
            local["item"] = it
            p = render(data.get("prompt", "{{item}}"), local)
            out, _ = await chat(model, [{"role": "user", "content": p or _as_text(it)}],
                                temperature=0.4, max_tokens=int(data.get("max_tokens", 300)))
            results.append(out)
        return {"output": results, "meta": f"mapped {len(results)} item(s)"}

    if t == "delay":
        try:
            secs = min(max(float(data.get("seconds", 2) or 0), 0), 120)
        except Exception:
            secs = 2
        await asyncio.sleep(secs)
        return {"output": incoming, "meta": f"waited {secs:g}s"}

    if t == "jsonpath":
        raw = incoming
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                pass
        path = str(data.get("path", "")).strip()
        cur = raw
        for part in [p for p in path.split(".") if p]:
            if isinstance(cur, list):
                try:
                    cur = cur[int(part)]
                except Exception:
                    cur = None
                    break
            elif isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        return {"output": cur, "meta": f"→ {path or '(root)'}"}

    if t == "classifier":
        labels = [ln.strip() for ln in str(data.get("labels", "")).splitlines() if ln.strip()]
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        subject = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        text, usage = await chat(
            model,
            [{"role": "system", "content": "Classify the user's text. Reply with exactly one of these labels and nothing else: " + ", ".join(labels)},
             {"role": "user", "content": subject or "(no input)"}],
            temperature=0, max_tokens=10,
        )
        low = text.strip().lower()
        matched = next((l for l in labels if l.lower() in low), "default")
        return {"output": incoming, "branch": matched,
                "tokens": usage.get("total_tokens"), "meta": f"→ {matched}"}

    if t == "translator":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        lang = render(str(data.get("language", "English")), ctx) or "English"
        text, usage = await chat(
            model,
            [{"role": "system", "content": f"Translate the user's text into {lang}. Output only the translation."},
             {"role": "user", "content": _as_text(incoming) or "(no input)"}],
            temperature=0.2, max_tokens=1200,
        )
        return {"output": text, "tokens": usage.get("total_tokens"), "meta": f"→ {lang}"}

    if t == "extractor":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        fields = [ln.strip() for ln in str(data.get("fields", "")).splitlines() if ln.strip()]
        keys = [f.split(":", 1)[0].strip() for f in fields]
        text, usage = await chat(
            model,
            [{"role": "system", "content": "Extract these fields from the user's text and reply with ONE JSON object only (keys: "
              + ", ".join(keys) + "). Use null for anything not present.\nField notes:\n" + "\n".join(fields)},
             {"role": "user", "content": _as_text(incoming) or "(no input)"}],
            temperature=0, max_tokens=600,
        )
        try:
            start = text.find("{")
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            return {"output": obj, "tokens": usage.get("total_tokens"), "meta": f"extracted {len(keys)} field(s)"}
        except Exception:
            return {"output": text, "tokens": usage.get("total_tokens"), "meta": "extracted (unparsed)"}

    if t in ("slack", "discord"):
        url = render(str(data.get("webhook_url", "")), ctx).strip()
        message = render(str(data.get("message", "")), ctx) or _as_text(incoming)
        if not url:
            return {"output": message, "meta": f"composed · dry-run (no webhook URL)"}
        payload = {"text": message} if t == "slack" else {"content": message[:2000]}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json=payload)
        ok = r.status_code < 300
        return {"output": message,
                "meta": f"{'sent' if ok else f'failed {r.status_code}'} · {t}"}

    if t == "merge":
        parts = incoming if isinstance(incoming, list) else [incoming]
        parts = [p for p in parts if p is not None]
        if data.get("mode") == "collect":
            return {"output": parts, "meta": f"collected {len(parts)}"}
        sep = data.get("separator")
        sep = sep if isinstance(sep, str) and sep else "\n\n"
        texts = [_as_text(p) for p in parts if _as_text(p) != ""]
        return {"output": sep.join(texts), "meta": f"merged {len(texts)} input(s)"}

    # unknown node type: pass through so the graph still runs
    return {"output": incoming, "meta": f"passthrough ({t})"}
