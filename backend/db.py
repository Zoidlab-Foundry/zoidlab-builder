"""SQLite persistence for workflows. Lean by design — swaps to Postgres later
without touching callers (all access goes through these functions)."""
import os
import json
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


def save_workflow(wf: dict):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    with _conn() as c:
        c.execute(
            """INSERT INTO workflows (id, name, graph, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 graph=excluded.graph, updated_at=excluded.updated_at""",
            (wf["id"], wf.get("name", "Untitled workflow"), graph, now),
        )
    return {"id": wf["id"], "updated_at": now}


def delete_workflow(wid):
    with _conn() as c:
        c.execute("DELETE FROM workflows WHERE id=?", (wid,))
