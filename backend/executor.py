"""In-process DAG executor — dataflow readiness model.

A node runs once all its incoming edges are resolved (delivered or dead) and at
least one delivered. Non-chosen branches (decision/switch/classifier/approval)
kill their edges, and death propagates, so downstream nodes fire correctly.
Supports linear + branching + fan-in (merge) + per-node retry/timeout.
Yields live status events (consumed as SSE)."""
import time
import json
import uuid
import asyncio
import datetime
from collections import deque
from nodes import exec_node, render

# Pending human-approval futures, keyed by an opaque token.
_pending: dict = {}


def resolve_approval(token: str, decision: str) -> bool:
    fut = _pending.get(token)
    if fut and not fut.done():
        fut.set_result(decision)
        return True
    return False


def _preview(v, limit=4000):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


async def _run_node(node, ctx):
    """exec_node with per-node timeout + retry/backoff (from node data)."""
    data = node.get("data") or {}
    try:
        timeout = float(data.get("timeout_s") or 0)
    except Exception:
        timeout = 0
    try:
        retries = int(data.get("retries") or 0)
    except Exception:
        retries = 0
    attempt = 0
    while True:
        try:
            if timeout > 0:
                return await asyncio.wait_for(exec_node(node, ctx), timeout)
            return await exec_node(node, ctx)
        except Exception:
            if attempt >= retries:
                raise
            attempt += 1
            await asyncio.sleep(min(2 ** attempt, 8))


async def run_workflow(wf: dict, trigger: dict, secrets: dict | None = None, interactive: bool = False):
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    edges = wf.get("edges", [])
    in_edges: dict[str, list] = {}
    out_edges: dict[str, list] = {}
    for e in edges:
        out_edges.setdefault(e["source"], []).append(e)
        in_edges.setdefault(e["target"], []).append(e)

    starts = [n["id"] for n in wf.get("nodes", []) if n["type"] == "start"]
    if not starts:
        starts = [nid for nid in nodes if not in_edges.get(nid)]
    if not starts:
        yield {"type": "error", "error": "No start node — add a Start node or an entry point."}
        return

    ctx = {
        "vars": dict(trigger or {}),
        "trigger": dict(trigger or {}),
        "secrets": dict(secrets or {}),
        "nodes": {},
        "previous": {"output": None},
        "now": datetime.datetime.utcnow().isoformat() + "Z",
        "today": datetime.date.today().isoformat(),
        "workflow": {"id": wf.get("id"), "name": wf.get("name")},
    }

    estatus = {e["id"]: "pending" for e in edges}
    node_inputs: dict[str, list] = {}
    done: set = set()
    dead: set = set()
    ready: deque = deque()
    inq: set = set()

    for s in starts:
        node_inputs[s] = [trigger or {}]
        ready.append(s)
        inq.add(s)

    def _check(nid):
        if nid in done or nid in dead or nid in inq:
            return
        ins = in_edges.get(nid, [])
        if not ins:
            return
        if all(estatus[e["id"]] != "pending" for e in ins):
            if any(estatus[e["id"]] == "delivered" for e in ins):
                ready.append(nid)
                inq.add(nid)
            else:
                dead.add(nid)
                for oe in out_edges.get(nid, []):
                    estatus[oe["id"]] = "dead"
                    _check(oe["target"])

    def deliver(e, value):
        estatus[e["id"]] = "delivered"
        node_inputs.setdefault(e["target"], []).append(value)
        _check(e["target"])

    def kill(e):
        estatus[e["id"]] = "dead"
        _check(e["target"])

    yield {"type": "start", "nodes": list(nodes.keys())}
    last_output = None

    while ready:
        nid = ready.popleft()
        inq.discard(nid)
        if nid in done or nid in dead or nid not in nodes:
            continue
        node = nodes[nid]
        inputs = node_inputs.get(nid, [])
        # merge sees every delivered input; other nodes get the most recent one
        ctx["previous"] = {"output": inputs if node["type"] == "merge" else (inputs[-1] if inputs else None)}

        yield {"type": "node", "nodeId": nid, "status": "running"}
        t0 = time.time()
        branch = None
        output = None
        try:
            if node["type"] == "approval":
                data = node.get("data") or {}
                msg = render(str(data.get("message", "Approve to continue?")), ctx)
                try:
                    to = float(data.get("timeout_s") or 300)
                except Exception:
                    to = 300
                if interactive:
                    token = uuid.uuid4().hex
                    fut = asyncio.get_event_loop().create_future()
                    _pending[token] = fut
                    yield {"type": "approval", "nodeId": nid, "message": msg, "token": token}
                    try:
                        decision = await asyncio.wait_for(fut, to)
                    except asyncio.TimeoutError:
                        decision = data.get("on_timeout") or "reject"
                    finally:
                        _pending.pop(token, None)
                else:
                    decision = data.get("auto") or "reject"
                ok = str(decision).lower() in ("approve", "approved", "true", "yes", "1")
                branch = "approved" if ok else "rejected"
                output = inputs[-1] if inputs else None
                ms = int((time.time() - t0) * 1000)
                ctx["nodes"][nid] = {"output": output}
                last_output = output
                yield {"type": "node", "nodeId": nid, "status": "complete",
                       "output": _preview(output), "ms": ms, "meta": branch}
            else:
                result = await _run_node(node, ctx)
                ms = int((time.time() - t0) * 1000)
                output = result.get("output")
                branch = result.get("branch")
                ctx["nodes"][nid] = {"output": output}
                last_output = output
                yield {"type": "node", "nodeId": nid, "status": "complete",
                       "output": _preview(output), "ms": ms,
                       "tokens": result.get("tokens"), "meta": result.get("meta")}
            done.add(nid)
            for e in out_edges.get(nid, []):
                if branch is not None and e.get("sourceHandle") != branch:
                    kill(e)
                else:
                    deliver(e, output)
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            done.add(nid)
            yield {"type": "node", "nodeId": nid, "status": "error", "error": str(ex), "ms": ms}
            for e in out_edges.get(nid, []):
                kill(e)

    yield {"type": "done", "output": _preview(last_output)}
