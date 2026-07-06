"""Nyquest relay client — OpenAI-compatible gateway at NYQUEST_BASE_URL.
All LLM nodes route through here, giving the builder every model Nyquest exposes."""
import os
import httpx

BASE = os.environ.get("NYQUEST_BASE_URL", "https://api.nyquest.ai/v1").rstrip("/")
KEY = os.environ.get("NYQUEST_API_KEY", "")
DEFAULT_MODEL = os.environ.get("BUILDER_DEFAULT_MODEL", "anthropic/claude-sonnet-5")


def _headers():
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
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
