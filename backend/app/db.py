from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session as SyncSession

from app.config import get_settings

settings = get_settings()


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, echo=False, connect_args=_connect_args(url))


# The FastAPI process (API requests) always connects as the least-privileged
# `radar_app` role (see docs/rls.md) — never as the migration/owner role.
# Falls back to DATABASE_URL for the SQLite test suite, where the concept of
# separate Postgres roles doesn't apply.
engine = make_engine(settings.resolved_app_url())
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# RLS/GUC plumbing below is entirely a Postgres concept (set_config doesn't
# exist in SQLite). The backend test suite runs against SQLite specifically
# so it needs no external services — app-layer account_id filtering (every
# router's Depends(get_current_account_id) + explicit WHERE clauses) is what
# that suite actually verifies; RLS itself is verified separately against a
# real Postgres, see docs/rls.md.
_IS_POSTGRES = engine.url.get_backend_name() == "postgresql"


class Base(DeclarativeBase):
    pass


_INFO_KEYS = {"app.account_id": "app_account_id", "app.user_id": "app_user_id"}


@event.listens_for(SyncSession, "after_begin")
def _reapply_rls_context_on_begin(session: SyncSession, transaction, connection) -> None:
    """Why this exists: `session.commit()` releases the SQLAlchemy Session's
    connection back to the pool, and the *next* statement on that same
    AsyncSession may check out a **different** physical connection for its
    autobegin transaction — a Postgres custom GUC set on connection A simply
    isn't there on connection B. Since almost every write endpoint in this
    API does `session.add(x); await session.commit(); await session.refresh(x)`,
    relying on "set it once per request" silently broke on the second
    statement after the first commit (a hard `invalid input syntax for type
    uuid: ""` — Postgres' reset value for a custom GUC once touched, not
    NULL — from the profiles/accounts RLS policies).
    This ORM event fires every time ANY transaction begins on this Session —
    the first one and every autobegin after a commit — so whatever context
    core/security.py stashed in session.info gets re-applied to whichever
    physical connection actually backs the new transaction, every time."""
    if connection.dialect.name != "postgresql":
        return
    for guc_name, info_key in _INFO_KEYS.items():
        value = session.info.get(info_key)
        if value is not None:
            connection.execute(text("SELECT set_config(:name, :value, true)"), {"name": guc_name, "value": value})


async def remember_rls_context(session: AsyncSession, *, account_id: str | None = None, user_id: str | None = None) -> None:
    """The one function core/security.py and app/services/jobs.py call to
    scope a session to an account/user. Stores the value on the session so
    the `after_begin` event above keeps re-applying it to every future
    transaction on this session, AND applies it immediately to the current
    transaction (the event only fires on *begin*, not retroactively)."""
    sync_session = session.sync_session
    if account_id is not None:
        sync_session.info["app_account_id"] = account_id
    if user_id is not None:
        sync_session.info["app_user_id"] = user_id

    if not _IS_POSTGRES:
        return
    if account_id is not None:
        await session.execute(text("SELECT set_config('app.account_id', :v, true)"), {"v": account_id})
    if user_id is not None:
        await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


async def _clear_rls_context(session: AsyncSession) -> None:
    """Defense in depth for connection pooling: once a request/job finishes,
    forget the stashed context (so the after_begin listener stops re-applying
    it) and explicitly blank the GUC on whatever connection is still checked
    out, so a connection that somehow got queried before the next request's
    own auth dependency ran fails closed instead of inheriting a stranger's
    account_id."""
    session.sync_session.info.pop("app_account_id", None)
    session.sync_session.info.pop("app_user_id", None)
    if not _IS_POSTGRES:
        return
    try:
        await session.rollback()
        await session.execute(text("SELECT set_config('app.account_id', '', false), set_config('app.user_id', '', false)"))
        await session.commit()
    except Exception:  # noqa: BLE001 - best-effort cleanup, never block session teardown
        pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await _clear_rls_context(session)
