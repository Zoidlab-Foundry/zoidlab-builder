"""ZoidLab AI Workflow Builder — API.
FastAPI + SQLite + in-process DAG executor. LLM nodes route through the Nyquest relay."""
import json
import time
import asyncio
import datetime
from contextlib import asynccontextmanager
from croniter import croniter
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

import db
import orgs
import analyzer
import foundry
from schema import Workflow, RunRequest
from executor import run_workflow, resolve_approval
from llm import list_models, set_relay_auth
from flowsmith import generate as flowsmith_generate
from auth import relay_key_from_cookie, session_payload
import vault
from pydantic import BaseModel

def _next_run(cron: str, base=None) -> str:
    base = base or datetime.datetime.now(datetime.timezone.utc)
    nxt = croniter(cron, base).get_next(datetime.datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=datetime.timezone.utc)
    return nxt.astimezone(datetime.timezone.utc).isoformat()


async def scheduler_loop():
    """Single in-process cron scheduler (systemd runs one uvicorn worker).
    Runs due workflows on their owner's key, logs them as source=schedule."""
    while True:
        try:
            for sch in db.due_schedules():
                wid, owner = sch["workflow_id"], sch["owner"]
                wf = db.get_workflow_raw(wid)  # unattended runner — schedule row is the capability
                nxt = _next_run(sch["cron"])
                now_iso = datetime.datetime.utcnow().isoformat() + "Z"
                if not wf:
                    with db._conn() as _c:
                        _c.execute("DELETE FROM schedules WHERE workflow_id=?", (wid,))
                    continue
                set_relay_auth(sch.get("relay_key"))
                foundry.set_session(foundry.mint_session(owner))
                try:
                    res = await _collect(wf, {}, db.secrets_map(owner), owner)
                    db.log_run(wid, owner, "schedule", res)
                    try:
                        await foundry.emit_spend(res.get("events"), wf.get("name"))
                    except Exception:
                        pass
                except Exception as ex:
                    db.log_run(wid, owner, "schedule",
                               {"status": "error", "error": str(ex), "events": [],
                                "started_at": now_iso, "ms": 0})
                db.mark_schedule_ran(wid, now_iso, nxt)
        except Exception:
            pass
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()


app = FastAPI(title="ZoidLab Workflow Builder", version="0.1.0", lifespan=lifespan)

import os as _os
_ALLOWED_ORIGINS = [o.strip() for o in _os.environ.get(
    "BUILDER_ALLOWED_ORIGINS",
    "https://builder.zoidlab.ai,https://foundry.zoidlab.ai,https://zoidlab.ai"
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


PRO_TIERS = {"pro", "teams", "team", "enterprise"}
# Public paths — no session required. Everything else under /api requires a Pro session.
# /hooks/* is the deployed-webhook trigger whose unguessable token IS the credential.
_PUBLIC_PATHS = ("/api/health", "/api/models")
_PUBLIC_PREFIXES = ("/hooks/",)
# SSE streaming endpoints are skipped by the middleware (BaseHTTPMiddleware can buffer
# streamed responses) and enforce auth inline via require_pro() instead.
_STREAM_PATHS = ("/api/run",)


def _pro_error(request: Request):
    """Return an HTTP error if the request lacks a valid Nyquest Pro session, else None."""
    p = session_payload(request.cookies.get("zb_session"))
    if not p or not p.get("sub"):
        return JSONResponse({"detail": "sign_in_required"}, status_code=401)
    if str(p.get("tier") or "").lower() not in PRO_TIERS:
        return JSONResponse({"detail": "pro_required"}, status_code=403)
    return None


def require_pro(request: Request):
    """Inline guard for streaming endpoints: raises 401/403 unless the caller is Pro."""
    p = session_payload(request.cookies.get("zb_session"))
    if not p or not p.get("sub"):
        raise HTTPException(status_code=401, detail="sign_in_required")
    if str(p.get("tier") or "").lower() not in PRO_TIERS:
        raise HTTPException(status_code=403, detail="pro_required")
    return p.get("sub")


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    """Backend-enforced Nyquest Pro gate. Ensures a request that reaches the API directly
    (not just through the frontend proxy) can't act as an anonymous shared-sandbox owner."""
    path = request.url.path
    exempt = (request.method == "OPTIONS" or not path.startswith("/api")
              or path in _PUBLIC_PATHS or path in _STREAM_PATHS
              or any(path.startswith(p) for p in _PUBLIC_PREFIXES))
    if not exempt:
        err = _pro_error(request)
        if err is not None:
            return err
    return await call_next(request)


def owner_of(request: Request):
    """Workflow owner = the Nyquest user id from the session. Behind the auth gate above,
    every /api endpoint that calls this already has a verified Pro session."""
    p = session_payload(request.cookies.get("zb_session"))
    return p.get("sub") if p else None


def ctx_of(request: Request):
    """Access context {user, orgs:{org_id: role}} for RBAC-scoped workflow/run access.
    Also claims any pending email invites for this user (idempotent, cheap)."""
    p = session_payload(request.cookies.get("zb_session")) or {}
    uid = p.get("sub")
    if uid and p.get("email"):
        try:
            orgs.claim_invites(uid, p["email"])
        except Exception:
            pass
    return {"user": uid, "orgs": orgs.user_org_roles(uid), "email": p.get("email"), "name": p.get("name")}


@app.get("/api/health")
def health():
    return {"ok": True, "service": "zoidlab-builder"}


@app.get("/api/models")
async def models():
    # "auto" = let the Nyquest relay route to the best model
    return {"models": ["auto", *await list_models()]}


@app.get("/api/workflows")
def workflows(request: Request):
    return {"workflows": db.list_workflows(ctx_of(request))}


@app.get("/api/workflows/{wid}")
def get_workflow(wid: str, request: Request):
    wf = db.get_workflow(wid, ctx_of(request))
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@app.post("/api/workflows")
def save_workflow(wf: Workflow, request: Request):
    ctx = ctx_of(request)
    body = wf.model_dump()
    existed = db.get_workflow(body.get("id"), ctx) is not None
    r = db.save_workflow(body, ctx)
    if not r:
        raise HTTPException(403, "You don't have edit access to this workflow")
    if not existed:
        orgs.audit(ctx["user"], body.get("org_id"), "workflow", body.get("id"), "created", {"name": body.get("name")})
    return r


@app.delete("/api/workflows/{wid}")
def delete_workflow(wid: str, request: Request):
    ctx = ctx_of(request)
    if not db.delete_workflow(wid, ctx):
        raise HTTPException(403, "You don't have permission to delete this workflow")
    orgs.audit(ctx["user"], None, "workflow", wid, "deleted", {})
    return {"ok": True}


class RenameRequest(BaseModel):
    name: str


@app.patch("/api/workflows/{wid}")
def rename_workflow(wid: str, req: RenameRequest, request: Request):
    r = db.rename_workflow(wid, req.name.strip() or "Untitled workflow", ctx_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


@app.post("/api/workflows/{wid}/clone")
def clone_workflow(wid: str, request: Request):
    r = db.clone_workflow(wid, ctx_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


class MoveRequest(BaseModel):
    org_id: str | None = None


@app.post("/api/workflows/{wid}/move")
def move_workflow(wid: str, req: MoveRequest, request: Request):
    ctx = ctx_of(request)
    r = db.move_workflow(wid, req.org_id, ctx)
    if not r:
        raise HTTPException(403, "You don't have permission to move this workflow")
    orgs.audit(ctx["user"], req.org_id, "workflow", wid, "moved", {"org_id": req.org_id})
    return r


# --- versioning ---
@app.get("/api/workflows/{wid}/versions")
def list_versions(wid: str, request: Request):
    v = db.list_versions(wid, ctx_of(request))
    if v is None:
        raise HTTPException(404, "Workflow not found")
    return {"versions": v}


class SnapshotRequest(BaseModel):
    label: str | None = None


@app.post("/api/workflows/{wid}/snapshot")
def snapshot_workflow(wid: str, req: SnapshotRequest, request: Request):
    r = db.snapshot_workflow(wid, (req.label or "").strip(), ctx_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


@app.get("/api/versions/{vid}")
def get_version(vid: str, request: Request):
    v = db.get_version(vid, ctx_of(request))
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@app.post("/api/versions/{vid}/restore")
def restore_version(vid: str, request: Request):
    ctx = ctx_of(request)
    wf = db.restore_version(vid, ctx)
    if not wf:
        raise HTTPException(404, "Version not found")
    orgs.audit(ctx["user"], wf.get("org_id"), "workflow", wf.get("id"), "version_restored", {})
    return wf


# --- secrets vault ---
@app.get("/api/secrets")
def secrets_list(request: Request):
    # values are never returned — only name + masked preview
    return {"secrets": db.list_secrets(owner_of(request))}


class SecretRequest(BaseModel):
    value: str


@app.put("/api/secrets/{name}")
def secret_set(name: str, req: SecretRequest, request: Request):
    if not vault.valid_name(name):
        raise HTTPException(400, "Name must be letters, numbers, or underscore (max 64).")
    if not req.value:
        raise HTTPException(400, "Empty value.")
    return db.set_secret(owner_of(request), name, req.value)


@app.delete("/api/secrets/{name}")
def secret_delete(name: str, request: Request):
    db.delete_secret(owner_of(request), name)
    return {"ok": True}


# --- monitoring ---
@app.get("/api/stats")
def stats(request: Request):
    return db.run_stats(ctx_of(request))


@app.get("/api/runs")
def runs(request: Request, workflow_id: str | None = None):
    return {"runs": db.list_runs(ctx_of(request), workflow_id)}


@app.get("/api/runs/{rid}")
def run_detail(rid: str, request: Request):
    r = db.get_run(rid, ctx_of(request))
    if not r:
        raise HTTPException(404, "Run not found")
    return r


# --- deployment (deploy workflow as a webhook) ---
@app.get("/api/workflows/{wid}/deployment")
def get_deployment(wid: str, request: Request):
    d = db.get_deployment(wid, ctx_of(request))
    if d is None:
        raise HTTPException(404, "Workflow not found")
    return d


@app.post("/api/workflows/{wid}/deploy")
def deploy(wid: str, request: Request):
    p = session_payload(request.cookies.get("zb_session"))
    ctx = ctx_of(request)
    d = db.deploy_workflow(wid, ctx, p.get("rk") if p else None)
    if d is None:
        raise HTTPException(403, "You don't have permission to deploy this workflow")
    orgs.audit(ctx["user"], None, "workflow", wid, "deployed", {})
    return d


@app.delete("/api/workflows/{wid}/deploy")
def undeploy(wid: str, request: Request):
    ctx = ctx_of(request)
    if not db.undeploy_workflow(wid, ctx):
        raise HTTPException(403, "You don't have permission")
    orgs.audit(ctx["user"], None, "workflow", wid, "undeployed", {})
    return {"ok": True}


# --- schedule (cron trigger) ---
@app.get("/api/workflows/{wid}/schedule")
def get_schedule(wid: str, request: Request):
    return db.get_schedule(wid, ctx_of(request)) or {"cron": None, "enabled": 0}


class ScheduleRequest(BaseModel):
    cron: str


@app.put("/api/workflows/{wid}/schedule")
def set_schedule(wid: str, req: ScheduleRequest, request: Request):
    cron = (req.cron or "").strip()
    if not croniter.is_valid(cron):
        raise HTTPException(400, "Invalid cron expression (5 fields: min hour dom mon dow, UTC).")
    p = session_payload(request.cookies.get("zb_session"))
    ctx = ctx_of(request)
    s = db.set_schedule(wid, ctx, cron, p.get("rk") if p else None, _next_run(cron))
    if s is None:
        raise HTTPException(403, "You don't have permission to schedule this workflow")
    orgs.audit(ctx["user"], None, "workflow", wid, "scheduled", {"cron": cron})
    return s


@app.delete("/api/workflows/{wid}/schedule")
def delete_schedule(wid: str, request: Request):
    db.delete_schedule(wid, ctx_of(request))
    return {"ok": True}


# --- organizations + RBAC -------------------------------------------------
@app.get("/api/orgs")
def list_orgs(request: Request):
    return {"orgs": orgs.list_orgs(owner_of(request))}


class OrgBody(BaseModel):
    name: str


@app.post("/api/orgs")
def create_org(body: OrgBody, request: Request):
    uid = owner_of(request)
    if not (body.name or "").strip():
        raise HTTPException(400, "Org name required")
    return {"org": orgs.create_org(body.name, uid)}


@app.get("/api/orgs/{oid}")
def get_org(oid: str, request: Request):
    o = orgs.get_org(oid, owner_of(request))
    if not o:
        raise HTTPException(404, "Org not found")
    return o


@app.patch("/api/orgs/{oid}")
def rename_org(oid: str, body: OrgBody, request: Request):
    o = orgs.rename_org(oid, body.name, owner_of(request))
    if not o:
        raise HTTPException(403, "Only an owner can rename the org")
    return o


@app.delete("/api/orgs/{oid}")
def delete_org(oid: str, request: Request):
    if not orgs.delete_org(oid, owner_of(request)):
        raise HTTPException(403, "Only an owner can delete the org")
    return {"ok": True}


class MemberBody(BaseModel):
    email: str | None = None
    user_id: str | None = None
    role: str = "viewer"


@app.post("/api/orgs/{oid}/members")
def add_member(oid: str, body: MemberBody, request: Request):
    r = orgs.add_member(oid, owner_of(request), email=body.email, member_user_id=body.user_id, role=body.role)
    if r.get("error"):
        code = 403 if r["error"] == "forbidden" else 400
        raise HTTPException(code, r["error"])
    return r


class RoleBody(BaseModel):
    role: str


@app.patch("/api/orgs/{oid}/members/{mid}")
def update_member(oid: str, mid: str, body: RoleBody, request: Request):
    r = orgs.update_member(oid, owner_of(request), mid, body.role)
    if r.get("error"):
        code = 403 if r["error"] in ("forbidden", "owner_only") else 400
        raise HTTPException(code, r["error"])
    return r


@app.delete("/api/orgs/{oid}/members/{mid}")
def remove_member(oid: str, mid: str, request: Request):
    r = orgs.remove_member(oid, owner_of(request), mid)
    if r.get("error"):
        code = 403 if r["error"] == "forbidden" else 400
        raise HTTPException(code, r["error"])
    return r


# --- audit log ------------------------------------------------------------
@app.get("/api/audit")
def audit(request: Request, org_id: str | None = None):
    rows = orgs.audit_list(owner_of(request), org_id=org_id)
    if rows is None:
        raise HTTPException(403, "Admin access required for this org's audit log")
    return {"audit": rows}


class ApproveRequest(BaseModel):
    token: str
    decision: str


@app.post("/api/approve")
def approve(req: ApproveRequest):
    """Resolve a pending human-approval node during an interactive run."""
    return {"ok": resolve_approval(req.token, req.decision)}


async def _collect(wf: dict, trigger: dict, secrets: dict, owner=None) -> dict:
    """Run a workflow to completion, collecting (redacted) events into a summary."""
    started = datetime.datetime.utcnow().isoformat() + "Z"
    t0 = time.time()
    red = vault.make_redactor(secrets.values())
    events, status, output, tokens, err = [], "complete", None, 0, None
    async for ev in run_workflow(wf, trigger, secrets, owner=owner):
        events.append(red(ev))
        if ev.get("type") == "node":
            if ev.get("tokens"):
                tokens += ev["tokens"]
            if ev.get("status") == "error":
                status, err = "error", red(ev.get("error"))
        elif ev.get("type") == "done":
            output = red(ev.get("output"))
        elif ev.get("type") == "error":
            status, err = "error", red(ev.get("error"))
    return {"status": status, "output": output, "tokens": tokens or None,
            "error": err, "ms": int((time.time() - t0) * 1000),
            "started_at": started, "events": events}


# --- public webhook trigger (no session; the token IS the credential) ---
@app.get("/hooks/{token}")
def hook_info(token: str):
    dep = db.deployment_by_token(token)
    if not dep:
        raise HTTPException(404, "Unknown or disabled hook")
    return {"ok": True, "workflow": dep["workflow"]["name"],
            "usage": "POST a JSON body here — it becomes {{trigger.*}} in the workflow."}


@app.post("/hooks/{token}")
async def hook_trigger(token: str, request: Request):
    dep = db.deployment_by_token(token)
    if not dep:
        raise HTTPException(404, "Unknown or disabled hook")
    try:
        trigger = await request.json()
    except Exception:
        trigger = {}
    if not isinstance(trigger, dict):
        trigger = {"payload": trigger}

    set_relay_auth(dep["relay_key"])  # bill the deployer's own wallet
    foundry.set_session(foundry.mint_session(dep["owner"]))  # unattended: mint a session for cross-app calls
    res = await _collect(dep["workflow"], trigger, db.secrets_map(dep["owner"]), dep["owner"])
    db.log_run(dep["workflow"]["id"], dep["owner"], "webhook", res)
    try:
        await foundry.emit_spend(res.get("events"), dep["workflow"].get("name"))
    except Exception:
        pass
    return JSONResponse(
        {"ok": res["status"] == "complete", "workflow": dep["workflow"]["name"],
         "status": res["status"], "output": res["output"],
         "ms": res["ms"], "tokens": res["tokens"], "error": res["error"]},
        status_code=200 if res["status"] == "complete" else 500,
    )


class GenerateRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.post("/api/generate")
async def generate(req: GenerateRequest, request: Request):
    """Flowsmith: natural-language description → workflow DAG."""
    set_relay_auth(relay_key_from_cookie(request.cookies.get("zb_session")))
    try:
        return await flowsmith_generate(req.prompt, req.model)
    except Exception as ex:
        raise HTTPException(400, f"Flowsmith could not build that: {ex}")


@app.post("/api/analyze")
def analyze_workflow(req: RunRequest, request: Request):
    """Quality analysis + performance recommendations for a workflow (AI-native, Phase 4).
    Static checks are deterministic; perf recs come from THIS workflow's real run history."""
    wf = req.workflow.model_dump()
    ctx = ctx_of(request)
    stats = db.node_run_stats(wf.get("id"), ctx) if wf.get("id") else {}
    return analyzer.analyze(wf, stats)


class OptimizeRequest(BaseModel):
    workflow: Workflow


@app.post("/api/optimize")
def optimize_workflow(req: OptimizeRequest, request: Request):
    """Return an optimized copy of the workflow with safe, behavior-preserving hardening
    applied (timeouts, retries, fallback, missing End). The caller reviews + applies it."""
    return analyzer.optimize(req.workflow.model_dump())


@app.post("/api/run")
async def run(req: RunRequest, request: Request):
    """Execute a workflow, streaming node status events as SSE."""
    require_pro(request)  # streaming endpoint — enforced inline (skipped by the middleware)
    wf = req.workflow.model_dump()
    cookie = request.cookies.get("zb_session")
    auth = relay_key_from_cookie(cookie)
    owner = owner_of(request)
    secrets = db.secrets_map(owner)
    red = vault.make_redactor(secrets.values())

    async def gen():
        set_relay_auth(auth)  # bill the logged-in user's own Nyquest wallet
        foundry.set_session(cookie)  # forward the caller's session for cross-app (TrustGate/SpendGuard) calls
        started = datetime.datetime.utcnow().isoformat() + "Z"
        t0 = time.time()
        events, status, output, tokens, err = [], "complete", None, 0, None
        try:
            async for ev in run_workflow(wf, req.trigger, secrets, interactive=True, owner=owner):
                ev = red(ev)  # never stream a secret back to the UI
                events.append(ev)
                if ev.get("type") == "node":
                    if ev.get("tokens"):
                        tokens += ev["tokens"]
                    if ev.get("status") == "error":
                        status, err = "error", ev.get("error")
                elif ev.get("type") == "done":
                    output = ev.get("output")
                yield f"data: {json.dumps(ev)}\n\n"
                await asyncio.sleep(0)  # flush
        except Exception as ex:
            status, err = "error", str(ex)
            yield f"data: {json.dumps({'type': 'error', 'error': str(ex)})}\n\n"
        finally:
            try:
                db.log_run(wf.get("id"), owner, "editor",
                           {"status": status, "output": output, "tokens": tokens or None,
                            "error": err, "ms": int((time.time() - t0) * 1000),
                            "started_at": started, "events": events})
            except Exception:
                pass
            try:
                n = await foundry.emit_spend(events, wf.get("name"))
                if n:
                    yield f"data: {json.dumps({'type': 'foundry', 'spendguard_events': n})}\n\n"
            except Exception:
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
