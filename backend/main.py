"""ZoidLab AI Workflow Builder — API.
FastAPI + SQLite + in-process DAG executor. LLM nodes route through the Nyquest relay."""
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import db
from schema import Workflow, RunRequest
from executor import run_workflow
from llm import list_models, set_relay_auth
from flowsmith import generate as flowsmith_generate
from auth import relay_key_from_cookie, session_payload
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

    async def gen():
        set_relay_auth(auth)  # bill the logged-in user's own Nyquest wallet
        try:
            async for ev in run_workflow(wf, req.trigger):
                yield f"data: {json.dumps(ev)}\n\n"
                await asyncio.sleep(0)  # flush
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'error': str(ex)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
