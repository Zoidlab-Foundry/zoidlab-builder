"""Secrets vault — symmetric encryption at rest + redaction helpers.

Secret values are encrypted with a Fernet key (VAULT_KEY env; falls back to a
key derived from BUILDER_SESSION_SECRET so dev works). They are decrypted only
to inject into a run's context and are redacted everywhere they might surface."""
import os
import re
import base64
import hashlib
from cryptography.fernet import Fernet

_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ""))


def _fernet() -> Fernet:
    key = os.environ.get("VAULT_KEY", "")
    if not key:
        seed = os.environ.get("BUILDER_SESSION_SECRET", "zoidlab-dev")
        key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def preview(value: str) -> str:
    v = value or ""
    return "••••" if len(v) <= 4 else "••••" + v[-4:]


def make_redactor(values):
    """Return f(x) that masks any secret value found in strings (recursing into
    dict/list). Only masks values >= 4 chars to avoid nuking trivial ones."""
    vals = sorted({v for v in values if v and len(v) >= 4}, key=len, reverse=True)

    def red(x):
        if isinstance(x, str):
            for v in vals:
                if v in x:
                    x = x.replace(v, "••••")
            return x
        if isinstance(x, dict):
            return {k: red(v) for k, v in x.items()}
        if isinstance(x, list):
            return [red(v) for v in x]
        return x

    return red
