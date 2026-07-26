# Server

FastAPI + SQLite backend and the bundled React dashboard for **Claude Usage**. A
single process ingests events, serves the query API, and serves the built dashboard.
See the [root README](../README.md) for the big picture.

## Layout

```
server/
├── app/
│   ├── main.py       # routes: ingestion, usage/summary/sessions/daily, health; serves the dashboard
│   ├── auth.py       # Microsoft Entra ID + Google OAuth (OIDC), session JWT, current_user dependency
│   ├── keys.py       # API key create/list/revoke + Bearer validation
│   ├── db.py         # SQLAlchemy engine + schema (SQLite/Postgres/MySQL)
│   ├── settings.py   # environment configuration
│   └── client/       # React (Vite + shadcn) dashboard
├── alembic/          # database migrations
├── scripts/
│   └── set_admin.py  # grant/revoke admin by email
├── tests/            # unittest suite
├── Dockerfile
└── compose.yaml
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python ≥ 3.14)
- [bun](https://bun.com/) — to build the dashboard

## Database

The server runs on **SQLite, PostgreSQL, or MySQL** — set `DATABASE_URL`:

```
sqlite:///usage.db                          # default
postgresql://user:password@host/dbname      # add ?sslmode=require for hosted PG
mysql+pymysql://user:password@host/dbname
```

The Postgres and MySQL drivers are optional extras (SQLite needs none). For local
runs install the one you need; the Docker image bundles both, so any `DATABASE_URL`
works there without a rebuild:

```bash
uv sync --extra postgres   # or --extra mysql
```

**Migrations** are managed by [Alembic](https://alembic.sqlalchemy.org/) and applied
automatically on startup (`init_db()` runs `alembic upgrade head`), so a fresh
database is created and an existing one upgraded before the server serves traffic.
After changing the schema in `app/db.py`, generate a migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

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
cp .env.example .env          # set ENVIRONMENT=production, provider credentials, SESSION_SECRET
docker compose up -d --build
```

For production, terminate TLS in front of the container and register your provider's
callback as an authorized redirect URI: `https://<host>/api/auth/microsoft/callback` for
Microsoft Entra ID (its **Web** platform), or `https://<host>/api/auth/google/callback`
for Google OAuth. Seed the first admin once someone has logged in:

```bash
docker compose exec server python -m scripts.set_admin you@example.com
```

## Expose with ngrok (self-hosting without a public domain)

If the machine has no public hostname/TLS, [ngrok](https://ngrok.com) gives you an HTTPS
URL for the OAuth redirect (both Microsoft Entra ID and Google OAuth require an HTTPS
**hostname** — a bare IP won't do).
Run ngrok as a container **on the server's compose network** so it reaches the app at
`server:8000` (the container's internal port — no host port needed):

```bash
# 1. start the server (creates the claude-usage_default network)
docker compose up -d --build

# 2. start ngrok, joined to that network, with your reserved domain + authtoken
docker run -d --name ngrok --restart unless-stopped \
  --network claude-usage_default \
  -e NGROK_AUTHTOKEN=<token> \
  ngrok/ngrok:latest http server:8000 --url=https://<your-domain>.ngrok-free.app
```

Then:
- set your provider's redirect URI in `.env` to
  `https://<your-domain>.ngrok-free.app/api/auth/<provider>/callback` — `ENTRA_REDIRECT_URI`
  for Microsoft Entra ID, `GOOGLE_REDIRECT_URI` for Google OAuth — and register that exact
  URL with the provider;
- point the plugin at `--config BASE_URL=https://<your-domain>.ngrok-free.app`;
- verify: `curl https://<your-domain>.ngrok-free.app/api/health`.

Notes: use a **reserved/static domain** so the URL survives restarts (provider redirect
URIs are pre-registered); ngrok **free allows one agent session** at a time; and the client
already sends an `ngrok-skip-browser-warning` header so the dashboard's API calls
aren't blocked by ngrok's free-tier interstitial.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL (default `sqlite:///usage.db`; also Postgres/MySQL — see Database below) |
| `ENTRA_TENANT_ID` / `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` | Azure app registration (optional if using Google OAuth) |
| `ENTRA_REDIRECT_URI` | Must match a **Web** redirect URI registered in Azure |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client (optional if using Microsoft Entra ID) |
| `GOOGLE_REDIRECT_URI` | Must match an authorized redirect URI on the Google client |
| `FRONTEND_URL` | Where the browser lands after login |
| `SESSION_SECRET` | Signs the session cookie / JWT (set a long random value) |
| `CORS_ORIGINS` | Comma-separated browser origins allowed with credentials |
| `ENVIRONMENT` | `production` (default) or `development` |

`.env` is gitignored — safe for secrets.

## Auth & roles

- **Dashboard login:** Microsoft Entra ID and/or Google OAuth (OIDC). Configure either or
  both; the sign-in screen shows a button per configured provider. Users are keyed by
  email, so the same address works across providers. When `ENVIRONMENT=development`, a
  dev shortcut `GET /api/auth/login?email=<email>` logs in without a provider; it is
  disabled in production (the route returns 404).
- **API keys:** created in the dashboard; the hook sends one as
  `Authorization: Bearer`. Only the SHA-256 hash is stored.
- **Roles:** an `admin` sees everything; an account **owner** (whose login email
  matches the account's `account_email`) sees all usage on that account; a `member`
  sees only their own. Admin is a per-user flag:

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
| `GET` | `/api/summary`, `/api/sessions`, `/api/sessions/{id}`, `/api/usage/daily`, `/api/accounts` | Usage queries (role-scoped; `?email=` to filter) |
| `GET` | `/api/health` | Liveness |

## Development

Run from source (builds the dashboard once, then serves the API and dashboard):

```bash
cp .env.example .env      # fill in provider credentials, or set ENVIRONMENT=development
cd app/client && bun install && bun run build && cd ../..   # build the dashboard once
uv run --env-file .env fastapi run app/main.py              # http://localhost:8000
```

For live dashboard work, run Vite separately (`cd app/client && bun run dev`); it
serves on `http://localhost:5173`. The browser calls the API from that origin, so it
must be listed in `CORS_ORIGINS` in `.env` — a comma-separated list:

```
CORS_ORIGINS=http://localhost:8000,http://localhost:5173
```

Run the tests:

```bash
uv run python -m unittest
```
