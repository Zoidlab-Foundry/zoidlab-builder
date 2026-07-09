"""Reads the ZoidLab session cookie (minted by the Next /api/session route,
signed with the shared BUILDER_SESSION_SECRET)."""
import os
import jwt

SECRET = os.environ.get("BUILDER_SESSION_SECRET", "")


def session_payload(cookie_value: str | None) -> dict | None:
    """Full session claims ({sub, email, name, tier, rk}) or None."""
    if not cookie_value or not SECRET:
        return None
    try:
        return jwt.decode(cookie_value, SECRET, algorithms=["HS256"])
    except Exception:
        return None


def relay_key_from_cookie(cookie_value: str | None) -> str | None:
    p = session_payload(cookie_value)
    return p.get("rk") if p else None
