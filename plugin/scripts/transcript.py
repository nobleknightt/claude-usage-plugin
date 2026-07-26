"""Read a Claude Code transcript (JSONL) and split new content into turns.

The transcript is append-only, so we read only the bytes appended since the last
run and split them on real user prompts. Normally that yields a single turn (the
one that just finished); on the first read of a session it yields every turn in
its history, each dated by its own transcript timestamps.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Turn:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    model: str = ""
    cwd: str = ""
    cost_usd: float = 0.0          # this turn's cost delta (0 → server computes)
    started_at: str = ""
    ended_at: str = ""

    @property
    def has_activity(self) -> bool:
        return bool(
            self.input_tokens or self.output_tokens or self.cache_read or self.cache_write
        )


@dataclass(slots=True)
class ParseResult:
    turns: list = field(default_factory=list)
    new_offset: int = 0
    cost_cumulative: float = 0.0   # session-cumulative cost after the last turn


def _iter_new_entries(path: Path, start_offset: int) -> tuple[list[dict], int]:
    """Parse only the transcript bytes appended since ``start_offset``.

    If the file is shorter than the offset (truncated or replaced, e.g. after a
    compaction), start over from the beginning.

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


def _is_user_prompt(entry: dict) -> bool:
    """Whether an entry is a real user prompt (a turn boundary).

    A ``type: "user"`` entry can be either a genuine prompt or a tool result fed
    back to the model. Only genuine prompts start a turn; tool results carry a
    ``tool_result`` content block and do not.
    """
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def parse(path: Path, start_offset: int = 0, prev_cost: float = 0.0) -> ParseResult:
    """Split the transcript's appended bytes into per-turn usage.

    Args:
        path: Path to the JSONL transcript file.
        start_offset: Byte offset from the previous parse of this session.
        prev_cost: The session-cumulative cost recorded after the last turn, so
            per-turn costs can be derived as increases over it.

    Returns:
        A :class:`ParseResult` with the turns found (each with its own tokens,
        cost delta, model, and timestamps), the new byte offset, and the
        session-cumulative cost to carry into the next parse.
    """
    entries, new_offset = _iter_new_entries(path, start_offset)

    turns: list[Turn] = []
    cost_cumulative = prev_cost
    baseline = prev_cost
    current: Turn | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.has_activity:
            current.cost_usd = round(max(cost_cumulative - baseline, 0.0), 6)
            turns.append(current)
        current = None

    for entry in entries:
        ts = entry.get("timestamp") or ""
        cwd = entry.get("cwd") or ""

        if _is_user_prompt(entry) or current is None:
            flush()
            current = Turn(cwd=cwd, started_at=ts, ended_at=ts)
            baseline = cost_cumulative

        usage = (entry.get("message") or {}).get("usage") or entry.get("usage")
        if isinstance(usage, dict):
            current.input_tokens += usage.get("input_tokens", 0)
            current.output_tokens += usage.get("output_tokens", 0)
            current.cache_read += usage.get("cache_read_input_tokens", 0)
            current.cache_write += usage.get("cache_creation_input_tokens", 0)

        model = (entry.get("message") or {}).get("model") or entry.get("model")
        if model:
            current.model = model
        if cwd and not current.cwd:
            current.cwd = cwd
        if entry.get("total_cost_usd") is not None:
            cost_cumulative = float(entry["total_cost_usd"])
        if ts:
            current.started_at = current.started_at or ts
            current.ended_at = ts

    flush()
    return ParseResult(turns=turns, new_offset=new_offset, cost_cumulative=cost_cumulative)
