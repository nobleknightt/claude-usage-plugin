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
import uuid
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

    # Parse only what was appended since the last turn (the delta), not the
    # whole transcript, so each recorded event is one turn's own usage.
    prior = state.read(config.state_path, session_id)
    usage = parse(Path(transcript_path), prior.offset, prior.cost)

    if not usage.has_activity:
        # An empty tail (e.g. a Stop with no new model work) — advance the
        # offset so we don't re-scan it, but record nothing.
        state.write(
            config.state_path,
            session_id,
            state.SessionState(usage.new_offset, prior.turn_index, usage.cost_cumulative),
        )
        sys.exit(0)

    turn_index = prior.turn_index + 1
    payload = {
        "account_email": read_account_email(),
        "session_id": session_id,
        "turn_index": turn_index,
        "cwd": usage.cwd,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "started_at": usage.started_at,
        "ended_at": usage.ended_at,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read": usage.cache_read,
        "cache_write": usage.cache_write,
        "cost_usd": usage.cost_usd,
    }

    try:
        queue = EventQueue(config.db_path)
        queue.enqueue(str(uuid.uuid4()), EVENT_TYPE, json.dumps(payload))
        # Only advance the offset once the event is safely queued, so a crash
        # before enqueue just re-reads the same tail next time (no lost turn).
        state.write(
            config.state_path,
            session_id,
            state.SessionState(usage.new_offset, turn_index, usage.cost_cumulative),
        )
    except Exception as e:
        logger.error("main: could not enqueue event: %s", e)
        sys.exit(0)

    # Best-effort background drain; failures just leave events pending.
    try:
        sync.drain(config)
    except Exception as e:
        logger.warning("main: drain failed, events remain queued: %s", e)

    sys.exit(0)


if __name__ == "__main__":
    main()
