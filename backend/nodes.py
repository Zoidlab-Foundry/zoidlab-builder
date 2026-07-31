"""Node execution + the {{expression}} template engine.

Template paths resolve against the run context:
  {{trigger.x}} {{vars.x}} {{previous.output}} {{nodes.<id>.output}}
  {{now}} {{today}} {{workflow.id}} {{workflow.name}}
"""
import re
import json
import asyncio
import socket
import ipaddress
from urllib.parse import urlparse
import httpx
import db_pg as db
import foundry
import pricing
from llm import chat, post_json, get_json, run_agent, DEFAULT_MODEL

_EXPR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _usage_cost(usage):
    """USD cost of one relay call from its usage dict (model + token split). 0.0 when the
    model is unpriced or 'auto' (unknowable) — the run is flagged partial in that case."""
    if not usage:
        return 0.0
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    if pt is None and ct is None:
        # only a total is known — split can't be priced accurately; treat as unpriced
        return 0.0
    cost, _ = pricing.cost_usd(usage.get("model"), pt or 0, ct or 0)
    return cost


def _um(usage):
    """Compact usage for cross-app spend emission: resolved model + token split."""
    if not usage:
        return None
    return {"model": usage.get("model"), "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens")}


def _host_is_public(host: str) -> bool:
    """True only if every address `host` resolves to is a public, routable IP.
    Blocks loopback / private / link-local (incl. cloud metadata 169.254.169.254) /
    reserved ranges — the SSRF guard for the HTTP node."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
                or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def _ssrf_guard(url: str):
    """Raise ValueError if `url` is not a safe, public http(s) target."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"blocked URL scheme '{p.scheme or 'none'}' — only http/https allowed")
    if not p.hostname:
        raise ValueError("HTTP node: missing host in URL")
    if not _host_is_public(p.hostname):
        raise ValueError(f"blocked internal/non-public host '{p.hostname}'")


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


def _abs_media(url):
    """Native media endpoints return root-relative paths (/media/...); make them
    absolute so downstream nodes (HTTP/Slack/email) and the canvas preview work."""
    if isinstance(url, str) and url.startswith("/"):
        from llm import BASE
        return BASE.rsplit("/v1", 1)[0].rstrip("/") + url
    return url


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
            "cost": _usage_cost(usage),
            "usage": _um(usage),
            "meta": f"{used} · {usage.get('total_tokens', '?')} tok",
        }

    if t == "trustgate":
        subject = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        model = render(str(data.get("model") or ""), ctx) or "auto"
        action = {
            "prompt": subject or "",
            "model": model, "provider": (model.split("/")[0] if "/" in model else None),
            "data_classification": data.get("data_classification") or "internal",
            "max_tokens": int(data.get("max_tokens") or 0) or None,
            "context_type": data.get("context_type") or None,
        }
        res = await foundry.trustgate_check(action, project_id=(data.get("project_id") or None))
        decision = res.get("decision", "skipped")
        blocked = decision in ("blocked", "require_approval")
        branch = "block" if blocked else "allow"
        reasons = res.get("reasons") or []
        return {"output": {"decision": decision, "risk_level": res.get("risk_level"),
                           "reasons": reasons, "recommended_action": res.get("recommended_action"),
                           "allowed": not blocked, "input": subject},
                "branch": branch,
                "meta": f"TrustGate: {decision}" + (f" · {reasons[0][:60]}" if reasons else "")}

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
        _ssrf_guard(url)  # block internal targets (metadata, private ranges)
        # follow_redirects=False so a 3xx can't bounce past the guard to an internal host
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as c:
            r = await c.request(method, url, headers=headers,
                                content=body.encode() if body else None)
        try:
            out = r.json()
        except Exception:
            out = r.text
        return {"output": out, "meta": f"{method} {r.status_code}"}

    # --- Foundry composition: call another ZoidLab app's deployed endpoint ---
    if t in ("rag_query", "memory_recall", "prompt_run"):
        url = render(data.get("endpoint", ""), ctx)
        _ssrf_guard(url)
        incoming_text = incoming if isinstance(incoming, str) else ""
        if t == "rag_query":
            payload = {"question": render(data.get("question", "") or incoming_text, ctx)}
        elif t == "memory_recall":
            payload = {"query": render(data.get("query", "") or incoming_text, ctx)}
        else:
            raw = data.get("variables")
            if isinstance(raw, str):
                try:
                    variables = json.loads(raw) if raw.strip() else {}
                except Exception:
                    variables = {}
            else:
                variables = dict(raw or {})
            payload = {"variables": {k: (render(v, ctx) if isinstance(v, str) else v) for k, v in variables.items()}}
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as c:
            r = await c.post(url, json=payload)
        try:
            j = r.json()
        except Exception:
            j = {}
        if t == "rag_query":
            g = j.get("grounding_score")
            return {"output": j.get("answer", r.text if not j else j),
                    "meta": f"RAG {r.status_code}" + (f" · grounding {g}" if g is not None else ""),
                    "citations": j.get("citations")}
        if t == "memory_recall":
            mems = j.get("memories", []) if isinstance(j, dict) else []
            return {"output": "\n".join(m.get("content", "") for m in mems) or mems,
                    "meta": f"Memory {r.status_code} · {len(mems)} recalled", "memories": mems}
        return {"output": j.get("output", r.text if not j else j), "meta": f"Prompt {r.status_code}"}

    # --- Foundry labs: start a durable job in a sibling lab as the run's user, wait for it ---
    if t in ("vision_run", "voice_run", "mcp_call", "swarm_run"):
        headers = foundry.lab_headers()
        if not headers:
            raise ValueError(f"{t}: no session to reach the lab — run signed-in, or via a deploy/schedule (which mints one)")
        incoming_text = _as_text(incoming) or ""
        if t == "vision_run":
            base, start, detail = foundry.VISIONLAB_URL, "/api/run", "/api/runs/"
            payload = {"task_id": render(data.get("task_id", ""), ctx), "asset_id": render(data.get("asset_id", ""), ctx)}
        elif t == "voice_run":
            base, start, detail = foundry.VOICELAB_URL, "/api/simulate", "/api/runs/"
            payload = {"agent_id": render(data.get("agent_id", ""), ctx), "scenario_id": render(data.get("scenario_id", ""), ctx),
                       "max_turns": int(data.get("max_turns") or 6)}
        elif t == "mcp_call":
            base, start, detail = foundry.MCPLAB_URL, "/api/test", "/api/tests/"
            raw = data.get("arguments")
            if isinstance(raw, str):
                try:
                    args = json.loads(render(raw, ctx)) if raw.strip() else {}
                except Exception:
                    args = {}
            else:
                args = dict(raw or {})
            payload = {"connector_id": render(data.get("connector_id", ""), ctx),
                       "tool_name": render(data.get("tool", ""), ctx), "arguments": args}
        else:
            base, start, detail = foundry.SWARMLAB_URL, "/api/run", "/api/runs/"
            payload = {"swarm_id": render(data.get("swarm_id", ""), ctx),
                       "task_input": render(data.get("task", "") or incoming_text, ctx)}
        if data.get("model"):
            payload["model"] = render(str(data["model"]), ctx)
        wait_s = min(float(data.get("wait_s") or 240), 570)
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(base + start, headers=headers, json=payload)
            if r.status_code != 200:
                raise ValueError(f"{t} start failed: HTTP {r.status_code} — {r.text[:200]}")
            j = r.json() if r.text else {}
            job_id = j.get("job_id")
            rid = j.get("run_id") or (j.get("run") or {}).get("id") or j.get("id")
            status = j.get("status") or (j.get("run") or {}).get("status") or "complete"
            # blocked/not-testable paths return the finished resource inline with no job
            if job_id:
                loop = asyncio.get_event_loop()
                deadline = loop.time() + wait_s
                while loop.time() < deadline:
                    await asyncio.sleep(2.5)
                    jr = await c.get(f"{base}/api/jobs/{job_id}", headers=headers)
                    if jr.status_code != 200:
                        continue
                    status = (jr.json() or {}).get("status") or status
                    if status in ("succeeded", "partial", "failed", "blocked", "timed_out", "cancelled", "interrupted"):
                        break
                else:
                    raise ValueError(f"{t}: lab job still {status} after {int(wait_s)}s — raise wait_s or check the lab's Runs page")
            run = {}
            if rid:
                dr = await c.get(f"{base}{detail}{rid}", headers=headers)
                if dr.status_code == 200:
                    run = dr.json() or {}
        if t == "vision_run":
            conf = run.get("confidence")
            return {"output": run.get("structured") or run.get("summary") or run,
                    "meta": f"Vision {status}" + (f" · conf {round(float(conf), 2)}" if conf is not None else ""),
                    "summary": run.get("summary"), "evidence": run.get("evidence")}
        if t == "voice_run":
            scores = run.get("scores") or {}
            return {"output": run.get("outcome") or status,
                    "meta": f"Voice {status} · {run.get('turns_used') or '?'} turns",
                    "transcript": run.get("transcript"), "scores": scores}
        if t == "mcp_call":
            return {"output": run.get("result") if run.get("result") is not None else run.get("error") or status,
                    "meta": f"MCP {status}" + (f" · {run.get('decision')}" if run.get("decision") else ""),
                    "decision": run.get("decision")}
        return {"output": run.get("final_output") or run.get("outcome") or status,
                "meta": f"Swarm {status} · {run.get('steps_used') or '?'} steps",
                "trace": run.get("trace"), "outcome": run.get("outcome")}

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
        return {"output": out, "tokens": usage.get("total_tokens"), "cost": _usage_cost(usage), "usage": _um(usage), "meta": f"summarized · {model}"}

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
        tok, cost, pt, ct, used_model = 0, 0.0, 0, 0, None
        for it in items:
            local = dict(ctx)
            local["item"] = it
            p = render(data.get("prompt", "{{item}}"), local)
            out, usage = await chat(model, [{"role": "user", "content": p or _as_text(it)}],
                                    temperature=0.4, max_tokens=int(data.get("max_tokens", 300)))
            results.append(out)
            tok += usage.get("total_tokens") or 0
            cost += _usage_cost(usage)
            pt += usage.get("prompt_tokens") or 0
            ct += usage.get("completion_tokens") or 0
            used_model = usage.get("model") or used_model
        usage_brief = {"model": used_model, "prompt_tokens": pt, "completion_tokens": ct} if used_model else None
        return {"output": results, "tokens": tok or None, "cost": cost, "usage": usage_brief, "meta": f"mapped {len(results)} item(s)"}

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
                "tokens": usage.get("total_tokens"), "cost": _usage_cost(usage), "usage": _um(usage), "meta": f"→ {matched}"}

    if t == "translator":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        lang = render(str(data.get("language", "English")), ctx) or "English"
        text, usage = await chat(
            model,
            [{"role": "system", "content": f"Translate the user's text into {lang}. Output only the translation."},
             {"role": "user", "content": _as_text(incoming) or "(no input)"}],
            temperature=0.2, max_tokens=1200,
        )
        return {"output": text, "tokens": usage.get("total_tokens"), "cost": _usage_cost(usage), "usage": _um(usage), "meta": f"→ {lang}"}

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
            return {"output": obj, "tokens": usage.get("total_tokens"), "cost": _usage_cost(usage), "usage": _um(usage), "meta": f"extracted {len(keys)} field(s)"}
        except Exception:
            return {"output": text, "tokens": usage.get("total_tokens"), "cost": _usage_cost(usage), "usage": _um(usage), "meta": "extracted (unparsed)"}

    if t in ("slack", "discord"):
        url = render(str(data.get("webhook_url", "")), ctx).strip()
        message = render(str(data.get("message", "")), ctx) or _as_text(incoming)
        if not url:
            return {"output": message, "meta": f"composed · dry-run (no webhook URL)"}
        payload = {"text": message} if t == "slack" else {"content": message[:2000]}
        _ssrf_guard(url)  # same guard the http node uses — the URL is user-supplied
        # follow_redirects=False so a 3xx can't bounce past the guard to an internal host
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as c:
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

    if t == "nyquest_image":
        model = render(str(data.get("model") or ""), ctx).strip() or "imagen-4.0-fast-generate-001"
        prompt = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        prompt = prompt.strip()
        if not prompt:
            raise RuntimeError("image node: empty prompt")
        body = {"model": model, "prompt": prompt}
        ar = render(str(data.get("aspect_ratio", "")), ctx).strip()
        if ar:
            body["aspect_ratio"] = ar
        res = await post_json("image/generate", body)
        # response: {"images": [url, ...]} where each item is a url or {"url": ...}
        imgs = res.get("images") or res.get("data") or []
        url = None
        if imgs:
            first = imgs[0]
            url = first if isinstance(first, str) else (first.get("url") or first.get("b64_json"))
        if not url:
            raise RuntimeError(f"image node: no image in response ({str(res)[:120]})")
        return {"output": _abs_media(url), "meta": f"image · {model}"}

    if t == "nyquest_speech":
        model = render(str(data.get("model") or ""), ctx).strip() or "gemini-2.5-flash-preview-tts"
        text = render(data["text"], ctx) if data.get("text") else _as_text(incoming)
        text = text.strip()
        if not text:
            raise RuntimeError("speech node: empty text")
        body = {"model": model, "text": text}
        voice = render(str(data.get("voice", "")), ctx).strip()
        if voice:
            body["voice"] = voice
        res = await post_json("audio/generate", body)
        url = res.get("audio_url") or res.get("url")
        if not url:
            raise RuntimeError(f"speech node: no audio in response ({str(res)[:120]})")
        return {"output": _abs_media(url), "meta": f"speech · {model}{' · ' + voice if voice else ''}"}

    if t == "nyquest_music":
        model = render(str(data.get("model") or ""), ctx).strip() or "lyria-3-clip-preview"
        prompt = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        prompt = prompt.strip()
        if not prompt:
            raise RuntimeError("music node: empty prompt")
        res = await post_json("music/generate", {"model": model, "prompt": prompt})
        url = res.get("audio_url") or res.get("url")
        if not url:
            raise RuntimeError(f"music node: no audio in response ({str(res)[:120]})")
        return {"output": _abs_media(url), "meta": f"music · {model}"}

    if t == "nyquest_agent":
        goal = render(data["goal"], ctx) if data.get("goal") else _as_text(incoming)
        goal = goal.strip()
        if not goal:
            raise RuntimeError("agent node: empty goal")
        body = {"goal": goal}
        model = render(str(data.get("model") or ""), ctx).strip()
        if model and model != "auto":
            body["model"] = model
        try:
            ms = int(data.get("max_steps") or 0)
        except Exception:
            ms = 0
        if ms > 0:
            body["max_steps"] = min(ms, 20)  # bound cost/latency
        res = await run_agent(body)
        ev = res["final"]
        content = ev.get("content") or ""
        cents = ev.get("total_cents")
        used = ev.get("steps_used")
        meta = f"agent · {used} step(s)"
        if isinstance(cents, (int, float)):
            meta += f" · ${cents / 100:.4f}"
        return {"output": content, "meta": meta}

    if t == "nyquest_video":
        prompt = render(data["prompt"], ctx) if data.get("prompt") else _as_text(incoming)
        prompt = prompt.strip()
        if not prompt:
            raise RuntimeError("video node: empty prompt")
        body = {"prompt": prompt}
        model = render(str(data.get("model") or ""), ctx).strip()
        if model and model != "auto":
            body["model"] = model
        ar = render(str(data.get("aspect_ratio", "")), ctx).strip()
        if ar:
            body["aspect_ratio"] = ar
        try:
            dur = int(data.get("duration_seconds") or 0)
        except Exception:
            dur = 0
        if dur > 0:
            body["duration_seconds"] = dur
        # submit (202 + {job_id, status}); balance is held up front
        sub = await post_json("video/generate", body)
        job_id = sub.get("job_id") or sub.get("id")
        if not job_id:
            raise RuntimeError(f"video node: no job_id in response ({str(sub)[:120]})")
        # poll the job until done/failed, self-bounded so we never loop forever
        try:
            max_wait = float(data.get("timeout_s") or 300)
        except Exception:
            max_wait = 300.0
        if max_wait <= 0:
            max_wait = 300.0
        interval, waited = 6.0, 0.0
        while True:
            await asyncio.sleep(interval)
            waited += interval
            job = await get_json(f"video/jobs/{job_id}")
            st = str(job.get("status") or "").lower()
            if st in ("done", "completed", "succeeded"):
                url = job.get("video_url") or job.get("url")
                if not url:
                    raise RuntimeError("video node: job done but no video_url")
                cost = job.get("cost")
                meta = f"video · {job.get('model') or model or 'veo'}"
                if isinstance(cost, (int, float)):
                    meta += f" · ${cost:.2f}"
                return {"output": _abs_media(url), "meta": meta}
            if st in ("failed", "error", "canceled", "cancelled"):
                raise RuntimeError("video job failed: " + str(job.get("error") or st)[:200])
            if waited >= max_wait:
                raise RuntimeError(f"video node: timed out after {int(waited)}s (job {job_id} still {st or 'running'})")

    if t == "guardrail":
        model = render(str(data.get("model") or ""), ctx) or DEFAULT_MODEL
        policy = render(data.get("policy", ""), ctx).strip() or "Block unsafe or disallowed content."
        subject = render(data["input"], ctx) if data.get("input") else _as_text(incoming)
        text, usage = await chat(
            model,
            [{"role": "system", "content": "You are a strict content guardrail. Given a POLICY and a MESSAGE, "
              "decide whether the message is ALLOWED or BLOCKED under the policy. Reply with ONE JSON object only: "
              '{"decision":"allow"|"block","reason":"one short sentence"}.'},
             {"role": "user", "content": f"POLICY:\n{policy}\n\nMESSAGE:\n{subject or '(empty)'}"}],
            temperature=0, max_tokens=120,
        )
        decision, reason = "allow", ""
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[text.find("{"):])
            decision = "block" if str(obj.get("decision", "")).lower().startswith("block") else "allow"
            reason = str(obj.get("reason", "")).strip()
        except Exception:
            decision = "block" if "block" in text.lower() else "allow"
        # allow → pass the content through; block → carry the reason so a
        # downstream node can explain the rejection.
        out = incoming if decision == "allow" else (reason or "Blocked by policy.")
        meta = decision + (f" · {reason[:40]}" if reason else "")
        return {"output": out, "branch": decision,
                "tokens": usage.get("total_tokens"), "meta": meta}

    if t == "datastore":
        owner = ctx.get("_owner")
        wid = (ctx.get("workflow") or {}).get("id") or ""
        key = render(str(data.get("key", "")), ctx).strip()
        if not key:
            raise RuntimeError("data store: empty key")
        op = (data.get("op") or "get").lower()
        if op == "get":
            val = db.kv_get(owner, wid, key)
            if val is None:
                val = render(str(data.get("default", "")), ctx)
            return {"output": val, "meta": f"get {key}"}
        if op == "set":
            val = render(data.get("value", "{{previous.output}}"), ctx)
            db.kv_set(owner, wid, key, val)
            return {"output": val, "meta": f"set {key}"}
        if op == "append":
            val = render(data.get("value", "{{previous.output}}"), ctx)
            sep = data.get("separator")
            sep = sep if isinstance(sep, str) and sep else "\n"
            new = db.kv_append(owner, wid, key, val, sep)
            return {"output": new, "meta": f"append {key}"}
        if op == "delete":
            db.kv_delete(owner, wid, key)
            return {"output": incoming, "meta": f"delete {key}"}
        raise RuntimeError(f"data store: unknown op '{op}'")

    # unknown node type: pass through so the graph still runs
    return {"output": incoming, "meta": f"passthrough ({t})"}
