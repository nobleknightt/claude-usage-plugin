"""SQLite access and schema for the usage tracker server.

One SQLite file holds everything: raw usage rows plus the auth tables
(`users`, `api_keys`) added in Phase 3. Kept deliberately small — see the plan's
"tiny to run" goal (one FastAPI process + SQLite + bundled SPA).
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

# Path to the SQLite file; override with DATABASE (e.g. a mounted volume in Docker).
DB = os.environ.get("DATABASE", "usage.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    account_email TEXT    DEFAULT '',
    session_id    TEXT    NOT NULL,
    cwd           TEXT    DEFAULT '',
    timestamp     TEXT    NOT NULL,
    model         TEXT    DEFAULT '',
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read    INTEGER DEFAULT 0,
    cache_write   INTEGER DEFAULT 0,
    cost_usd      REAL    DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_email     ON usage(email);
CREATE INDEX IF NOT EXISTS idx_session   ON usage(session_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON usage(timestamp);

-- Who the user is. Email comes from the Entra-verified id_token; is_admin is
-- refreshed from the ADMIN_EMAILS allowlist on every login.
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT    NOT NULL UNIQUE,
    name       TEXT    NOT NULL DEFAULT '',
    is_admin   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

-- API keys the hook sends as `Authorization: Bearer`. Only the hash is stored,
-- so a leaked key can be revoked but never recovered.
CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    label        TEXT    NOT NULL DEFAULT '',
    key_hash     TEXT    NOT NULL UNIQUE,
    prefix       TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    last_used_at TEXT,
    revoked_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

-- Idempotency ledger: the hook may resend an event (retry after a network
-- blip), so ingestion records each event_id once and ignores repeats.
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    received_at TEXT NOT NULL
);
"""


def now() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        The timezone-aware current time formatted as ISO 8601.
    """
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create the database schema if it does not already exist."""
    # `with sqlite3.connect(...)` commits but does NOT close the connection,
    # which leaks it and locks the file on Windows. Close explicitly.
    conn = sqlite3.connect(DB)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with row access and foreign keys enabled.

    Yields:
        An open connection whose rows behave like mappings. The connection is
        closed automatically when the context exits.
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
