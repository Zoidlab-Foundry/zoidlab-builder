"""Nyquest relay client — OpenAI-compatible gateway at NYQUEST_BASE_URL.
All LLM nodes route through here, giving the builder every model Nyquest exposes."""
import os
import json
import httpx
from contextvars import ContextVar

BASE = os.environ.get("NYQUEST_BASE_URL", "https://api.nyquest.ai/v1").rstrip("/")
KEY = os.environ.get("NYQUEST_API_KEY", "")
DEFAULT_MODEL = os.environ.get("BUILDER_DEFAULT_MODEL", "anthropic/claude-sonnet-5")

# Per-request relay auth — set to the logged-in user's own key so their wallet
# is billed. Falls back to the shared KEY (owner) when unset.
_relay_auth: ContextVar = ContextVar("relay_auth", default=None)


def set_relay_auth(value):
    _relay_auth.set(value or None)


def _auth():
    return _relay_auth.get() or KEY


def _headers():
    h = {"Authorization": f"Bearer {_auth()}", "Content-Type": "application/json"}
    # OpenRouter attribution (harmless on other OpenAI-compatible gateways)
    if "openrouter" in BASE:
        h["HTTP-Referer"] = "https://builder.zoidlab.ai"
        h["X-Title"] = "ZoidLab Workflow Builder"
    return h


async def chat(model, messages, temperature=0.7, max_tokens=1024):
    """Returns (text, usage_dict). Raises on transport/HTTP error."""
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            f"{BASE}/chat/completions",
            headers=_headers(),
            json={
                "model": model or DEFAULT_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"relay {r.status_code}: {r.text[:300]}")
        j = r.json()
        text = (j.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return text, j.get("usage", {}) or {}


async def post_json(path, body, timeout=180):
    """POST to a Nyquest API path (relative to the /v1 base) with per-user auth.
    Used by native Nyquest nodes (image gen, etc.). Raises on HTTP error."""
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(f"{BASE}/{path.lstrip('/')}", headers=_headers(), json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"nyquest {r.status_code}: {r.text[:200]}")
        return r.json()


async def get_json(path, timeout=30):
    """GET a Nyquest API path (relative to the /v1 base) with per-user auth.
    Used to poll async jobs (video). Raises on HTTP error."""
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(f"{BASE}/{path.lstrip('/')}", headers=_headers())
        if r.status_code >= 400:
            raise RuntimeError(f"nyquest {r.status_code}: {r.text[:200]}")
        return r.json()


async def run_agent(body, read_timeout=180.0):
    """POST /v1/agents/run and consume the SSE stream to completion (per-user
    auth). Returns the terminal 'final' event dict (with content/total_cents/
    steps_used) plus a 'steps' list of plan/tool_call/observation events.
    Raises on HTTP failure, an 'error' event, or a stream that ends with no final.
    read_timeout bounds the gap BETWEEN events (agents emit periodically), not
    the total run — the executor's timeout_s caps overall wall-clock."""
    steps = []
    to = httpx.Timeout(connect=15.0, read=read_timeout, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=to) as c:
        async with c.stream("POST", f"{BASE}/agents/run", headers=_headers(), json=body) as r:
            if r.status_code >= 400:
                raw = (await r.aread()).decode(errors="replace")[:200]
                raise RuntimeError(f"agents {r.status_code}: {raw}")
            buf = ""
            async for chunk in r.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    for line in block.split("\n"):
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            ev = json.loads(payload)
                        except Exception:
                            continue
                        et = ev.get("type")
                        if et in ("plan", "tool_call", "observation"):
                            steps.append(ev)
                        elif et == "final":
                            return {"final": ev, "steps": steps}
                        elif et == "error":
                            raise RuntimeError("agent error: " + str(ev.get("message"))[:200])
    raise RuntimeError("agent stream ended without a final event")


async def list_models():
    """Model ids from the relay, for the node config dropdown. Never raises."""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{BASE}/models", headers={"Authorization": f"Bearer {KEY}"})
            r.raise_for_status()
            ids = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
            return sorted(ids)
    except Exception:
        # fallback list so the UI always has options even if the relay is down
        return [
            "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5",
            "gpt-5", "gpt-5-mini", "gemini-2.5-pro", "llama-4-70b",
        ]
