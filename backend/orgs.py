"""Organizations, membership, RBAC roles, and the audit log.

Roles (ascending): viewer < editor < admin < owner.
  viewer  — read + run workflows in the org
  editor  — + create/edit/version/deploy/schedule workflows
  admin   — + manage members (invite/role/remove)
  owner   — + rename/delete the org

Invites: adding a member by email who has never signed in creates a *pending* row
(user_id NULL). On their next login (session carries their email) `claim_invites`
binds the pending rows to their Nyquest user id. Adding by a known user id is immediate.

Shares the builder SQLite database (db._conn / same file)."""
import uuid
import datetime
import db

ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}
ROLES = list(ROLE_RANK)


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _nid(p):
    return f"{p}_{uuid.uuid4().hex[:10]}"


def init():
    with db._conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orgs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_user_id TEXT NOT NULL, created_at TEXT NOT NULL )""")
        # surrogate id PK; (org_id, user_id/email) uniqueness enforced in code.
        c.execute("""CREATE TABLE IF NOT EXISTS org_members (
            id TEXT PRIMARY KEY, org_id TEXT NOT NULL, user_id TEXT, email TEXT,
            role TEXT NOT NULL DEFAULT 'viewer', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_member_user ON org_members(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_member_org ON org_members(org_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_member_email ON org_members(email)")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY, actor_user_id TEXT, org_id TEXT, entity_type TEXT,
            entity_id TEXT, action TEXT, details TEXT, created_at TEXT NOT NULL )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_log(org_id, created_at)")


# --- membership resolution -------------------------------------------------
def user_org_roles(user_id):
    """{org_id: role} for every org the user is an ACTIVE member of. Empty for None."""
    if not user_id:
        return {}
    with db._conn() as c:
        rows = c.execute(
            "SELECT org_id, role FROM org_members WHERE user_id=? AND status='active'", (user_id,)
        ).fetchall()
    return {r["org_id"]: r["role"] for r in rows}


def claim_invites(user_id, email):
    """Bind pending email invites to this user on login. Returns count claimed."""
    if not user_id or not email:
        return 0
    with db._conn() as c:
        rows = c.execute(
            "SELECT id, org_id FROM org_members WHERE status='pending' AND lower(email)=lower(?)",
            (email,),
        ).fetchall()
        n = 0
        for r in rows:
            # skip if the user is already an active member of that org
            dup = c.execute("SELECT 1 FROM org_members WHERE org_id=? AND user_id=? AND status='active'",
                            (r["org_id"], user_id)).fetchone()
            if dup:
                c.execute("DELETE FROM org_members WHERE id=?", (r["id"],))
                continue
            c.execute("UPDATE org_members SET user_id=?, status='active' WHERE id=?", (user_id, r["id"]))
            n += 1
    return n


# --- orgs ------------------------------------------------------------------
def create_org(name, user_id):
    oid = _nid("org")
    now = _now()
    with db._conn() as c:
        c.execute("INSERT INTO orgs (id, name, owner_user_id, created_at) VALUES (?,?,?,?)",
                  (oid, name.strip() or "Untitled org", user_id, now))
        c.execute("""INSERT INTO org_members (id, org_id, user_id, email, role, status, created_at)
                     VALUES (?,?,?,?,'owner','active',?)""",
                  (_nid("mem"), oid, user_id, None, now))
    audit(user_id, oid, "org", oid, "created", {"name": name})
    return get_org(oid, user_id)


def list_orgs(user_id):
    roles = user_org_roles(user_id)
    if not roles:
        return []
    with db._conn() as c:
        out = []
        for oid, role in roles.items():
            o = c.execute("SELECT id, name, created_at FROM orgs WHERE id=?", (oid,)).fetchone()
            if not o:
                continue
            n = c.execute("SELECT COUNT(*) n FROM org_members WHERE org_id=? AND status='active'", (oid,)).fetchone()["n"]
            wf = c.execute("SELECT COUNT(*) n FROM workflows WHERE org_id=?", (oid,)).fetchone()["n"]
            d = dict(o); d["role"] = role; d["members"] = n; d["workflows"] = wf
            out.append(d)
    return sorted(out, key=lambda x: x["created_at"])


def get_org(oid, user_id):
    role = user_org_roles(user_id).get(oid)
    if not role:
        return None
    with db._conn() as c:
        o = c.execute("SELECT * FROM orgs WHERE id=?", (oid,)).fetchone()
        if not o:
            return None
        members = [dict(r) for r in c.execute(
            "SELECT id, user_id, email, role, status, created_at FROM org_members WHERE org_id=? ORDER BY created_at",
            (oid,)).fetchall()]
    d = dict(o); d["role"] = role; d["members"] = members
    return d


def rename_org(oid, name, user_id):
    if not _has(user_id, oid, "owner"):
        return None
    with db._conn() as c:
        c.execute("UPDATE orgs SET name=? WHERE id=?", (name.strip() or "Untitled org", oid))
    audit(user_id, oid, "org", oid, "renamed", {"name": name})
    return get_org(oid, user_id)


def delete_org(oid, user_id):
    if not _has(user_id, oid, "owner"):
        return False
    with db._conn() as c:
        # detach org workflows back to their personal owners (never orphan/delete user data)
        c.execute("UPDATE workflows SET org_id=NULL WHERE org_id=?", (oid,))
        c.execute("DELETE FROM org_members WHERE org_id=?", (oid,))
        c.execute("DELETE FROM orgs WHERE id=?", (oid,))
    audit(user_id, None, "org", oid, "deleted", {})
    return True


# --- members ---------------------------------------------------------------
def _has(user_id, oid, need):
    return ROLE_RANK.get(user_org_roles(user_id).get(oid), 0) >= ROLE_RANK[need]


def add_member(oid, actor, email=None, member_user_id=None, role="viewer"):
    if not _has(actor, oid, "admin"):
        return {"error": "forbidden"}
    if role not in ROLE_RANK or role == "owner":
        role = "viewer"  # owner is not assignable via invite
    email = (email or "").strip() or None
    if not email and not member_user_id:
        return {"error": "email_or_user_required"}
    now = _now()
    with db._conn() as c:
        # de-dupe: existing active member by user_id or email
        if member_user_id:
            ex = c.execute("SELECT id FROM org_members WHERE org_id=? AND user_id=?", (oid, member_user_id)).fetchone()
            if ex:
                c.execute("UPDATE org_members SET role=?, status='active' WHERE id=?", (role, ex["id"]))
                audit(actor, oid, "member", member_user_id, "role_changed", {"role": role})
                return {"ok": True}
        if email:
            ex = c.execute("SELECT id FROM org_members WHERE org_id=? AND lower(email)=lower(?)", (oid, email)).fetchone()
            if ex:
                c.execute("UPDATE org_members SET role=? WHERE id=?", (role, ex["id"]))
                return {"ok": True}
        status = "active" if member_user_id else "pending"
        c.execute("""INSERT INTO org_members (id, org_id, user_id, email, role, status, created_at)
                     VALUES (?,?,?,?,?,?,?)""",
                  (_nid("mem"), oid, member_user_id, email, role, status, now))
    audit(actor, oid, "member", member_user_id or email, "invited", {"role": role, "email": email})
    return {"ok": True, "status": status}


def update_member(oid, actor, member_id, role):
    if not _has(actor, oid, "admin"):
        return {"error": "forbidden"}
    if role not in ROLE_RANK:
        return {"error": "bad_role"}
    with db._conn() as c:
        m = c.execute("SELECT * FROM org_members WHERE id=? AND org_id=?", (member_id, oid)).fetchone()
        if not m:
            return {"error": "not_found"}
        # never demote the last owner
        if m["role"] == "owner" and role != "owner":
            owners = c.execute("SELECT COUNT(*) n FROM org_members WHERE org_id=? AND role='owner' AND status='active'", (oid,)).fetchone()["n"]
            if owners <= 1:
                return {"error": "last_owner"}
        # only an owner can grant owner
        if role == "owner" and not _has(actor, oid, "owner"):
            return {"error": "owner_only"}
        c.execute("UPDATE org_members SET role=? WHERE id=?", (role, member_id))
    audit(actor, oid, "member", m["user_id"] or m["email"], "role_changed", {"role": role})
    return {"ok": True}


def remove_member(oid, actor, member_id):
    with db._conn() as c:
        m = c.execute("SELECT * FROM org_members WHERE id=? AND org_id=?", (member_id, oid)).fetchone()
        if not m:
            return {"error": "not_found"}
        self_leave = m["user_id"] and m["user_id"] == actor
        if not self_leave and not _has(actor, oid, "admin"):
            return {"error": "forbidden"}
        if m["role"] == "owner":
            owners = c.execute("SELECT COUNT(*) n FROM org_members WHERE org_id=? AND role='owner' AND status='active'", (oid,)).fetchone()["n"]
            if owners <= 1:
                return {"error": "last_owner"}
        c.execute("DELETE FROM org_members WHERE id=?", (member_id,))
    audit(actor, oid, "member", m["user_id"] or m["email"], "removed", {})
    return {"ok": True}


# --- audit log -------------------------------------------------------------
def audit(actor, org_id, entity_type, entity_id, action, details=None):
    import json
    with db._conn() as c:
        c.execute("""INSERT INTO audit_log (id, actor_user_id, org_id, entity_type, entity_id, action, details, created_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (_nid("aud"), actor, org_id, entity_type, entity_id, action,
                   json.dumps(details or {}), _now()))


def audit_list(user_id, org_id=None, limit=200):
    """Personal actions (actor=user) plus, for orgs the user can admin, that org's trail."""
    import json
    roles = user_org_roles(user_id)
    admin_orgs = [oid for oid, r in roles.items() if ROLE_RANK[r] >= ROLE_RANK["admin"]]
    with db._conn() as c:
        if org_id:
            if ROLE_RANK.get(roles.get(org_id), 0) < ROLE_RANK["admin"]:
                return None
            rows = c.execute("SELECT * FROM audit_log WHERE org_id=? ORDER BY created_at DESC LIMIT ?",
                             (org_id, limit)).fetchall()
        else:
            clause = "actor_user_id=?"
            args = [user_id]
            if admin_orgs:
                clause += " OR org_id IN (%s)" % ",".join("?" * len(admin_orgs))
                args += admin_orgs
            rows = c.execute(f"SELECT * FROM audit_log WHERE {clause} ORDER BY created_at DESC LIMIT ?",
                             (*args, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d.get("details") or "{}")
        except Exception:
            d["details"] = {}
        out.append(d)
    return out
