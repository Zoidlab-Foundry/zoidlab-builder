"""Reads the per-user relay key from the ZoidLab session cookie (minted by the
Next /api/session route, signed with the shared BUILDER_SESSION_SECRET)."""
import os
import jwt

SECRET = os.environ.get("BUILDER_SESSION_SECRET", "")


def relay_key_from_cookie(cookie_value: str | None) -> str | None:
    """Return the user's Nyquest relay key (claim `rk`) from a valid session
    cookie, or None if absent/invalid so the caller can fall back."""
    if not cookie_value or not SECRET:
        return None
    try:
        payload = jwt.decode(cookie_value, SECRET, algorithms=["HS256"])
        return payload.get("rk")
    except Exception:
        return None
