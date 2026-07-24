"""Read a Claude Code transcript (JSONL) and extract one turn's usage delta."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TurnUsage:
    cwd: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int
    cost_usd: float          # this turn's delta (0 → server computes from tokens)
    cost_cumulative: float   # session-cumulative cost, to carry into the next turn
    started_at: str
    ended_at: str
    new_offset: int

    @property
    def has_activity(self) -> bool:
        return bool(
            self.input_tokens or self.output_tokens or self.cache_read or self.cache_write
        )


def _iter_new_entries(path: Path, start_offset: int) -> tuple[list[dict], int]:
    """Parse only the transcript bytes appended since ``start_offset``.

    The transcript is append-only, so reading from the saved offset yields just
    the latest turn. If the file is shorter than the offset (it was truncated or
    replaced, e.g. after a compaction), we start over from the beginning.

    Args:
        path: Path to the JSONL transcript file.
        start_offset: Byte offset to resume reading from.

    Returns:
        A ``(entries, new_offset)`` pair — the parsed new objects and the byte
        offset to resume from next time.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return [], start_offset

    offset = 0 if start_offset > size else start_offset
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
            new_offset = fh.tell()
    except OSError:
        return [], start_offset

    entries: list[dict] = []
    for raw in chunk.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries, new_offset


def parse(path: Path, start_offset: int = 0, prev_cost: float = 0.0) -> TurnUsage:
    """Extract the usage delta for the turn appended since ``start_offset``.

    Args:
        path: Path to the JSONL transcript file.
        start_offset: Byte offset from the previous parse of this session.
        prev_cost: The session-cumulative cost recorded after the last turn, so
            this turn's cost can be derived as the increase over it.

    Returns:
        The token counts, model, per-turn cost delta, timing, and new byte
        offset for the appended slice. ``total_cost_usd`` in the transcript is
        session-cumulative, so the turn cost is ``cumulative - prev_cost``; a 0
        delta tells the server to compute cost from tokens instead.
    """
    entries, new_offset = _iter_new_entries(path, start_offset)

    input_tokens = output_tokens = cache_read = cache_write = 0
    model = ""
    cost_cumulative = prev_cost
    cwd = ""
    started_at = ended_at = ""
    for entry in entries:
        usage = entry.get("message", {}).get("usage") or entry.get("usage")
        if isinstance(usage, dict):
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cache_read += usage.get("cache_read_input_tokens", 0)
            cache_write += usage.get("cache_creation_input_tokens", 0)
        model = entry.get("message", {}).get("model") or entry.get("model") or model
        if entry.get("total_cost_usd") is not None:
            cost_cumulative = float(entry["total_cost_usd"])
        if not cwd and entry.get("cwd"):
            cwd = entry["cwd"]
        ts = entry.get("timestamp")
        if ts:
            started_at = started_at or ts
            ended_at = ts

    return TurnUsage(
        cwd=cwd,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        cost_usd=round(max(cost_cumulative - prev_cost, 0.0), 6),
        cost_cumulative=cost_cumulative,
        started_at=started_at,
        ended_at=ended_at,
        new_offset=new_offset,
    )
