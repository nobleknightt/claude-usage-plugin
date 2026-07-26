# Claude Usage Plugin

Per-user token, cost, and session tracking for Claude Code — built for teams that
**share a single Claude account**.

Claude Code's built-in `/usage` reports against whoever is logged in. When a team
shares one Claude subscription there's no way to see who consumed what. This project
fixes that: a Claude Code **plugin** tags every turn with the user's identity (via an
API key) and ships it to a small self-hosted **server** with a dashboard.

## What's inside

- **[`plugin/`](plugin/)** — the Claude Code plugin: `Stop`/`SessionEnd` hooks parse
  each turn's transcript, queue it locally, and sync to the server in the background.
  See [`plugin/README.md`](plugin/README.md).
- **[`server/`](server/)** — FastAPI + SQLite server and a React dashboard: Microsoft
  Entra ID / Google OAuth sign-in, API-key management, and per-role visibility. See
  [`server/README.md`](server/README.md) to run it.

## How it works

- **Identity** is the API key, resolved server-side — never self-reported by the client.
- **Account** is the shared Claude account (read live from `~/.claude.json`), used to
  reconcile who is on which account.
- The hook is **local-first**: if the server is down, events stay queued and sync on a
  later run. Zero data loss.

## Roles & visibility

| Role | Sees |
|---|---|
| **Admin** | Everything, org-wide |
| **Account owner** (whose login email matches the Claude account's email) | All usage billed to their account |
| **Member** | Only their own usage |

## Install the plugin

You need a running server ([set one up](server/README.md)) and, from its dashboard,
an `API_KEY` (**API keys** tab) plus the server's URL for `BASE_URL`.

The hooks run on [`uv`](https://docs.astral.sh/uv/), so install it first:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then install from the marketplace `nobleknightt/claude-usage-plugin` — pick one:

- **CLI (scriptable):**
  ```bash
  claude plugin marketplace add nobleknightt/claude-usage-plugin
  claude plugin install claude-usage@claude-usage --config API_KEY=<key> --config BASE_URL=<url>
  ```
- **Interactive:** run `/plugin`, install `claude-usage`, enter config when prompted.
- **VS Code:** the graphical `/plugins` panel can't enter config — open a terminal from
  the Claude panel's `/` menu (**Open Claude in Terminal**), then run `/plugin`.

After an interactive install, run `/reload-plugins` to activate it. Then use Claude
Code as normal — usage shows up on the dashboard.

---

To run the server, see [`server/README.md`](server/README.md). For plugin internals
and development, see [`plugin/README.md`](plugin/README.md).
