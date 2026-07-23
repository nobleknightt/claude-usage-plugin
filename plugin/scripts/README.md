# Hook scripts

The client half of the Claude Usage Tracker plugin. These run as Claude Code
hooks and **never block the session** — they parse the turn's transcript, write to
a local durable queue, and sync to the server in the background. See the
[root README](../../README.md) for the whole system.

## Files

| File | Role |
|---|---|
| `track.py` | **Stop** hook. Reads hook stdin, parses the transcript, builds a usage event, enqueues it, kicks off a drain, and exits `0`. Pure observer — never writes decision output. |
| `sync.py` | **SessionEnd** hook (and the drain step). Ships queued events to the server with `Authorization: Bearer` and backoff; removes them once the server confirms. |
| `storage.py` | The local SQLite outbox at `$CLAUDE_PLUGIN_DATA/events.db` (`enqueue` / `claim_pending` / `mark_synced` / …). |
| `transcript.py` | Transcript parsing + token/cost extraction. |
| `config.py` | Reads config (`API_KEY`, `BASE_URL`) and resolves data-dir paths. |
| `pyproject.toml` | Lets `uv run` provision Python (stdlib only — no third-party deps). |

## How it works

```
Stop hook → track.py: parse transcript → enqueue event → exit 0   (never waits on the network)
            queued events → POST /api/events/batch  (idempotent on event_id, with backoff)
SessionEnd → sync.py: final drain of anything still pending
```

If the server is down, events stay `pending` in the local queue and sync on a later
run — **zero data loss**.

- **Identity** is the `API_KEY` (resolved to a user server-side); it is never
  self-reported in the payload.
- **`account_email`** is read live from `~/.claude.json` each run — the shared Claude
  account the usage is billed against.
- Only **metrics** are sent per turn — token counts, model, cost, session id, and
  `cwd`. Prompts, assistant responses, and tool inputs/outputs are **never** sent.

## Configuration

Set at install as the plugin's `userConfig` and injected into the hooks as
environment variables:

| Config | Notes |
|---|---|
| `API_KEY` | Sensitive. Generated for you in the dashboard. |
| `BASE_URL` | The usage tracker server's URL. |

## Install / local dev

Install via the marketplace (see the root README):

```bash
claude plugin install claude-usage@claude-usage \
  --config API_KEY=<key> --config BASE_URL=<server-url>
```

Hooks are declared in [`../hooks/hooks.json`](../hooks/hooks.json) and invoked with
`uv run --project ${CLAUDE_PLUGIN_ROOT}/scripts python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py`,
so `uv` provisions the Python runtime automatically — nothing to install by hand.
Runtime data (the queue and logs) lives under `${CLAUDE_PLUGIN_DATA}`.
