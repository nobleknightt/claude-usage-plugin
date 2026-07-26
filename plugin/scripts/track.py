"""Stop-hook entry point: record one turn's usage, then return.

Reads the Claude Code hook payload from stdin, parses the transcript, writes a
usage event to the local queue, and triggers a background sync. Always exits 0
and never writes to stdout, so it stays a pure observer and never interferes
with Claude Code stopping.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

import state
import sync
from config import Config, read_account_email
from storage import EventQueue
from transcript import parse

logger = logging.getLogger("usage-tracker.track")

EVENT_TYPE = "usage"


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("usage-tracker")
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main() -> None:
    try:
        hook_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # malformed input — never block Claude Code

    # A continuation turn (a prior Stop hook forced Claude to keep working) has
    # no new user-facing result of its own; skip it to avoid double-counting.
    if hook_data.get("stop_hook_active"):
        sys.exit(0)

    config = Config.load()
    if not config.api_key or not config.base_url:
        sys.exit(0)  # not configured — nothing to record or send to

    _configure_logging(config.log_path)

    session_id = hook_data.get("session_id", "")
    transcript_path = hook_data.get("transcript_path", "")
    if not transcript_path or not session_id:
        sys.exit(0)

    # Read only the bytes appended since the last run and split them into turns.
    # Normally that's the single turn that just finished; on a session's first
    # read it's the whole history, each turn dated by its own transcript time.
    prior = state.read(config.state_path, session_id)
    result = parse(Path(transcript_path), prior.offset, prior.cost)

    if not result.turns:
        # Nothing new with usage — advance the offset so we don't re-scan it.
        state.write(
            config.state_path,
            session_id,
            state.SessionState(result.new_offset, prior.turn_index, result.cost_cumulative),
        )
        sys.exit(0)

    account_email = read_account_email()
    now = datetime.now(timezone.utc).isoformat()
    turn_index = prior.turn_index
    try:
        queue = EventQueue(config.db_path)
        for turn in result.turns:
            turn_index += 1
            payload = {
                "account_email": account_email,
                "session_id": session_id,
                "turn_index": turn_index,
                "cwd": turn.cwd,
                "timestamp": turn.ended_at or now,
                "started_at": turn.started_at,
                "ended_at": turn.ended_at,
                "model": turn.model,
                "input_tokens": turn.input_tokens,
                "output_tokens": turn.output_tokens,
                "cache_read": turn.cache_read,
                "cache_write": turn.cache_write,
                "cost_usd": turn.cost_usd,
            }
            # Stable id (session + turn) makes ingestion idempotent across
            # retries and resyncs — the server counts each turn once.
            queue.enqueue(f"{session_id}:{turn_index}", EVENT_TYPE, json.dumps(payload))
        # Advance the offset only once the events are safely queued, so a crash
        # before this just re-reads the same tail next time (no lost turns).
        state.write(
            config.state_path,
            session_id,
            state.SessionState(result.new_offset, turn_index, result.cost_cumulative),
        )
    except Exception as e:
        logger.error("main: could not enqueue events: %s", e)
        sys.exit(0)

    # Best-effort background drain; failures just leave events pending.
    try:
        sync.drain(config)
    except Exception as e:
        logger.warning("main: drain failed, events remain queued: %s", e)

    sys.exit(0)


if __name__ == "__main__":
    main()
