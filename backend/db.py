"""SQLite persistence for workflows. Lean by design — swaps to Postgres later
without touching callers (all access goes through these functions)."""
import os
import json
import uuid
import sqlite3
import datetime

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "builder.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                graph TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                name TEXT NOT NULL,
                graph TEXT NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_versions_wf ON versions(workflow_id, created_at)")


def list_workflows():
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, updated_at FROM workflows ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_workflow(wid):
    with _conn() as c:
        row = c.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            return None
        g = json.loads(row["graph"])
        g["id"] = row["id"]
        g["name"] = row["name"]
        g["updated_at"] = row["updated_at"]
        return g


AUTO_VERSION_GAP = 120  # seconds — auto-snapshot at most this often per workflow


def save_workflow(wf: dict):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    name = wf.get("name", "Untitled workflow")
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    with _conn() as c:
        c.execute(
            """INSERT INTO workflows (id, name, graph, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 graph=excluded.graph, updated_at=excluded.updated_at""",
            (wf["id"], name, graph, now),
        )
    _maybe_auto_version(wf["id"], name, graph, now)
    return {"id": wf["id"], "updated_at": now}


def _maybe_auto_version(wid, name, graph, now):
    """Snapshot into history, throttled: skip if unchanged from the latest
    version or if the latest auto-version is younger than AUTO_VERSION_GAP."""
    with _conn() as c:
        latest = c.execute(
            "SELECT graph, label, created_at FROM versions WHERE workflow_id=? ORDER BY created_at DESC LIMIT 1",
            (wid,),
        ).fetchone()
    if latest:
        if latest["graph"] == graph:
            return
        try:
            age = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(latest["created_at"].rstrip("Z"))).total_seconds()
        except Exception:
            age = AUTO_VERSION_GAP + 1
        # only throttle consecutive AUTO versions; always keep a fresh point after a labeled one
        if latest["label"] is None and age < AUTO_VERSION_GAP:
            return
    _insert_version(wid, name, graph, None, now)


def _insert_version(wid, name, graph, label, now):
    with _conn() as c:
        c.execute(
            "INSERT INTO versions (id, workflow_id, name, graph, label, created_at) VALUES (?,?,?,?,?,?)",
            ("v_" + uuid.uuid4().hex[:10], wid, name, graph, label, now),
        )


def snapshot_workflow(wid, label):
    wf = get_workflow(wid)
    if not wf:
        return None
    now = datetime.datetime.utcnow().isoformat() + "Z"
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    _insert_version(wid, wf.get("name", "Untitled"), graph, label or "Manual save", now)
    return {"ok": True, "created_at": now}


def list_versions(wid):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, label, created_at, graph FROM versions WHERE workflow_id=? ORDER BY created_at DESC",
            (wid,),
        ).fetchall()
    out = []
    for r in rows:
        g = json.loads(r["graph"])
        out.append({
            "id": r["id"], "name": r["name"], "label": r["label"],
            "created_at": r["created_at"],
            "nodes": len(g.get("nodes", [])), "edges": len(g.get("edges", [])),
        })
    return out


def get_version(vid):
    with _conn() as c:
        r = c.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
    if not r:
        return None
    g = json.loads(r["graph"])
    g["id"] = r["workflow_id"]
    g["name"] = r["name"]
    return g


def restore_version(vid):
    with _conn() as c:
        r = c.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
    if not r:
        return None
    g = json.loads(r["graph"])
    now = datetime.datetime.utcnow().isoformat() + "Z"
    # snapshot the pre-restore state's version chain marker, then set current
    save_workflow({"id": r["workflow_id"], "name": r["name"], "nodes": g.get("nodes", []), "edges": g.get("edges", [])})
    _insert_version(r["workflow_id"], r["name"], r["graph"],
                    f"Restored from {r['created_at'][:16].replace('T', ' ')}", now)
    wf = get_workflow(r["workflow_id"])
    return wf


def delete_workflow(wid):
    with _conn() as c:
        c.execute("DELETE FROM workflows WHERE id=?", (wid,))
        c.execute("DELETE FROM versions WHERE workflow_id=?", (wid,))


def rename_workflow(wid, name):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        c.execute("UPDATE workflows SET name=?, updated_at=? WHERE id=?", (name, now, wid))
    return {"id": wid, "name": name, "updated_at": now}


def clone_workflow(wid):
    src = get_workflow(wid)
    if not src:
        return None
    new = {
        "id": "wf_" + uuid.uuid4().hex[:8],
        "name": src.get("name", "Untitled") + " (copy)",
        "nodes": src.get("nodes", []),
        "edges": src.get("edges", []),
    }
    save_workflow(new)
    return {"id": new["id"], "name": new["name"]}
