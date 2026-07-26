"""Database access and schema for the usage tracker server.

Backed by SQLAlchemy so the same code runs on SQLite (default), PostgreSQL, or
MySQL — pick one with ``DATABASE_URL``. Timestamps are stored as ISO 8601 strings
(their first 10 chars are the date), which keeps date grouping portable via
``substr`` without per-dialect date functions.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.engine import Connection, Engine

from .settings import get_settings

# SQLAlchemy URL (from settings, i.e. the DATABASE_URL env var), e.g.
# sqlite:///usage.db, postgresql://user:pw@host/db, mysql+pymysql://user:pw@host/db.
# Mutable so tests (and configure()) can retarget the engine.
DATABASE_URL = get_settings().database_url

# Seed rates in USD per million tokens: (input, output, cache_write, cache_read).
# Cache tiers follow Anthropic's standard multipliers (5-min write = 1.25x input,
# read = 0.1x input). Users can override rows at runtime.
MODEL_PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5":    (10.0, 50.0, 12.50, 1.00),
    "claude-opus-4-8":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-7":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-6":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-5":   (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-1":   (15.0, 75.0, 18.75, 1.50),
    "claude-sonnet-5":   (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 3.75, 0.30),
    "claude-haiku-4-5":  (1.0, 5.0, 1.25, 0.10),
}

metadata = MetaData()

# One row per turn (the delta from a single Stop hook), so per-session totals are
# SUM(...) over turns. Timestamps are ISO strings.
usage = Table(
    "usage", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String, nullable=False, index=True),
    Column("account_email", String, default=""),
    Column("session_id", String, nullable=False, index=True),
    Column("turn_index", Integer, default=0),
    Column("cwd", String, default=""),
    Column("timestamp", String, nullable=False, index=True),
    # Date portion (YYYY-MM-DD) of the event time, precomputed at insert so the
    # daily rollup groups by a plain indexed column, portable across dialects.
    Column("day", String, index=True, default=""),
    Column("started_at", String, default=""),
    Column("ended_at", String, default=""),
    Column("model", String, default=""),
    Column("input_tokens", Integer, default=0),
    Column("output_tokens", Integer, default=0),
    Column("cache_read", Integer, default=0),
    Column("cache_write", Integer, default=0),
    Column("cost_usd", Float, default=0.0),
    Column("cost_source", String, default=""),
)

# Per-model rates used to compute cost when the transcript's own cost is 0.
model_pricing = Table(
    "model_pricing", metadata,
    Column("model", String, primary_key=True),
    Column("input_per_mtok", Float, nullable=False),
    Column("output_per_mtok", Float, nullable=False),
    Column("cache_write_per_mtok", Float, nullable=False),
    Column("cache_read_per_mtok", Float, nullable=False),
    Column("updated_at", String, nullable=False),
)

# Who the user is. Email + display name come from the verified id_token; is_admin
# is a per-user flag (see scripts/set_admin.py).
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String, nullable=False, unique=True),
    Column("name", String, nullable=False, default=""),
    Column("is_admin", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False),
)

# API keys the hook sends as Bearer tokens. Only the hash is stored.
api_keys = Table(
    "api_keys", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("label", String, nullable=False, default=""),
    Column("key_hash", String, nullable=False, unique=True),
    Column("prefix", String, nullable=False, default=""),
    Column("created_at", String, nullable=False),
    Column("last_used_at", String),
    Column("revoked_at", String),
)

# Idempotency ledger: ingestion records each event_id once and ignores repeats.
events = Table(
    "events", metadata,
    Column("event_id", String, primary_key=True),
    Column("event_type", String, nullable=False),
    Column("received_at", String, nullable=False),
)

_engine: Engine | None = None


def _normalize_url(url: str) -> str:
    """Point the postgres scheme at the installed psycopg (v3) driver.

    A bare ``postgresql://`` URL (as Neon and others hand out) defaults to
    psycopg2; we ship psycopg 3, so make the driver explicit.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        url = _normalize_url(DATABASE_URL)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        # pool_pre_ping avoids handing out a connection a serverless Postgres
        # (e.g. Neon) has already dropped after idling.
        _engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    return _engine


def configure(url: str) -> None:
    """Point the module at a different database and rebuild the engine.

    Used by tests to target an isolated SQLite file.

    Args:
        url: A SQLAlchemy database URL.
    """
    global DATABASE_URL, _engine
    DATABASE_URL = url
    if _engine is not None:
        _engine.dispose()
    _engine = None


def now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _alembic_config():
    """Build an Alembic config pointed at this project and the current URL."""
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent  # server/
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _normalize_url(DATABASE_URL))
    return cfg


def init_db() -> None:
    """Migrate the database to the latest schema and seed model pricing.

    Alembic is the single source of truth for the schema: ``upgrade head`` both
    creates the tables on a fresh database and applies later migrations on an
    existing one.
    """
    from alembic import command

    command.upgrade(_alembic_config(), "head")

    engine = get_engine()
    with engine.begin() as conn:
        have = {r[0] for r in conn.execute(text("SELECT model FROM model_pricing"))}
        missing = [
            {"model": m, "i": i, "o": o, "cw": cw, "cr": cr, "ts": now()}
            for m, (i, o, cw, cr) in MODEL_PRICING.items()
            if m not in have
        ]
        if missing:
            conn.execute(
                text(
                    "INSERT INTO model_pricing "
                    "(model, input_per_mtok, output_per_mtok, cache_write_per_mtok, "
                    " cache_read_per_mtok, updated_at) "
                    "VALUES (:model, :i, :o, :cw, :cr, :ts)"
                ),
                missing,
            )


@contextmanager
def get_db() -> Generator[Connection, None, None]:
    """Open a database connection; callers commit writes explicitly.

    Yields:
        A SQLAlchemy connection. Use ``.mappings()`` on result sets for
        dict-like rows. The connection is closed when the context exits.
    """
    conn = get_engine().connect()
    try:
        yield conn
    finally:
        conn.close()
