"""Read a Claude Code transcript (JSONL) and extract usage for a turn."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TranscriptUsage:
    cwd: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int
    cost_usd: float


def _read_entries(path: Path) -> list[dict]:
    """Parse a transcript file, skipping malformed or non-object lines.

    Args:
        path: Path to the JSONL transcript file.

    Returns:
        The parsed JSON objects, one per valid line; empty if unreadable.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    entries: list[dict] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def parse(path: Path) -> TranscriptUsage:
    """Extract aggregated usage for a turn from a transcript file.

    Args:
        path: Path to the JSONL transcript file.

    Returns:
        The summed token counts, model, cost, and originating cwd.
    """
    entries = _read_entries(path)

    input_tokens = output_tokens = cache_read = cache_write = 0
    model = ""
    cost_usd = 0.0
    for entry in entries:
        usage = entry.get("message", {}).get("usage") or entry.get("usage")
        if isinstance(usage, dict):
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cache_read += usage.get("cache_read_input_tokens", 0)
            cache_write += usage.get("cache_creation_input_tokens", 0)
        model = entry.get("message", {}).get("model") or entry.get("model") or model
        cost_usd = entry.get("total_cost_usd") or cost_usd

    # The first entry's cwd is the session's original directory, stable even if
    # the session later cd's elsewhere. The UI groups by session and can derive a
    # label from this (e.g. the basename) as needed.
    cwd = ""
    for entry in entries:
        session_cwd = entry.get("cwd")
        if session_cwd:
            cwd = session_cwd
            break

    return TranscriptUsage(
        cwd=cwd,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        cost_usd=float(cost_usd),
    )
