"""ZoidLab AI Workflow Builder — API.
FastAPI + SQLite + in-process DAG executor. LLM nodes route through the Nyquest relay."""
import json
import time
import asyncio
import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

import db
from schema import Workflow, RunRequest
from executor import run_workflow
from llm import list_models, set_relay_auth
from flowsmith import generate as flowsmith_generate
from auth import relay_key_from_cookie, session_payload
import vault
from pydantic import BaseModel

app = FastAPI(title="ZoidLab Workflow Builder", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init()


def owner_of(request: Request):
    """Workflow owner = the Nyquest user id from the session (None = local sandbox)."""
    p = session_payload(request.cookies.get("zb_session"))
    return p.get("sub") if p else None


@app.get("/api/health")
def health():
    return {"ok": True, "service": "zoidlab-builder"}


@app.get("/api/models")
async def models():
    # "auto" = let the Nyquest relay route to the best model
    return {"models": ["auto", *await list_models()]}


@app.get("/api/workflows")
def workflows(request: Request):
    return {"workflows": db.list_workflows(owner_of(request))}


@app.get("/api/workflows/{wid}")
def get_workflow(wid: str, request: Request):
    wf = db.get_workflow(wid, owner_of(request))
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@app.post("/api/workflows")
def save_workflow(wf: Workflow, request: Request):
    r = db.save_workflow(wf.model_dump(), owner_of(request))
    if not r:
        raise HTTPException(409, "Workflow id belongs to another user")
    return r


@app.delete("/api/workflows/{wid}")
def delete_workflow(wid: str, request: Request):
    db.delete_workflow(wid, owner_of(request))
    return {"ok": True}


class RenameRequest(BaseModel):
    name: str


@app.patch("/api/workflows/{wid}")
def rename_workflow(wid: str, req: RenameRequest, request: Request):
    r = db.rename_workflow(wid, req.name.strip() or "Untitled workflow", owner_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


@app.post("/api/workflows/{wid}/clone")
def clone_workflow(wid: str, request: Request):
    r = db.clone_workflow(wid, owner_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


# --- versioning ---
@app.get("/api/workflows/{wid}/versions")
def list_versions(wid: str, request: Request):
    v = db.list_versions(wid, owner_of(request))
    if v is None:
        raise HTTPException(404, "Workflow not found")
    return {"versions": v}


class SnapshotRequest(BaseModel):
    label: str | None = None


@app.post("/api/workflows/{wid}/snapshot")
def snapshot_workflow(wid: str, req: SnapshotRequest, request: Request):
    r = db.snapshot_workflow(wid, (req.label or "").strip(), owner_of(request))
    if not r:
        raise HTTPException(404, "Workflow not found")
    return r


@app.get("/api/versions/{vid}")
def get_version(vid: str, request: Request):
    v = db.get_version(vid, owner_of(request))
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@app.post("/api/versions/{vid}/restore")
def restore_version(vid: str, request: Request):
    wf = db.restore_version(vid, owner_of(request))
    if not wf:
        raise HTTPException(404, "Version not found")
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
    return db.run_stats(owner_of(request))


@app.get("/api/runs")
def runs(request: Request, workflow_id: str | None = None):
    return {"runs": db.list_runs(owner_of(request), workflow_id)}


@app.get("/api/runs/{rid}")
def run_detail(rid: str, request: Request):
    r = db.get_run(rid, owner_of(request))
    if not r:
        raise HTTPException(404, "Run not found")
    return r


# --- deployment (deploy workflow as a webhook) ---
@app.get("/api/workflows/{wid}/deployment")
def get_deployment(wid: str, request: Request):
    d = db.get_deployment(wid, owner_of(request))
    if d is None:
        raise HTTPException(404, "Workflow not found")
    return d


@app.post("/api/workflows/{wid}/deploy")
def deploy(wid: str, request: Request):
    p = session_payload(request.cookies.get("zb_session"))
    d = db.deploy_workflow(wid, owner_of(request), p.get("rk") if p else None)
    if d is None:
        raise HTTPException(404, "Workflow not found")
    return d


@app.delete("/api/workflows/{wid}/deploy")
def undeploy(wid: str, request: Request):
    if not db.undeploy_workflow(wid, owner_of(request)):
        raise HTTPException(404, "Workflow not found")
    return {"ok": True}


async def _collect(wf: dict, trigger: dict, secrets: dict) -> dict:
    """Run a workflow to completion, collecting (redacted) events into a summary."""
    started = datetime.datetime.utcnow().isoformat() + "Z"
    t0 = time.time()
    red = vault.make_redactor(secrets.values())
    events, status, output, tokens, err = [], "complete", None, 0, None
    async for ev in run_workflow(wf, trigger, secrets):
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
    res = await _collect(dep["workflow"], trigger, db.secrets_map(dep["owner"]))
    db.log_run(dep["workflow"]["id"], dep["owner"], "webhook", res)
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


@app.post("/api/run")
async def run(req: RunRequest, request: Request):
    """Execute a workflow, streaming node status events as SSE."""
    wf = req.workflow.model_dump()
    auth = relay_key_from_cookie(request.cookies.get("zb_session"))
    owner = owner_of(request)
    secrets = db.secrets_map(owner)
    red = vault.make_redactor(secrets.values())

    async def gen():
        set_relay_auth(auth)  # bill the logged-in user's own Nyquest wallet
        started = datetime.datetime.utcnow().isoformat() + "Z"
        t0 = time.time()
        events, status, output, tokens, err = [], "complete", None, 0, None
        try:
            async for ev in run_workflow(wf, req.trigger, secrets):
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

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
