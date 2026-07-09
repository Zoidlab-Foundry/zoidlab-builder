"""SQLite persistence for workflows. Lean by design — swaps to Postgres later
without touching callers (all access goes through these functions).

Ownership: every workflow row carries `owner` (the Nyquest user id from the
session). All reads/writes are scoped to the caller's owner; `owner=None`
(sessionless/local) is its own sandbox — the public path is always gated."""
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
        # ownership migration (idempotent)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(workflows)")]
        if "owner" not in cols:
            c.execute("ALTER TABLE workflows ADD COLUMN owner TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_workflows_owner ON workflows(owner, updated_at)")


def _owned(c, wid, owner):
    """The workflow row iff it belongs to `owner` (NULL-safe)."""
    return c.execute(
        "SELECT * FROM workflows WHERE id=? AND owner IS ?", (wid, owner)
    ).fetchone()


def list_workflows(owner=None):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, updated_at FROM workflows WHERE owner IS ? ORDER BY updated_at DESC",
            (owner,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_workflow(wid, owner=None):
    with _conn() as c:
        row = _owned(c, wid, owner)
        if not row:
            return None
        g = json.loads(row["graph"])
        g["id"] = row["id"]
        g["name"] = row["name"]
        g["updated_at"] = row["updated_at"]
        return g


AUTO_VERSION_GAP = 120  # seconds — auto-snapshot at most this often per workflow


def save_workflow(wf: dict, owner=None):
    """Upsert scoped to owner. Returns None if the id exists under a different
    owner (prevents cross-user id collisions/overwrites)."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    name = wf.get("name", "Untitled workflow")
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    with _conn() as c:
        existing = c.execute("SELECT owner FROM workflows WHERE id=?", (wf["id"],)).fetchone()
        if existing is not None and existing["owner"] != owner:
            return None
        c.execute(
            """INSERT INTO workflows (id, name, graph, updated_at, owner) VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 graph=excluded.graph, updated_at=excluded.updated_at""",
            (wf["id"], name, graph, now, owner),
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
        if latest["label"] is None and age < AUTO_VERSION_GAP:
            return
    _insert_version(wid, name, graph, None, now)


def _insert_version(wid, name, graph, label, now):
    with _conn() as c:
        c.execute(
            "INSERT INTO versions (id, workflow_id, name, graph, label, created_at) VALUES (?,?,?,?,?,?)",
            ("v_" + uuid.uuid4().hex[:10], wid, name, graph, label, now),
        )


def delete_workflow(wid, owner=None):
    with _conn() as c:
        if not _owned(c, wid, owner):
            return False
        c.execute("DELETE FROM workflows WHERE id=?", (wid,))
        c.execute("DELETE FROM versions WHERE workflow_id=?", (wid,))
    return True


def rename_workflow(wid, name, owner=None):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        if not _owned(c, wid, owner):
            return None
        c.execute("UPDATE workflows SET name=?, updated_at=? WHERE id=?", (name, now, wid))
    return {"id": wid, "name": name, "updated_at": now}


def clone_workflow(wid, owner=None):
    src = get_workflow(wid, owner)
    if not src:
        return None
    new = {
        "id": "wf_" + uuid.uuid4().hex[:8],
        "name": src.get("name", "Untitled") + " (copy)",
        "nodes": src.get("nodes", []),
        "edges": src.get("edges", []),
    }
    save_workflow(new, owner)
    return {"id": new["id"], "name": new["name"]}


def snapshot_workflow(wid, label, owner=None):
    wf = get_workflow(wid, owner)
    if not wf:
        return None
    now = datetime.datetime.utcnow().isoformat() + "Z"
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    _insert_version(wid, wf.get("name", "Untitled"), graph, label or "Manual save", now)
    return {"ok": True, "created_at": now}


def list_versions(wid, owner=None):
    with _conn() as c:
        if not _owned(c, wid, owner):
            return None
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


def _version_row(vid, owner):
    """Version row iff its parent workflow belongs to owner."""
    with _conn() as c:
        return c.execute(
            """SELECT v.* FROM versions v JOIN workflows w ON w.id = v.workflow_id
               WHERE v.id=? AND w.owner IS ?""",
            (vid, owner),
        ).fetchone()


def get_version(vid, owner=None):
    r = _version_row(vid, owner)
    if not r:
        return None
    g = json.loads(r["graph"])
    g["id"] = r["workflow_id"]
    g["name"] = r["name"]
    return g


def restore_version(vid, owner=None):
    r = _version_row(vid, owner)
    if not r:
        return None
    g = json.loads(r["graph"])
    now = datetime.datetime.utcnow().isoformat() + "Z"
    save_workflow({"id": r["workflow_id"], "name": r["name"], "nodes": g.get("nodes", []), "edges": g.get("edges", [])}, owner)
    _insert_version(r["workflow_id"], r["name"], r["graph"],
                    f"Restored from {r['created_at'][:16].replace('T', ' ')}", now)
    return get_workflow(r["workflow_id"], owner)
