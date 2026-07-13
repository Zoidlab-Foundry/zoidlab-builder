"""Cross-app Foundry integration — Builder ⇄ TrustGate / SpendGuard.

Two real enforcement paths:
  • SpendGuard emission — after a run, each LLM call's real model + token split is POSTed
    to SpendGuard's ledger so Builder spend shows up in the user's SpendGuard dashboard.
  • TrustGate check — the `trustgate` node asks TrustGate's live policy engine "is this AI
    action allowed?" and routes allow/block on the real decision.

Auth: sibling apps are Nyquest-Pro gated on the shared `zb_session` cookie. An interactive
run forwards the caller's cookie; an unattended run (webhook/schedule) mints a short-lived
session for the workflow owner with the shared BUILDER_SESSION_SECRET. All calls are
best-effort and never break a workflow run.
"""
import os
import time
import uuid
import datetime
import jwt
import httpx
from contextvars import ContextVar

ENABLED = os.environ.get("FOUNDRY_INTEGRATION", "on").lower() not in ("off", "false", "0")
SPENDGUARD_URL = os.environ.get("SPENDGUARD_URL", "http://127.0.0.1:8701").rstrip("/")
TRUSTGATE_URL = os.environ.get("TRUSTGATE_URL", "http://127.0.0.1:8700").rstrip("/")
SECRET = os.environ.get("BUILDER_SESSION_SECRET", "")

# per-run auth: the zb_session token to present to sibling apps
_session: ContextVar = ContextVar("foundry_session", default=None)


def set_session(token):
    _session.set(token or None)


def mint_session(owner, email=None, tier="pro"):
    """A short-lived zb_session for `owner` so unattended runs can reach Pro-gated siblings.
    The owner is a Pro user (they created/deployed this through the gated Builder)."""
    if not (SECRET and owner):
        return None
    now = int(time.time())
    return jwt.encode({"sub": owner, "email": email, "tier": tier, "iat": now, "exp": now + 900},
                      SECRET, algorithm="HS256")


def _headers():
    tok = _session.get()
    return {"Cookie": f"zb_session={tok}", "Content-Type": "application/json"} if tok else None


def available():
    return ENABLED and bool(_headers())


# --- SpendGuard: emit real usage from a completed run ----------------------
def spend_events_from(events, feature="", environment="production", correlation_id=None, resource_ref=None):
    """Build canonical SpendGuard usage events (blueprint §6.3) from a run's node events.
    Only LLM calls with a known model + token split are emitted (priced from real tokens)."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("type") != "node":
            continue
        u = ev.get("usage") or {}
        model = u.get("model")
        if not model:
            continue
        pt = int(u.get("prompt_tokens") or 0)
        ct = int(u.get("completion_tokens") or 0)
        if pt <= 0 and ct <= 0:
            continue
        out.append({"model": model, "prompt_tokens": pt, "completion_tokens": ct,
                    "app": "builder", "feature": feature or (ev.get("nodeId") or ""),
                    "source": "builder", "latency_ms": ev.get("ms"),
                    "environment": environment, "correlation_id": correlation_id,
                    "resource_ref": resource_ref})
    return out


async def emit_spend(events, workflow=None, source="editor"):
    """POST the run's LLM usage to SpendGuard as canonical usage events. Best-effort."""
    if not available():
        return 0
    wf = workflow or {}
    # editor runs are development; unattended (webhook/schedule) are production
    environment = "production" if source in ("webhook", "schedule") else "development"
    correlation_id = "run_" + uuid.uuid4().hex[:12]
    resource_ref = {"package_id": "builder", "resource_id": wf.get("id"),
                    "resource_type": "workflow"} if wf.get("id") else None
    payload = spend_events_from(events, feature=(wf.get("name") or "")[:60],
                                environment=environment, correlation_id=correlation_id,
                                resource_ref=resource_ref)
    if not payload:
        return 0
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{SPENDGUARD_URL}/api/events/bulk", headers=_headers(),
                             json={"events": payload})
            return len(payload) if r.status_code < 400 else 0
    except Exception:
        return 0


# --- TrustGate: real policy decision ---------------------------------------
async def trustgate_check(action, project_id=None):
    """Ask TrustGate's engine if an action is allowed. Returns the decision dict
    ({decision, risk_level, reasons, ...}) or {'decision':'skipped', ...} if unreachable."""
    if not available():
        return {"decision": "skipped", "reason": "TrustGate not reachable / not signed in",
                "reasons": [], "risk_level": "unknown"}
    body = {"project_id": project_id, "request": action, "save": True}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{TRUSTGATE_URL}/api/test", headers=_headers(), json=body)
            if r.status_code >= 400:
                return {"decision": "skipped", "reason": f"TrustGate {r.status_code}",
                        "reasons": [], "risk_level": "unknown"}
            return r.json()
    except Exception as ex:
        return {"decision": "skipped", "reason": str(ex)[:120], "reasons": [], "risk_level": "unknown"}
