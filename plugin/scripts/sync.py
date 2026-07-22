"""Drain pending events from the local queue to the tracker server.

Runs in the background (async hook) and on session end. Never raises past its
own boundary: if the server is unreachable the events simply stay pending and
are retried on the next run.
"""

import json
import logging
import logging.handlers
import sys
import urllib.request
from pathlib import Path

from config import Config
from storage import EventQueue

logger = logging.getLogger("usage-tracker.sync")

BATCH_LIMIT = 100


def _post_batch(base_url: str, api_key: str, events: list[dict]) -> None:
    """POST a batch of events to the server's ingestion endpoint.

    Args:
        base_url: The tracker server's base URL.
        api_key: The API key sent as a Bearer token.
        events: The event envelopes to send.
    """
    body = json.dumps({"events": events}).encode()
    req = urllib.request.Request(
        base_url + "/api/events/batch",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def drain(config: Config) -> None:
    """Send all pending events the server will accept, marking them synced."""
    queue = EventQueue(config.db_path)
    rows = queue.claim_pending(BATCH_LIMIT)
    if not rows:
        return

    ids = [row["id"] for row in rows]
    events = [
        {"event_id": row["id"], "event_type": row["event_type"], "payload": json.loads(row["payload"])}
        for row in rows
    ]

    try:
        _post_batch(config.base_url, config.api_key, events)
    except Exception as e:
        queue.mark_attempted(ids)
        logger.warning("drain: server unreachable, keeping %d event(s): %s", len(ids), e)
        return

    queue.mark_synced(ids)
    queue.purge_synced()
    logger.info("drain: synced %d event(s)", len(ids))


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("usage-tracker").addHandler(handler)
    logging.getLogger("usage-tracker").setLevel(logging.INFO)


def main() -> None:
    config = Config.load()
    if not config.base_url:
        sys.exit(0)
    _configure_logging(config.log_path)
    try:
        drain(config)
    except Exception as e:
        logger.error("main: unexpected error: %s", e)
    sys.exit(0)


if __name__ == "__main__":
    main()
