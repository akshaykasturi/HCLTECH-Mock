"""Database engine and sessions. DATABASE_URL picks the database: empty = local SQLite file
backend/app.db, otherwise e.g. a Postgres URL from Render/Neon. Tables are created on first use.

An unreachable database must never take the app down: creating the engine does not connect,
Postgres connections time out after DB_CONNECT_TIMEOUT_S, and table creation is retried on the
next use until it succeeds. db_status() is the last known state, shown by /health."""
import re
import threading
from functools import lru_cache

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import BACKEND_DIR, get_settings
from app.db.models import Base

_lock = threading.Lock()
_state = {"tables_ready": False, "status": "unknown"}  # status: unknown | ok | unavailable


def normalize_url(url: str) -> str:
    """Hosts hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named (psycopg 3)."""
    if not url:
        return f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def dialect() -> str:
    """postgresql, sqlite, ...: safe to show. Never the URL itself."""
    return make_url(normalize_url(get_settings().database_url)).get_backend_name()


def mask(text: str) -> str:
    """Remove the database URL and its host from an error message before it is logged."""
    url = make_url(normalize_url(get_settings().database_url))
    text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", "<url masked>", text)
    if url.host:
        text = text.replace(url.host, "<host masked>")
    return text


def connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql"):
        return {"connect_timeout": get_settings().db_connect_timeout_s}
    return {}


@lru_cache
def get_engine() -> Engine:
    """Builds the engine without connecting, so this never fails because the database is down."""
    url = normalize_url(get_settings().database_url)
    # pool_pre_ping: test a pooled connection before using it (Neon closes idle connections)
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args(url))


def ensure_tables() -> None:
    """Create missing tables once (no Alembic, never alters existing ones). Raises if the database
    can't be reached; the next call tries again, so the app recovers when the database comes back."""
    if _state["tables_ready"]:
        return
    with _lock:
        if not _state["tables_ready"]:
            try:
                Base.metadata.create_all(get_engine())
            except Exception:
                _state["status"] = "unavailable"
                raise
            _state["tables_ready"] = True
            _state["status"] = "ok"


def set_db_status(available: bool) -> None:
    _state["status"] = "ok" if available else "unavailable"


def db_status() -> str:
    return _state["status"]


def reset_db_state() -> None:
    """Forget the cached engine and state (tests that switch DATABASE_URL)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    _sessionmaker.cache_clear()
    _state.update(tables_ready=False, status="unknown")


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_sessionmaker() -> sessionmaker[Session]:
    ensure_tables()
    return _sessionmaker()
