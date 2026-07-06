"""In-process DAG executor. Walks the graph from the start node(s), runs each
node, and yields live status events (consumed as SSE by the frontend).

Prototype scope: linear flows + single-branch decisions. Merge/fan-in and
parallel Celery execution come in a later phase."""
import time
import json
import datetime
from collections import deque
from nodes import exec_node


def _preview(v, limit=4000):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


async def run_workflow(wf: dict, trigger: dict):
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    edges = wf.get("edges", [])

    out_edges: dict[str, list] = {}
    in_count: dict[str, int] = {}
    for e in edges:
        out_edges.setdefault(e["source"], []).append(e)
        in_count[e["target"]] = in_count.get(e["target"], 0) + 1

    starts = [n["id"] for n in wf.get("nodes", []) if n["type"] == "start"]
    if not starts:
        starts = [nid for nid in nodes if in_count.get(nid, 0) == 0]
    if not starts:
        yield {"type": "error", "error": "No start node — add a Start node or an entry point."}
        return

    ctx = {
        "vars": dict(trigger or {}),
        "trigger": dict(trigger or {}),
        "nodes": {},
        "previous": {"output": None},
        "now": datetime.datetime.utcnow().isoformat() + "Z",
        "today": datetime.date.today().isoformat(),
        "workflow": {"id": wf.get("id"), "name": wf.get("name")},
    }

    node_input = {nid: (trigger or {}) for nid in starts}
    q = deque(starts)
    visited: set[str] = set()
    last_output = None

    yield {"type": "start", "nodes": list(nodes.keys())}

    while q:
        nid = q.popleft()
        if nid in visited or nid not in nodes:
            continue
        visited.add(nid)
        node = nodes[nid]
        ctx["previous"] = {"output": node_input.get(nid)}

        yield {"type": "node", "nodeId": nid, "status": "running"}
        t0 = time.time()
        try:
            result = await exec_node(node, ctx)
            ms = int((time.time() - t0) * 1000)
            output = result.get("output")
            ctx["nodes"][nid] = {"output": output}
            last_output = output
            yield {
                "type": "node", "nodeId": nid, "status": "complete",
                "output": _preview(output), "ms": ms,
                "tokens": result.get("tokens"), "meta": result.get("meta"),
            }
            branch = result.get("branch")
            for e in out_edges.get(nid, []):
                if branch is not None and e.get("sourceHandle") != branch:
                    continue
                node_input[e["target"]] = output
                q.append(e["target"])
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            yield {"type": "node", "nodeId": nid, "status": "error",
                   "error": str(ex), "ms": ms}
            # stop this branch; other queued branches continue

    yield {"type": "done", "output": _preview(last_output)}
