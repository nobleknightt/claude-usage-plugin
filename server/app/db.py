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

# Seed rates in USD per million tokens: (input, output, cache_write, cache_read).
# Cache tiers follow Anthropic's standard multipliers (5-min write = 1.25x input,
# read = 0.1x input). Users can override rows at runtime.
MODEL_PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5":    (10.0, 50.0, 12.50, 1.00),
    "claude-opus-4-8":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-7":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-6":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-5":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-1":   (15.0, 75.0, 18.75, 1.50),
    "claude-sonnet-5":   (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 3.75, 0.30),
    "claude-haiku-4-5":  (1.0, 5.0, 1.25, 0.10),
}

SCHEMA = """
-- One row per turn (the delta reported by a single Stop hook), not a
-- cumulative snapshot — so per-session totals are SUM(...) over turns.
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    account_email TEXT    DEFAULT '',
    session_id    TEXT    NOT NULL,
    turn_index    INTEGER DEFAULT 0,
    cwd           TEXT    DEFAULT '',
    timestamp     TEXT    NOT NULL,
    started_at    TEXT    DEFAULT '',
    ended_at      TEXT    DEFAULT '',
    model         TEXT    DEFAULT '',
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read    INTEGER DEFAULT 0,
    cache_write   INTEGER DEFAULT 0,
    cost_usd      REAL    DEFAULT 0.0,
    cost_source   TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_email     ON usage(email);
CREATE INDEX IF NOT EXISTS idx_session   ON usage(session_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON usage(timestamp);

-- Per-model rates (USD per million tokens) used to compute cost when the
-- transcript's own total_cost_usd is 0. Seeded from a code default; a row can be
-- overridden at runtime and won't be clobbered on restart.
CREATE TABLE IF NOT EXISTS model_pricing (
    model                TEXT PRIMARY KEY,
    input_per_mtok       REAL NOT NULL,
    output_per_mtok      REAL NOT NULL,
    cache_write_per_mtok REAL NOT NULL,
    cache_read_per_mtok  REAL NOT NULL,
    updated_at           TEXT NOT NULL
);

-- Who the user is. Email + display name come from the Entra-verified id_token;
-- is_admin is a per-user flag (see scripts/set_admin.py).
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
    """Create the schema, migrate older DBs, and seed model pricing."""
    # `with sqlite3.connect(...)` commits but does NOT close the connection,
    # which leaks it and locks the file on Windows. Close explicitly.
    conn = sqlite3.connect(DB)
    try:
        conn.executescript(SCHEMA)
        # Add columns introduced after the first schema (SQLite has no
        # "ADD COLUMN IF NOT EXISTS", so check PRAGMA first).
        cols = {r[1] for r in conn.execute("PRAGMA table_info(usage)")}
        for col, ddl in (
            ("cost_source", "cost_source TEXT DEFAULT ''"),
            ("turn_index", "turn_index INTEGER DEFAULT 0"),
            ("started_at", "started_at TEXT DEFAULT ''"),
            ("ended_at", "ended_at TEXT DEFAULT ''"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE usage ADD COLUMN {ddl}")
        # Seed pricing (INSERT OR IGNORE keeps any runtime overrides).
        conn.executemany(
            "INSERT OR IGNORE INTO model_pricing "
            "(model, input_per_mtok, output_per_mtok, cache_write_per_mtok, cache_read_per_mtok, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(m, i, o, cw, cr, now()) for m, (i, o, cw, cr) in MODEL_PRICING.items()],
        )
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
