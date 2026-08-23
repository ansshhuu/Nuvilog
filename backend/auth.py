"""
Lightweight demo login gate.

Not a real multi-user auth system: one shared credential pair from env
vars, no user table, no password hashing, no refresh flow. Good enough to
keep the 4 real screens off the open internet for a demo; not meant to
survive a real security review.
"""
from __future__ import annotations

import os
import time

import jwt
from fastapi import Header, HTTPException

# No fallback: a guessable default would let anyone forge an admin token by
# reading this source file, which defeats the whole point of signing it.
SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET is not set. Generate one with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\" "
        "and add it to .env."
    )
TOKEN_TTL_SECONDS = 12 * 60 * 60


def check_credentials(email: str, password: str) -> str | None:
    """Return the role for a matching (email, password), else None."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return None
    if email == admin_email and password == admin_password:
        return os.environ.get("ADMIN_ROLE", "ADMIN")
    return None


def issue_token(email: str, role: str) -> str:
    payload = {"email": email, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency guarding a route behind a valid session token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
