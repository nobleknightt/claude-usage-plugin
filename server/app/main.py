"""
Claude Code per-user token usage tracker — FastAPI + SQLite server.

Run (development):
  uv run fastapi dev app/main.py

Run (production):
  uv run fastapi run app/main.py
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import auth, keys
from .auth import current_user
from .db import get_db, init_db, now
from .keys import require_api_key
from .settings import get_settings

__version__ = "0.1.0"

# main.py and the client both live under server/app/.
CLIENT_DIST = Path(__file__).resolve().parent / "client" / "dist"
settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("usage-tracker")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    if not settings.auth_configured:
        logger.warning("Entra auth not configured — login endpoints will return 503")
    yield


app = FastAPI(
    title="Claude Usage",
    description="Per-user Claude Code token & cost tracking",
    version=__version__,
    lifespan=lifespan,
    # API docs are exposed only in development; hidden in production.
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

# Signs the session cookie that carries the logged-in dashboard user.
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

# Cookies require explicit origins + credentials (never "*" with credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UsageEvent(BaseModel):
    account_email: str   = ""
    session_id:    str
    cwd:           str   = ""
    timestamp:     str   = ""
    model:         str   = ""
    input_tokens:  int   = 0
    output_tokens: int   = 0
    cache_read:    int   = 0
    cache_write:   int   = 0
    cost_usd:      float = 0.0


class EventEnvelope(BaseModel):
    event_id:   str
    event_type: str  = "usage"
    payload:    dict = {}


class EventBatch(BaseModel):
    events: list[EventEnvelope]


router = APIRouter(prefix="/api")


def _insert_usage(conn, email: str, p: dict) -> None:
    """Write one usage row from a hook payload.

    Args:
        conn: An open database connection.
        email: The owning user's email, resolved from the API key.
        p: The event payload with token counts, model, cost, and session info.
    """
    conn.execute(
        """
        INSERT INTO usage
            (email, account_email, session_id, cwd, timestamp, model,
             input_tokens, output_tokens, cache_read, cache_write, cost_usd)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            email,
            p.get("account_email", ""),
            p.get("session_id", ""),
            p.get("cwd", ""),
            p.get("timestamp") or now(),
            p.get("model", ""),
            p.get("input_tokens", 0),
            p.get("output_tokens", 0),
            p.get("cache_read", 0),
            p.get("cache_write", 0),
            p.get("cost_usd", 0.0),
        ),
    )


@router.post("/events/batch", summary="Ingest a batch of hook events (idempotent)")
def ingest_batch(batch: EventBatch, user: dict = Depends(require_api_key)) -> dict:
    """Ingest a batch of hook events (the plugin sync worker's primary path).

    Idempotent on ``event_id``: an event already in the ledger is skipped, so a
    client retry after a network blip never double-counts.

    Args:
        batch: The batch of event envelopes to ingest.
        user: The owning user, resolved from the Bearer API key.

    Returns:
        Counts of newly ``accepted`` events and skipped ``duplicates``.
    """
    accepted = duplicates = 0
    with get_db() as conn:
        for ev in batch.events:
            cur = conn.execute(
                "INSERT OR IGNORE INTO events (event_id, event_type, received_at) "
                "VALUES (?, ?, ?)",
                (ev.event_id, ev.event_type, now()),
            )
            if cur.rowcount == 0:
                duplicates += 1
                continue
            _insert_usage(conn, user["email"], ev.payload)
            accepted += 1
        conn.commit()
    return {"accepted": accepted, "duplicates": duplicates}


@router.post("/usage", summary="Ingest one Stop-hook event (legacy)")
def record_usage(event: UsageEvent, user: dict = Depends(require_api_key)) -> dict:
    """Ingest a single usage event (legacy, non-idempotent path).

    Args:
        event: The single usage event to record.
        user: The owning user, resolved from the Bearer API key.

    Returns:
        ``{"ok": True}`` once the row is written.
    """
    # Identity is the API key, resolved server-side — never self-reported.
    ts = event.timestamp or datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        _insert_usage(conn, user["email"], {**event.model_dump(), "timestamp": ts})
        conn.commit()
    return {"ok": True}


def _visibility_filter(user: dict, requested: Optional[str]) -> tuple[str, list]:
    """Build the WHERE clause enforcing who can see whose rows.

    - Admin: everything (optionally narrowed to a requested email).
    - Account owner: their own rows plus everyone whose usage is billed to the
      Claude account they own. Ownership means the logged-in email equals the
      ``account_email`` (which is the Claude account's own address).
    - Everyone else (co-users borrowing someone else's account): only their own.

    A ``requested`` email narrows the result to that user, but always *within*
    the caller's allowed scope — so an account owner can filter to a co-user on
    their account, but not to someone outside it.

    Args:
        user: The logged-in dashboard user.
        requested: An optional email to narrow to (constrained to the scope).

    Returns:
        A ``(clause, params)`` pair; ``clause`` is empty when no filter applies.
    """
    conditions: list[str] = []
    params: list = []
    if not user["is_admin"]:
        # own usage OR usage billed to the account this user owns
        conditions.append("(email = ? OR account_email = ?)")
        params += [user["email"], user["email"]]
    if requested:
        conditions.append("email = ?")
        params.append(requested)
    return " AND ".join(conditions), params


@router.get("/summary", summary="Per-user aggregated totals")
def summary(
    user:      dict          = Depends(current_user),
    email:     Optional[str] = Query(None, description="Filter by email (admin only)"),
    from_date: Optional[str] = Query(None, alias="from", description="YYYY-MM-DD"),
    to_date:   Optional[str] = Query(None, alias="to",   description="YYYY-MM-DD"),
) -> list[dict]:
    """Return per-user aggregated usage totals within the visible scope.

    Args:
        user: The logged-in dashboard user (sets the visibility scope).
        email: Optional email filter (admins only).
        from_date: Optional inclusive start date (YYYY-MM-DD).
        to_date: Optional inclusive end date (YYYY-MM-DD).

    Returns:
        One dict per (user, account) with session count, token totals, cost,
        and last-seen timestamp.
    """
    conditions, params = _date_filter_parts(from_date, to_date)
    vis_clause, vis_params = _visibility_filter(user, email)
    if vis_clause:
        conditions.append(vis_clause)
        params += vis_params
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_db() as conn:
        # Each row holds the session's cumulative totals as of that turn
        # (same as cost_usd), not a per-turn delta — so per-session totals
        # must be MAX(...), never SUM(...), or multi-turn sessions get
        # counted once per turn instead of once. Collapse to one row per
        # session first, then SUM those session totals per user.
        rows = conn.execute(
            f"""
            WITH session_totals AS (
                SELECT
                    session_id,
                    email,
                    account_email,
                    MAX(input_tokens)  AS input_tokens,
                    MAX(output_tokens) AS output_tokens,
                    MAX(cache_read)    AS cache_read,
                    MAX(cache_write)   AS cache_write,
                    MAX(cost_usd)      AS cost_usd,
                    MAX(timestamp)     AS last_seen
                FROM usage
                {where}
                GROUP BY session_id
            )
            SELECT
                email,
                account_email,
                COUNT(*)                   AS sessions,
                SUM(input_tokens)          AS input_tokens,
                SUM(output_tokens)         AS output_tokens,
                SUM(cache_read)            AS cache_read,
                SUM(cache_write)           AS cache_write,
                ROUND(SUM(cost_usd), 6)   AS cost_usd,
                MAX(last_seen)             AS last_seen
            FROM session_totals
            GROUP BY email, account_email
            ORDER BY cost_usd DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/sessions", summary="Per-session breakdown")
def sessions(
    user:      dict          = Depends(current_user),
    email:     Optional[str] = Query(None, description="Filter by email (admin only)"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
    limit:     int           = Query(100, ge=1, le=1000),
) -> list[dict]:
    """Return a per-session breakdown within the visible scope.

    Args:
        user: The logged-in dashboard user (sets the visibility scope).
        email: Optional email filter (admins only).
        from_date: Optional inclusive start date (YYYY-MM-DD).
        to_date: Optional inclusive end date (YYYY-MM-DD).
        limit: Maximum number of sessions to return.

    Returns:
        One dict per session with its cwd, model, timing, token totals,
        and cost.
    """
    conditions, params = _date_filter_parts(from_date, to_date)
    vis_clause, vis_params = _visibility_filter(user, email)
    if vis_clause:
        conditions.append(vis_clause)
        params += vis_params
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_db() as conn:
        # cwd/model can change between turns of the same session (cd,
        # model switch), so a bare column under GROUP BY session_id would
        # return an arbitrary row's value, not necessarily the latest one.
        # Pull those two from the most recent row per session explicitly.
        rows = conn.execute(
            f"""
            SELECT
                email,
                account_email,
                session_id,
                (SELECT cwd FROM usage u2
                 WHERE u2.session_id = usage.session_id
                 ORDER BY timestamp DESC LIMIT 1)  AS cwd,
                (SELECT model FROM usage u2
                 WHERE u2.session_id = usage.session_id
                 ORDER BY timestamp DESC LIMIT 1)  AS model,
                MIN(timestamp)              AS started_at,
                MAX(timestamp)              AS last_turn_at,
                COUNT(*)                    AS turns,
                MAX(input_tokens)           AS input_tokens,
                MAX(output_tokens)          AS output_tokens,
                MAX(cache_read)             AS cache_read,
                MAX(cache_write)            AS cache_write,
                ROUND(MAX(cost_usd), 6)    AS cost_usd
            FROM usage
            {where}
            GROUP BY session_id
            ORDER BY last_turn_at DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/usage/daily", summary="Per-day token totals for the activity heatmap")
def usage_daily(
    user:      dict          = Depends(current_user),
    email:     Optional[str] = Query(None, description="Filter by email (admin only)"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
) -> list[dict]:
    """Return per-day token totals for the GitHub-style activity heatmap.

    Intensity is input+output tokens (cache excluded so it isn't distorted).
    Rows are cumulative snapshots, so we take the max per session per day first,
    then sum across sessions for that day.

    Args:
        user: The logged-in dashboard user (sets the visibility scope).
        email: Optional email filter (admins only).
        from_date: Optional inclusive start date (YYYY-MM-DD).
        to_date: Optional inclusive end date (YYYY-MM-DD).

    Returns:
        One dict per active day: ``date`` (YYYY-MM-DD), ``tokens``, ``cost_usd``.
    """
    conditions, params = _date_filter_parts(from_date, to_date)
    vis_clause, vis_params = _visibility_filter(user, email)
    if vis_clause:
        conditions.append(vis_clause)
        params += vis_params
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            WITH per_session_day AS (
                SELECT
                    date(timestamp)                        AS day,
                    session_id,
                    MAX(input_tokens) + MAX(output_tokens) AS tokens,
                    MAX(cost_usd)                          AS cost_usd
                FROM usage
                {where}
                GROUP BY date(timestamp), session_id
            )
            SELECT
                day                     AS date,
                SUM(tokens)             AS tokens,
                ROUND(SUM(cost_usd), 6) AS cost_usd
            FROM per_session_day
            GROUP BY day
            ORDER BY day
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/health", summary="Health check")
def health() -> dict:
    """Report server liveness.

    Returns:
        ``{"status": "ok"}``.
    """
    return {"status": "ok"}


def _date_filter_parts(
    from_date: Optional[str], to_date: Optional[str]
) -> tuple[list[str], list[str]]:
    """Build SQL conditions for an optional inclusive date range.

    Args:
        from_date: Optional inclusive start date (YYYY-MM-DD).
        to_date: Optional inclusive end date (YYYY-MM-DD).

    Returns:
        A ``(conditions, params)`` pair to fold into a WHERE clause.
    """
    conditions: list[str] = []
    params:     list[str] = []
    if from_date:
        conditions.append("timestamp >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("timestamp <= ?")
        params.append(to_date + "T23:59:59")
    return conditions, params


app.include_router(router)
app.include_router(auth.router)
app.include_router(keys.router)

# app.frontend() serves the built SPA as low-priority routes: the /api
# path operations above are matched first, and any unmatched browser
# navigation (e.g. deep-linking /sessions) falls back to index.html so
# client-side routing works instead of 404ing. See
# https://fastapi.tiangolo.com/tutorial/frontend/
if CLIENT_DIST.is_dir():
    app.frontend("/", directory=CLIENT_DIST)
else:
    logger.info("client/dist not found — run `bun run build` in server/client/ to serve the dashboard")
