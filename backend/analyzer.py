"""Workflow analyzer + optimizer — the AI-native layer (Phase 4).

Three honest capabilities:
  1. Quality analysis   — deterministic static checks over the graph (reliability,
     structure, security, cost hygiene). Every finding points at a node and severity.
  2. Performance recs   — data-driven, computed from THIS workflow's real run history
     (per-node latency / cost / error-rate from logged events). No history → no perf recs.
  3. Auto-optimize      — applies only SAFE, behavior-preserving fixes (timeouts, retries,
     a fallback route, a missing End node). It never silently swaps a model or edits a
     prompt — those change output quality, so they stay as recommendations you apply.
"""
import re
import copy
import pricing

LLM_NODES = {"llm", "summarizer", "classifier", "translator", "extractor", "foreach"}
NET_NODES = {"http", "rag_query", "memory_recall", "prompt_run"}
FRONTIER = ("opus", "gpt-5", "sonnet", "gemini-2.5-pro", "claude-3-opus")
SEV_WEIGHT = {"high": 15, "medium": 8, "low": 3}

# crude secret sniffers — a literal key/token pasted into a field instead of {{secrets.*}}
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
    r"gh[posu]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)


def _txt(v):
    return v if isinstance(v, str) else ""


def _model_of(node):
    d = node.get("data") or {}
    return str(d.get("model") or "").strip()


def _adjacency(wf):
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    out, inc = {nid: [] for nid in nodes}, {nid: [] for nid in nodes}
    for e in wf.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in out:
            out[s].append(t)
        if t in inc:
            inc[t].append(s)
    return nodes, out, inc


def analyze(wf, node_stats=None):
    """Return {score, checks[], recommendations[], node_stats, summary}."""
    node_stats = node_stats or {}
    nodes, out, inc = _adjacency(wf)
    checks = []

    def add(sev, cid, title, detail, node_id=None, fixable=False):
        checks.append({"id": cid, "severity": sev, "title": title, "detail": detail,
                       "node_id": node_id, "fixable": fixable})

    starts = [nid for nid, n in nodes.items() if n.get("type") == "start"]
    ends = [nid for nid, n in nodes.items() if n.get("type") == "end"]

    # --- structure ---
    if not starts:
        add("high", "no_start", "No Start node", "Add a Start node so the workflow has an entry point.")
    if not ends:
        add("low", "no_end", "No End node", "Add an End node to make the workflow's final output explicit.", fixable=True)

    # reachability from the first start
    reachable = set()
    if starts:
        stack = [starts[0]]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            stack.extend(out.get(cur, []))
    for nid, n in nodes.items():
        if n.get("type") == "start":
            continue
        if starts and nid not in reachable:
            add("medium", "unreachable", "Unreachable node",
                f"'{_label(n)}' can't be reached from Start — it will never run.", node_id=nid)
        elif n.get("type") != "end" and not out.get(nid):
            add("low", "dead_end", "Dead-end node",
                f"'{_label(n)}' has no outgoing connection, so its output is discarded.", node_id=nid)

    # --- per-node reliability / security / cost ---
    for nid, n in nodes.items():
        t = n.get("type")
        d = n.get("data") or {}
        # hardcoded secrets
        blob = " ".join(_txt(d.get(k)) for k in ("prompt", "system", "template", "url", "body", "variables", "question", "query"))
        if isinstance(d.get("headers"), dict):
            blob += " " + " ".join(f"{k}:{v}" for k, v in d["headers"].items())
        if _SECRET_RE.search(blob):
            add("high", "hardcoded_secret", "Hardcoded credential",
                f"'{_label(n)}' looks like it contains a literal API key/token. Move it to the Secrets vault and reference it as {{{{secrets.NAME}}}}.", node_id=nid)
        # reliability on LLM + network nodes
        if t in LLM_NODES or t in NET_NODES:
            if not int(d.get("timeout_s") or 0):
                add("low", "no_timeout", "No timeout",
                    f"'{_label(n)}' has no timeout — a hung call blocks the whole run.", node_id=nid, fixable=True)
            if not int(d.get("retries") or 0):
                add("low", "no_retries", "No retries",
                    f"'{_label(n)}' won't retry a transient failure. One retry with backoff is cheap insurance.", node_id=nid, fixable=True)
        if t == "llm" and not _txt(d.get("fallback")).strip():
            add("low", "no_fallback", "No fallback model",
                f"'{_label(n)}' has no fallback — if the model errors the run fails. Add a fallback route.", node_id=nid, fixable=True)
        # cost hygiene — frontier model flagged only as advisory
        m = _model_of(n).lower()
        if t in LLM_NODES and any(h in m for h in FRONTIER):
            add("low", "frontier_model", "Premium model",
                f"'{_label(n)}' uses a frontier model ({_model_of(n)}). If the task is simple, a cheaper tier (e.g. a mini/flash model) may match quality at a fraction of the cost.", node_id=nid)

    # --- performance recommendations from real run history ---
    recommendations = _perf_recs(nodes, node_stats)

    score = max(0, 100 - sum(SEV_WEIGHT.get(c["severity"], 0) for c in checks))
    order = {"high": 0, "medium": 1, "low": 2}
    checks.sort(key=lambda c: order.get(c["severity"], 3))
    fixable = sum(1 for c in checks if c.get("fixable"))
    return {
        "score": score,
        "checks": checks,
        "recommendations": recommendations,
        "node_stats": node_stats,
        "summary": {"issues": len(checks), "fixable": fixable,
                    "high": sum(1 for c in checks if c["severity"] == "high"),
                    "runs_analyzed": max((s["runs"] for s in node_stats.values()), default=0)},
    }


def _label(n):
    d = n.get("data") or {}
    return d.get("label") or n.get("type") or n.get("id")


def _perf_recs(nodes, node_stats):
    recs = []
    if not node_stats:
        return recs
    ranked_cost = sorted(node_stats.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    total_cost = sum(s["cost"] for s in node_stats.values())
    top_id, top = ranked_cost[0]
    if total_cost > 0 and top["cost"] / total_cost > 0.5 and top["cost"] > 0.001:
        n = nodes.get(top_id, {})
        recs.append({"type": "cost_hotspot", "node_id": top_id,
                     "title": f"'{_label(n)}' drives {round(top['cost']/total_cost*100)}% of run cost",
                     "detail": f"${round(top['cost'],4)} across {top['runs']} run(s). Try a cheaper model, cache repeated inputs, or trim the prompt."})
    slow = max(node_stats.items(), key=lambda kv: kv[1]["ms_avg"], default=None)
    if slow and slow[1]["ms_avg"] > 4000:
        n = nodes.get(slow[0], {})
        recs.append({"type": "latency", "node_id": slow[0],
                     "title": f"'{_label(n)}' is slow (~{round(slow[1]['ms_avg']/1000,1)}s avg)",
                     "detail": "Consider a faster model, a lower max_tokens, or running independent branches in parallel."})
    for nid, s in node_stats.items():
        if s["runs"] >= 3 and s["errors"] / s["runs"] > 0.2:
            n = nodes.get(nid, {})
            recs.append({"type": "flaky", "node_id": nid,
                         "title": f"'{_label(n)}' fails {round(s['errors']/s['runs']*100)}% of the time",
                         "detail": f"{s['errors']}/{s['runs']} runs errored. Add retries/timeout, or a fallback model."})
    return recs


def optimize(wf):
    """Apply only safe, behavior-preserving hardening. Returns {workflow, applied[]}."""
    wf = copy.deepcopy(wf)
    applied = []
    nodes = wf.get("nodes", [])
    for n in nodes:
        t = n.get("type")
        d = n.setdefault("data", {})
        lbl = _label(n)
        if t in LLM_NODES or t in NET_NODES:
            if not int(d.get("timeout_s") or 0):
                d["timeout_s"] = 120 if t in LLM_NODES else 60
                applied.append(f"Set {d['timeout_s']}s timeout on '{lbl}'")
            if not int(d.get("retries") or 0):
                d["retries"] = 1
                applied.append(f"Enabled 1 retry on '{lbl}'")
        if t == "llm" and not _txt(d.get("fallback")).strip():
            m = str(d.get("model") or "").strip().lower()
            if m and m != "auto":
                d["fallback"] = "auto"  # a failing specific model routes to the relay's best available
                applied.append(f"Added fallback (auto) on '{lbl}'")
    # add an End node if missing, wired from the last terminal node
    ids = {n["id"] for n in nodes}
    if not any(n.get("type") == "end" for n in nodes) and nodes:
        _nodes, out, _inc = _adjacency(wf)
        terminals = [nid for nid in ids if not out.get(nid) and _nodes[nid].get("type") != "start"]
        anchor = terminals[0] if terminals else (nodes[-1]["id"] if nodes else None)
        if anchor:
            import uuid
            eid = "end_" + uuid.uuid4().hex[:6]
            # place it to the right of the anchor
            ax = next((n.get("position", {}).get("x", 0) for n in nodes if n["id"] == anchor), 0)
            ay = next((n.get("position", {}).get("y", 0) for n in nodes if n["id"] == anchor), 0)
            nodes.append({"id": eid, "type": "end", "position": {"x": ax + 260, "y": ay},
                          "data": {"label": "End"}})
            wf.setdefault("edges", []).append({"id": f"e_{anchor}_{eid}", "source": anchor, "target": eid})
            applied.append("Added an End node to capture the final output")
    return {"workflow": wf, "applied": applied, "count": len(applied)}
