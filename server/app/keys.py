"""API key management + the hook's Bearer-token authentication.

Keys are created in the dashboard (session-authenticated) and shown in plaintext
exactly once; only their SHA-256 hash is stored. The hook then sends the key as
`Authorization: Bearer <key>`, and `require_api_key` resolves it back to a user
on ingestion.
"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .auth import current_user
from .db import get_db, now


def hash_key(raw: str) -> str:
    """Hash a raw API key for storage and lookup.

    Args:
        raw: The plaintext API key.

    Returns:
        The hex-encoded SHA-256 digest of the key.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def require_api_key(authorization: str | None = Header(default=None)) -> dict:
    """Resolve a Bearer API key to its owning user.

    Also stamps ``last_used_at`` so the dashboard can show when a key was last
    active.

    Args:
        authorization: The request ``Authorization`` header, expected to be
            ``Bearer <key>``.

    Returns:
        The key's user as a dict with ``id``, ``email``, and ``is_admin`` keys.

    Raises:
        HTTPException: 401 if the header is missing/malformed or the key is
            unknown or revoked.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT k.id AS key_id, u.id AS user_id, u.email, u.is_admin
            FROM api_keys k JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = ? AND k.revoked_at IS NULL
            """,
            (hash_key(raw),),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="invalid or revoked API key")
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now(), row["key_id"])
        )
        conn.commit()
    return {"id": row["user_id"], "email": row["email"], "is_admin": bool(row["is_admin"])}


router = APIRouter(prefix="/api/keys")


class CreateKeyBody(BaseModel):
    label: str = ""


def _status(row) -> str:
    return "revoked" if row["revoked_at"] else "active"


@router.post("", summary="Create an API key (returns the secret once)")
def create_key(body: CreateKeyBody, user: dict = Depends(current_user)) -> dict:
    """Create a new API key for the logged-in user.

    Args:
        body: The request body carrying an optional key label.
        user: The logged-in dashboard user (from the session).

    Returns:
        The new key's ``id``, ``label``, ``prefix``, and the plaintext ``key``.
        The plaintext is returned only here and never stored.
    """
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]  # non-secret display hint so the dashboard can tell keys apart
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (user_id, label, key_hash, prefix, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user["id"], body.label, hash_key(raw), prefix, now()),
        )
        conn.commit()
        key_id = cur.lastrowid
    # `key` is returned only here and never stored — the caller must save it now.
    return {"id": key_id, "label": body.label, "prefix": prefix, "key": raw}


@router.get("", summary="List my API keys")
def list_keys(user: dict = Depends(current_user)) -> list[dict]:
    """List the logged-in user's API keys (without the secrets).

    Args:
        user: The logged-in dashboard user (from the session).

    Returns:
        One dict per key with ``id``, ``label``, ``prefix``, ``created_at``,
        ``last_used_at``, and ``status``.
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, label, prefix, created_at, last_used_at, revoked_at "
            "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "prefix": r["prefix"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "status": _status(r),
        }
        for r in rows
    ]


@router.delete("/{key_id}", summary="Revoke an API key")
def revoke_key(key_id: int, user: dict = Depends(current_user)) -> dict:
    """Revoke one of the logged-in user's API keys.

    Args:
        key_id: The id of the key to revoke.
        user: The logged-in dashboard user (from the session).

    Returns:
        ``{"ok": True}`` once the key is revoked.

    Raises:
        HTTPException: 404 if the key does not exist, is already revoked, or
            belongs to another user.
    """
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE api_keys SET revoked_at = ? "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (now(), key_id, user["id"]),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="key not found")
    return {"ok": True}
