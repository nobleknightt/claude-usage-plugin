# Server

FastAPI + SQLite backend and the bundled React dashboard for **Claude Usage**. A
single process ingests events, serves the query API, and serves the built SPA.
See the [root README](../README.md) for the big picture.

## Layout

```
server/
├── app/
│   ├── main.py       # routes: ingestion, usage/summary/sessions/daily, health; serves the SPA
│   ├── auth.py       # Entra ID (OIDC) login, session JWT, current_user dependency
│   ├── keys.py       # API key create/list/revoke + Bearer validation
│   ├── db.py         # SQLite schema + access
│   ├── settings.py   # environment configuration
│   └── client/       # React (Vite + shadcn) dashboard
├── scripts/
│   └── set_admin.py  # grant/revoke admin by email
├── tests/            # unittest suite
├── Dockerfile
└── compose.yaml
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python ≥ 3.14)
- [bun](https://bun.com/) — to build the dashboard

## Run (development)

```bash
cp .env.example .env      # fill in Entra values, or set ENVIRONMENT=development
cd app/client && bun install && bun run build && cd ../..   # build the SPA once
uv run --env-file .env fastapi run app/main.py              # http://localhost:8000
```

For live dashboard development run Vite separately: `cd app/client && bun run dev`
(serves on `:5173`; keep that origin in `CORS_ORIGINS`).

## Run (Docker)

```bash
docker compose up --build
```

Builds the dashboard and server image in one shot; the SQLite DB is persisted on the
`usage-data` volume.

## Deploy server

You only need `server/` — it's self-contained (the Docker build bundles the dashboard;
nothing from `plugin/` is required).

Copy just this folder with [`degit`](https://github.com/Rich-Harris/degit) (downloads a
repo subdirectory without git history), run via `bunx`:

```bash
bunx degit@latest nobleknightt/claude-usage-plugin/server claude-usage-server
cd claude-usage-server
cp .env.example .env          # set ENVIRONMENT=production, Entra creds, SESSION_SECRET
docker compose up -d --build
```

For production, terminate TLS in front of the container and register
`https://<host>/api/auth/microsoft/callback` as the Entra **Web** redirect URI. Seed the
first admin once someone has logged in:

```bash
docker compose exec server python -m scripts.set_admin you@example.com
```

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE` | SQLite path (default `usage.db`; compose uses `/data/usage.db`) |
| `ENTRA_TENANT_ID` / `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` | Azure app registration |
| `ENTRA_REDIRECT_URI` | Must match a **Web** redirect URI registered in Azure |
| `FRONTEND_URL` | Where the browser lands after login |
| `SESSION_SECRET` | Signs the session cookie / JWT (set a long random value) |
| `CORS_ORIGINS` | Comma-separated browser origins allowed with credentials |
| `ENVIRONMENT` | `production` (default) or `development` |

`.env` is gitignored — safe for secrets.

## Auth & roles

- **Dashboard login:** Microsoft Entra ID (OIDC). When `ENVIRONMENT=development`, a
  dev shortcut `GET /api/auth/login?email=<email>` logs in without Entra (404 in
  production).
- **API keys:** created in the dashboard; the hook sends one as
  `Authorization: Bearer`. Only the SHA-256 hash is stored.
- **Roles:** `admin` (all), account **owner** (login email == `account_email` → all
  usage on that account), `member` (own only). Admin is a per-user flag:

  ```bash
  uv run python -m scripts.set_admin you@example.com          # grant (creates the user if new)
  uv run python -m scripts.set_admin you@example.com --revoke # remove
  ```

## API (summary)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/events/batch` | Ingest events (Bearer key, idempotent on `event_id`) |
| `GET` | `/api/me` | Current user + role |
| `GET`/`POST`/`DELETE` | `/api/keys[/{id}]` | Manage API keys |
| `GET` | `/api/summary`, `/api/sessions`, `/api/usage/daily` | Usage queries (role-scoped; `?email=` to filter) |
| `GET` | `/api/health` | Liveness |

## Tests

```bash
uv run python -m unittest
```
