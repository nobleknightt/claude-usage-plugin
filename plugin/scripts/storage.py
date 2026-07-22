"""Local durable event queue backed by SQLite.

The hook writes each event here and returns immediately; the sync worker drains
pending rows to the server and marks them synced. This is what makes tracking
survive a server outage or a machine reboot without blocking Claude Code.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    last_attempt_at TEXT,
    synced_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventQueue:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Open a connection that commits on success and always closes.

        Yields:
            An open SQLite connection with row access enabled.
        """
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def enqueue(self, event_id: str, event_type: str, payload: str) -> None:
        """Add an event to the queue, ignoring duplicates.

        Args:
            event_id: Globally unique id; a repeat is silently ignored.
            event_type: The kind of event (e.g. ``"usage"``).
            payload: The JSON-encoded event body.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO events (id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (event_id, event_type, payload, _now()),
            )

    def claim_pending(self, limit: int = 100) -> list[sqlite3.Row]:
        """Return the oldest pending events awaiting sync.

        Args:
            limit: Maximum number of events to return.

        Returns:
            Rows with ``id``, ``event_type``, and ``payload``, oldest first.
        """
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, event_type, payload FROM events "
                "WHERE status = 'pending' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_synced(self, ids: list[str]) -> None:
        """Mark events as successfully synced to the server.

        Args:
            ids: The ids of the events to mark synced.
        """
        if not ids:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE events SET status = 'synced', synced_at = ? WHERE id = ?",
                [(_now(), i) for i in ids],
            )

    def mark_attempted(self, ids: list[str]) -> None:
        """Record a failed sync attempt so backoff can be applied.

        Args:
            ids: The ids of the events whose attempt count to increment.
        """
        if not ids:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE events SET attempts = attempts + 1, last_attempt_at = ? WHERE id = ?",
                [(_now(), i) for i in ids],
            )

    def purge_synced(self) -> None:
        """Remove already-synced events to keep the queue small."""
        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE status = 'synced'")
