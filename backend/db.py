"""SQLite persistence for workflows. Lean by design — swaps to Postgres later
without touching callers (all access goes through these functions).

Ownership: every workflow row carries `owner` (the Nyquest user id from the
session). All reads/writes are scoped to the caller's owner; `owner=None`
(sessionless/local) is its own sandbox — the public path is always gated."""
import os
import json
import uuid
import secrets as _secrets
import sqlite3
import datetime
import vault

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
        # ownership + org migration (idempotent)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(workflows)")]
        if "owner" not in cols:
            c.execute("ALTER TABLE workflows ADD COLUMN owner TEXT")
        if "org_id" not in cols:
            c.execute("ALTER TABLE workflows ADD COLUMN org_id TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_workflows_owner ON workflows(owner, updated_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_workflows_org ON workflows(org_id, updated_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                token TEXT PRIMARY KEY,
                workflow_id TEXT UNIQUE NOT NULL,
                relay_key TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                owner TEXT,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ms INTEGER,
                tokens INTEGER,
                output TEXT,
                error TEXT,
                events TEXT
            )
        """)
        rcols = [r["name"] for r in c.execute("PRAGMA table_info(runs)")]
        if "cost_usd" not in rcols:
            c.execute("ALTER TABLE runs ADD COLUMN cost_usd REAL")
        if "org_id" not in rcols:
            c.execute("ALTER TABLE runs ADD COLUMN org_id TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_runs_wf ON runs(workflow_id, started_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_runs_org ON runs(org_id, started_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                value_enc TEXT NOT NULL,
                preview TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (owner, name)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                owner TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner, workflow_id, key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                workflow_id TEXT PRIMARY KEY,
                owner TEXT,
                cron TEXT NOT NULL,
                relay_key TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run TEXT,
                last_run TEXT,
                created_at TEXT NOT NULL
            )
        """)
    import orgs  # lazy (orgs imports db) — create org/member/audit tables
    orgs.init()


# --- access control (personal + org RBAC) --------------------------------
ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}


def _can(role, need):
    return role is not None and ROLE_RANK.get(role, 0) >= ROLE_RANK[need]


def _access(c, wid, ctx):
    """(row, role) for a workflow under access context ctx={'user','orgs':{oid:role}}.
    Personal workflows (org_id NULL) grant role 'owner' to their owner. Org workflows
    grant the caller's membership role. (None, None) if no access."""
    ctx = ctx or {}
    row = c.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row:
        return None, None
    if row["org_id"]:
        role = (ctx.get("orgs") or {}).get(row["org_id"])
        return (row, role) if role else (None, None)
    return (row, "owner") if row["owner"] == ctx.get("user") else (None, None)


def _owned(c, wid, owner):
    """The workflow row iff it belongs to `owner` (NULL-safe)."""
    return c.execute(
        "SELECT * FROM workflows WHERE id=? AND owner IS ?", (wid, owner)
    ).fetchone()


def list_workflows(ctx=None):
    """Personal workflows (owned + not in an org) plus every org workflow the caller can see."""
    ctx = ctx or {}
    user = ctx.get("user")
    org_roles = ctx.get("orgs") or {}
    org_ids = list(org_roles)
    with _conn() as c:
        q = "SELECT id, name, updated_at, org_id, owner FROM workflows WHERE (owner IS ? AND org_id IS NULL)"
        args = [user]
        if org_ids:
            q += " OR org_id IN (%s)" % ",".join("?" * len(org_ids))
            args += org_ids
        q += " ORDER BY updated_at DESC"
        rows = c.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["role"] = org_roles.get(r["org_id"]) if r["org_id"] else "owner"
        out.append(d)
    return out


def get_workflow(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row:
            return None
        g = json.loads(row["graph"])
        g["id"] = row["id"]
        g["name"] = row["name"]
        g["updated_at"] = row["updated_at"]
        g["org_id"] = row["org_id"]
        g["role"] = role
        return g


def get_workflow_raw(wid):
    """Bypass access control — for unattended runners (scheduler, webhook) whose token/
    schedule row IS the capability. Never exposed directly to an API caller."""
    with _conn() as c:
        row = c.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row:
        return None
    g = json.loads(row["graph"])
    g["id"] = row["id"]; g["name"] = row["name"]; g["org_id"] = row["org_id"]
    return g


AUTO_VERSION_GAP = 120  # seconds — auto-snapshot at most this often per workflow


def save_workflow(wf: dict, ctx=None):
    """Upsert. New workflows are personal (or placed in an org the caller can edit);
    updates require editor+ on the existing row. Returns None on a permission failure
    (id belongs to another user, or caller lacks edit rights in the org)."""
    ctx = ctx or {}
    user = ctx.get("user")
    now = datetime.datetime.utcnow().isoformat() + "Z"
    name = wf.get("name", "Untitled workflow")
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    with _conn() as c:
        existing = c.execute("SELECT owner, org_id FROM workflows WHERE id=?", (wf["id"],)).fetchone()
        if existing is not None:
            # update — enforce access, keep ownership/org fixed (moving is a separate op)
            _, role = _access(c, wf["id"], ctx)
            if not _can(role, "editor"):
                return None
            c.execute("UPDATE workflows SET name=?, graph=?, updated_at=? WHERE id=?",
                      (name, graph, now, wf["id"]))
        else:
            # create — optional org placement requires editor+ in that org
            org_id = wf.get("org_id") or None
            if org_id and not _can((ctx.get("orgs") or {}).get(org_id), "editor"):
                return None
            c.execute(
                "INSERT INTO workflows (id, name, graph, updated_at, owner, org_id) VALUES (?,?,?,?,?,?)",
                (wf["id"], name, graph, now, user, org_id),
            )
    _maybe_auto_version(wf["id"], name, graph, now)
    return {"id": wf["id"], "updated_at": now}


def move_workflow(wid, org_id, ctx=None):
    """Move a workflow to an org (or back to personal, org_id=None). Requires the caller
    be editor+ on the source and, if targeting an org, editor+ there."""
    ctx = ctx or {}
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return None
        if org_id and not _can((ctx.get("orgs") or {}).get(org_id), "editor"):
            return None
        new_owner = row["owner"] or ctx.get("user")  # keep creator; ensure set when leaving sandbox
        c.execute("UPDATE workflows SET org_id=?, owner=? WHERE id=?", (org_id or None, new_owner, wid))
    return {"id": wid, "org_id": org_id or None}


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


def delete_workflow(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        # personal owner can delete their own; in an org it takes admin+
        need = "owner" if (row and not row["org_id"]) else "admin"
        if not row or not _can(role, need):
            return False
        c.execute("DELETE FROM workflows WHERE id=?", (wid,))
        c.execute("DELETE FROM versions WHERE workflow_id=?", (wid,))
        c.execute("DELETE FROM deployments WHERE workflow_id=?", (wid,))
        c.execute("DELETE FROM runs WHERE workflow_id=?", (wid,))
        c.execute("DELETE FROM schedules WHERE workflow_id=?", (wid,))
    return True


# --- data store (persistent key/value, per owner+workflow) ---------------
def kv_get(owner, workflow_id, key):
    with _conn() as c:
        r = c.execute(
            "SELECT value FROM kv_store WHERE owner=? AND workflow_id=? AND key=?",
            (owner or "", workflow_id or "", key),
        ).fetchone()
        return r["value"] if r else None


def kv_set(owner, workflow_id, key, value):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        c.execute(
            """INSERT INTO kv_store (owner, workflow_id, key, value, updated_at) VALUES (?,?,?,?,?)
               ON CONFLICT(owner, workflow_id, key) DO UPDATE SET value=excluded.value,
                 updated_at=excluded.updated_at""",
            (owner or "", workflow_id or "", key, value, now),
        )
    return value


def kv_append(owner, workflow_id, key, value, sep="\n"):
    """Append value to the existing text under key (sep-joined); returns the new value."""
    prev = kv_get(owner, workflow_id, key)
    new = value if not prev else prev + (sep or "\n") + value
    kv_set(owner, workflow_id, key, new)
    return new


def kv_delete(owner, workflow_id, key):
    with _conn() as c:
        c.execute("DELETE FROM kv_store WHERE owner=? AND workflow_id=? AND key=?",
                  (owner or "", workflow_id or "", key))


# --- schedules (cron) -----------------------------------------------------
def get_schedule(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row:
            return None
        r = c.execute("SELECT cron, enabled, next_run, last_run FROM schedules WHERE workflow_id=?",
                      (wid,)).fetchone()
        return dict(r) if r else None


def set_schedule(wid, ctx, cron, relay_key, next_run):
    """Editor+ can schedule. Runs under the scheduling user (their key + secrets)."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    ctx = ctx or {}
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return None
        c.execute(
            """INSERT INTO schedules (workflow_id, owner, cron, relay_key, enabled, next_run, last_run, created_at)
               VALUES (?,?,?,?,1,?,NULL,?)
               ON CONFLICT(workflow_id) DO UPDATE SET cron=excluded.cron, owner=excluded.owner,
                 relay_key=excluded.relay_key, enabled=1, next_run=excluded.next_run""",
            (wid, ctx.get("user"), cron, relay_key, next_run, now),
        )
    return get_schedule(wid, ctx)


def delete_schedule(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return
        c.execute("DELETE FROM schedules WHERE workflow_id=?", (wid,))


def due_schedules():
    """Enabled schedules whose next_run has passed (parsed in Python)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    with _conn() as c:
        for r in c.execute("SELECT * FROM schedules WHERE enabled=1").fetchall():
            try:
                nr = datetime.datetime.fromisoformat((r["next_run"] or "").replace("Z", "+00:00"))
                if nr.tzinfo is None:
                    nr = nr.replace(tzinfo=datetime.timezone.utc)
                if nr <= now:
                    out.append(dict(r))
            except Exception:
                pass
    return out


def mark_schedule_ran(wid, last_run, next_run):
    with _conn() as c:
        c.execute("UPDATE schedules SET last_run=?, next_run=? WHERE workflow_id=?", (last_run, next_run, wid))


# --- deployments ---------------------------------------------------------
def get_deployment(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row:
            return None
        r = c.execute("SELECT token, enabled, created_at FROM deployments WHERE workflow_id=?", (wid,)).fetchone()
        return dict(r) if r else {"token": None, "enabled": 0}


def deploy_workflow(wid, ctx=None, relay_key=None):
    """Create (or rotate) the webhook deployment. relay_key = the deployer's
    own Nyquest key so unattended runs bill their wallet. Requires editor+."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    token = "zh_" + _secrets.token_urlsafe(24)
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return None
        c.execute("DELETE FROM deployments WHERE workflow_id=?", (wid,))
        c.execute(
            "INSERT INTO deployments (token, workflow_id, relay_key, enabled, created_at) VALUES (?,?,?,1,?)",
            (token, wid, relay_key, now),
        )
    return {"token": token, "enabled": 1, "created_at": now}


def undeploy_workflow(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return False
        c.execute("DELETE FROM deployments WHERE workflow_id=?", (wid,))
    return True


def deployment_by_token(token):
    with _conn() as c:
        r = c.execute(
            """SELECT d.workflow_id, d.relay_key, w.owner FROM deployments d
               JOIN workflows w ON w.id = d.workflow_id
               WHERE d.token=? AND d.enabled=1""",
            (token,),
        ).fetchone()
    if not r:
        return None
    wf = get_workflow_raw(r["workflow_id"])  # token is the capability; bypass RBAC
    if not wf:
        return None
    return {"workflow": wf, "relay_key": r["relay_key"], "owner": r["owner"]}


# --- run log --------------------------------------------------------------
def _run_cost(events):
    """Sum per-node relay cost from the run's events (0.0 for auto/unpriced calls)."""
    total = 0.0
    for ev in events or []:
        if isinstance(ev, dict) and ev.get("cost"):
            try:
                total += float(ev["cost"])
            except Exception:
                pass
    return round(total, 6)


def log_run(workflow_id, owner, source, res):
    events = res.get("events") or []
    cost = _run_cost(events)
    with _conn() as c:
        org = c.execute("SELECT org_id FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        org_id = org["org_id"] if org else None
        c.execute(
            """INSERT INTO runs (id, workflow_id, owner, org_id, source, status, started_at, ms, tokens, cost_usd, output, error, events)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "run_" + uuid.uuid4().hex[:10], workflow_id, owner, org_id, source,
                res.get("status", "error"), res.get("started_at", datetime.datetime.utcnow().isoformat() + "Z"),
                res.get("ms"), res.get("tokens"), cost,
                (res.get("output") or "")[:4000] if res.get("output") else None,
                (res.get("error") or "")[:2000] if res.get("error") else None,
                json.dumps(events)[:100000],
            ),
        )


def _run_visibility(ctx):
    """(sql_clause, args) selecting runs the caller can see: their personal runs plus
    runs of any org they belong to."""
    ctx = ctx or {}
    org_ids = list(ctx.get("orgs") or {})
    clause = "(r.owner IS ? AND r.org_id IS NULL)"
    args = [ctx.get("user")]
    if org_ids:
        clause += " OR r.org_id IN (%s)" % ",".join("?" * len(org_ids))
        args += org_ids
    return "(" + clause + ")", args


def list_runs(ctx=None, workflow_id=None, limit=100):
    vis, args = _run_visibility(ctx)
    q = (f"""SELECT r.id, r.workflow_id, COALESCE(w.name,'(deleted)') AS workflow_name,
                   r.source, r.status, r.started_at, r.ms, r.tokens, r.cost_usd, r.org_id
            FROM runs r LEFT JOIN workflows w ON w.id = r.workflow_id
            WHERE {vis} """)
    if workflow_id:
        q += "AND r.workflow_id = ? "
        args.append(workflow_id)
    q += "ORDER BY r.started_at DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def get_run(rid, ctx=None):
    vis, args = _run_visibility(ctx)
    with _conn() as c:
        r = c.execute(
            f"""SELECT r.*, COALESCE(w.name,'(deleted)') AS workflow_name
               FROM runs r LEFT JOIN workflows w ON w.id = r.workflow_id
               WHERE r.id=? AND {vis}""",
            (rid, *args),
        ).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["events"] = json.loads(d.get("events") or "[]")
    except Exception:
        d["events"] = []
    return d


# --- secrets vault (owner-scoped; '' = local sandbox) ---
def list_secrets(owner=None):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT name, preview, created_at FROM secrets WHERE owner=? ORDER BY name",
            (owner or "",),
        ).fetchall()]


def set_secret(owner, name, value):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        c.execute(
            """INSERT INTO secrets (owner, name, value_enc, preview, created_at) VALUES (?,?,?,?,?)
               ON CONFLICT(owner, name) DO UPDATE SET value_enc=excluded.value_enc,
                 preview=excluded.preview, created_at=excluded.created_at""",
            (owner or "", name, vault.encrypt(value), vault.preview(value), now),
        )
    return {"name": name, "preview": vault.preview(value)}


def delete_secret(owner, name):
    with _conn() as c:
        c.execute("DELETE FROM secrets WHERE owner=? AND name=?", (owner or "", name))


def secrets_map(owner=None):
    """{name: plaintext} for injecting into a run. Decrypt failures are skipped."""
    out = {}
    with _conn() as c:
        for r in c.execute("SELECT name, value_enc FROM secrets WHERE owner=?", (owner or "",)).fetchall():
            try:
                out[r["name"]] = vault.decrypt(r["value_enc"])
            except Exception:
                pass
    return out


def run_stats(ctx=None):
    vis, a = _run_visibility(ctx)
    # the visibility clause uses table alias `r.`; stats queries are single-table, alias runs as r
    with _conn() as c:
        row = c.execute(
            f"""SELECT COUNT(*) total,
                      SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) ok,
                      COALESCE(SUM(tokens),0) tokens,
                      COALESCE(SUM(cost_usd),0) cost,
                      COALESCE(AVG(ms),0) avg_ms
               FROM runs r WHERE {vis}""",
            a,
        ).fetchone()
        by_src = {r["source"]: r["n"] for r in c.execute(
            f"SELECT source, COUNT(*) n FROM runs r WHERE {vis} GROUP BY source", a
        ).fetchall()}
        days = [dict(r) for r in c.execute(
            f"""SELECT substr(started_at,1,10) d, COUNT(*) n,
                      SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) ok,
                      COALESCE(SUM(cost_usd),0) cost
               FROM runs r WHERE {vis} GROUP BY d ORDER BY d DESC LIMIT 14""",
            a,
        ).fetchall()]
        by_wf = [dict(r) for r in c.execute(
            f"""SELECT r.workflow_id, COALESCE(w.name,'(deleted)') AS name,
                      COUNT(*) runs, COALESCE(SUM(r.cost_usd),0) cost, COALESCE(SUM(r.tokens),0) tokens
               FROM runs r LEFT JOIN workflows w ON w.id=r.workflow_id
               WHERE {vis} GROUP BY r.workflow_id ORDER BY cost DESC LIMIT 8""",
            a,
        ).fetchall()]
        # how many priced-token runs lack a cost (auto/unpriced) → honesty flag
        partial = c.execute(
            f"SELECT COUNT(*) n FROM runs r WHERE {vis} AND COALESCE(tokens,0)>0 AND COALESCE(cost_usd,0)=0", a
        ).fetchone()["n"]
    total = row["total"] or 0
    ok = row["ok"] or 0
    return {
        "total": total,
        "ok": ok,
        "failed": total - ok,
        "success_rate": round(100 * ok / total) if total else None,
        "tokens": row["tokens"] or 0,
        "cost_usd": round(row["cost"] or 0, 4),
        "cost_partial_runs": partial,
        "avg_ms": int(row["avg_ms"] or 0),
        "by_source": by_src,
        "by_workflow": [{**d, "cost": round(d["cost"], 4)} for d in by_wf],
        "days": [{**d, "cost": round(d["cost"], 4)} for d in reversed(days)],
    }


def node_run_stats(wid, ctx=None, limit=200):
    """Aggregate per-node metrics from a workflow's recent runs (for the optimizer's
    performance analysis). Returns {node_id: {runs, errors, ms_avg, cost, tokens}}."""
    vis, args = _run_visibility(ctx)
    with _conn() as c:
        rows = c.execute(
            f"SELECT r.events FROM runs r WHERE {vis} AND r.workflow_id=? ORDER BY r.started_at DESC LIMIT ?",
            (*args, wid, limit),
        ).fetchall()
    agg = {}
    for row in rows:
        try:
            events = json.loads(row["events"] or "[]")
        except Exception:
            continue
        for ev in events:
            if not isinstance(ev, dict) or ev.get("type") != "node" or ev.get("status") == "running":
                continue
            nid = ev.get("nodeId")
            if not nid:
                continue
            a = agg.setdefault(nid, {"runs": 0, "errors": 0, "ms_sum": 0, "cost": 0.0, "tokens": 0})
            a["runs"] += 1
            if ev.get("status") == "error":
                a["errors"] += 1
            if ev.get("ms"):
                a["ms_sum"] += ev["ms"]
            if ev.get("cost"):
                a["cost"] += ev["cost"]
            if ev.get("tokens"):
                a["tokens"] += ev["tokens"]
    out = {}
    for nid, a in agg.items():
        out[nid] = {"runs": a["runs"], "errors": a["errors"],
                    "ms_avg": round(a["ms_sum"] / a["runs"]) if a["runs"] else 0,
                    "cost": round(a["cost"], 6), "tokens": a["tokens"]}
    return out


def rename_workflow(wid, name, ctx=None):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row or not _can(role, "editor"):
            return None
        c.execute("UPDATE workflows SET name=?, updated_at=? WHERE id=?", (name, now, wid))
    return {"id": wid, "name": name, "updated_at": now}


def clone_workflow(wid, ctx=None):
    src = get_workflow(wid, ctx)
    if not src:
        return None
    new = {
        "id": "wf_" + uuid.uuid4().hex[:8],
        "name": src.get("name", "Untitled") + " (copy)",
        "nodes": src.get("nodes", []),
        "edges": src.get("edges", []),
        "org_id": src.get("org_id"),  # a clone stays in the same org (if any)
    }
    save_workflow(new, ctx)
    return {"id": new["id"], "name": new["name"]}


def snapshot_workflow(wid, label, ctx=None):
    wf = get_workflow(wid, ctx)
    if not wf or not _can(wf.get("role"), "editor"):
        return None
    now = datetime.datetime.utcnow().isoformat() + "Z"
    graph = json.dumps({"nodes": wf.get("nodes", []), "edges": wf.get("edges", [])})
    _insert_version(wid, wf.get("name", "Untitled"), graph, label or "Manual save", now)
    return {"ok": True, "created_at": now}


def list_versions(wid, ctx=None):
    with _conn() as c:
        row, role = _access(c, wid, ctx)
        if not row:
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


def _version_row(vid, ctx, need="viewer"):
    """Version row iff the caller has at least `need` role on its parent workflow."""
    with _conn() as c:
        r = c.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
        if not r:
            return None
        _, role = _access(c, r["workflow_id"], ctx)
    return r if _can(role, need) else None


def get_version(vid, ctx=None):
    r = _version_row(vid, ctx, "viewer")
    if not r:
        return None
    g = json.loads(r["graph"])
    g["id"] = r["workflow_id"]
    g["name"] = r["name"]
    return g


def restore_version(vid, ctx=None):
    r = _version_row(vid, ctx, "editor")
    if not r:
        return None
    g = json.loads(r["graph"])
    now = datetime.datetime.utcnow().isoformat() + "Z"
    save_workflow({"id": r["workflow_id"], "name": r["name"], "nodes": g.get("nodes", []), "edges": g.get("edges", [])}, ctx)
    _insert_version(r["workflow_id"], r["name"], r["graph"],
                    f"Restored from {r['created_at'][:16].replace('T', ' ')}", now)
    return get_workflow(r["workflow_id"], ctx)
