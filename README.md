# Claude Usage

Per-user token, cost, and session tracking for Claude Code — built for teams that
**share a single Claude account**.

Claude Code's built-in `/usage` reports against whoever is logged in. When a team
shares one Claude subscription there's no way to see who consumed what. This project
fixes that: a Claude Code **plugin** tags every turn with the user's identity (via an
API key) and ships it to a small self-hosted **server** with a dashboard.

## What's inside

- **[`plugin/`](plugin/)** — the Claude Code plugin. `Stop`/`SessionEnd` hooks parse
  each turn's transcript, write to a local durable SQLite queue, and sync to the
  server in the background. See [`plugin/scripts/README.md`](plugin/scripts/README.md).
- **[`server/`](server/)** — FastAPI + SQLite server and a React (Vite + shadcn)
  dashboard, served by the same process: Entra ID login, API-key management, and
  per-role visibility. See [`server/README.md`](server/README.md).
- **[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)** — marketplace
  manifest so the plugin can be installed by path or from a git remote.

## How it works

```
Claude Code turn ends
  → Stop hook (plugin) → parse transcript → local SQLite queue → exit (never blocks)
  → async sync → POST /api/events/batch   (Authorization: Bearer <API_KEY>, idempotent)
  → server SQLite → dashboard
```

- **Identity** is the API key, resolved server-side — never self-reported by the client.
- **`account_email`** is the shared Claude account (read live from `~/.claude.json`),
  used to reconcile who is on which account.
- The hook is **local-first**: if the server is down, events stay queued and sync on a
  later run. Zero data loss.

## Roles & visibility

| Role | Sees |
|---|---|
| **Admin** | Everything, org-wide |
| **Account owner** (login email == the Claude account's email) | All usage billed to their account |
| **Member** | Only their own usage |

## Quick start

**1. Run the server** (needs [uv](https://docs.astral.sh/uv/) + [bun](https://bun.com/)):

```bash
cd server
cp .env.example .env          # fill in Entra + SESSION_SECRET, or set ENVIRONMENT=development
cd app/client && bun install && bun run build && cd ../..   # build the dashboard
uv run --env-file .env fastapi run app/main.py              # http://localhost:8000
# …or one command with Docker:  docker compose up --build
```

**2. Get an API key** — sign in to the dashboard and create one under **API keys**.
(First admin: `cd server && uv run python -m scripts.set_admin you@example.com`.)

**3. Install the plugin:**

```bash
claude plugin marketplace add /path/to/claude-usage-plugin
claude plugin install claude-usage@claude-usage \
  --config API_KEY=<your key> --config BASE_URL=http://localhost:8000
```

Use Claude Code as normal — usage shows up on the dashboard.

## Requirements

- **uv** (Python ≥ 3.14) — server and hook
- **bun** — dashboard build
- **Claude Code** — to run the plugin
