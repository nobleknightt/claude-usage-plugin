"""Per-session parse state so each Stop hook only reads the transcript's new tail.

The transcript is append-only JSONL, so we remember the byte offset we last read
up to (and how many turns we've recorded) for every session. The next hook seeks
to that offset and parses only what was appended — that appended slice is exactly
one turn's delta, instead of re-summing the whole file every time.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SessionState:
    offset: int = 0
    turn_index: int = 0
    cost: float = 0.0


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read(path: Path, session_id: str) -> SessionState:
    """Return the saved parse state for a session (defaults for a new one).

    Args:
        path: The state file path.
        session_id: The session whose state to look up.

    Returns:
        The saved :class:`SessionState`, or a zeroed one if unseen.
    """
    entry = _load(path).get(session_id) or {}
    return SessionState(
        offset=int(entry.get("offset", 0)),
        turn_index=int(entry.get("turn_index", 0)),
        cost=float(entry.get("cost", 0.0)),
    )


def write(path: Path, session_id: str, state: SessionState) -> None:
    """Persist the parse state for a session, leaving other sessions untouched.

    Args:
        path: The state file path.
        session_id: The session whose state to update.
        state: The new state to store.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    data[session_id] = {
        "offset": state.offset,
        "turn_index": state.turn_index,
        "cost": state.cost,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
