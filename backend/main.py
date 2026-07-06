"""ZoidLab AI Workflow Builder — API.
FastAPI + SQLite + in-process DAG executor. LLM nodes route through the Nyquest relay."""
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import db
from schema import Workflow, RunRequest
from executor import run_workflow
from llm import list_models

app = FastAPI(title="ZoidLab Workflow Builder", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "zoidlab-builder"}


@app.get("/api/models")
async def models():
    return {"models": await list_models()}


@app.get("/api/workflows")
def workflows():
    return {"workflows": db.list_workflows()}


@app.get("/api/workflows/{wid}")
def get_workflow(wid: str):
    wf = db.get_workflow(wid)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@app.post("/api/workflows")
def save_workflow(wf: Workflow):
    return db.save_workflow(wf.model_dump())


@app.delete("/api/workflows/{wid}")
def delete_workflow(wid: str):
    db.delete_workflow(wid)
    return {"ok": True}


@app.post("/api/run")
async def run(req: RunRequest):
    """Execute a workflow, streaming node status events as SSE."""
    wf = req.workflow.model_dump()

    async def gen():
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
