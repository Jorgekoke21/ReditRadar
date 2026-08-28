"""Integration tests against the REAL Postgres + real roles (docs/rls.md).

Deliberately independent of app.config/Settings and of conftest.py's env
overrides (which force everything to SQLite for the rest of the suite) —
these tests connect directly via SQLAlchemy to the local docker-compose
Postgres using the three roles' well-known local dev credentials, because
they are testing the DATABASE's own role/policy configuration, not the
application code layered on top of it.

Run with (NOT the sqlite-overridden command used for the rest of the suite):
    docker compose run --rm backend pytest tests/test_rls_postgres.py -v

Skips gracefully (not a failure) if `db` doesn't resolve — i.e. if not run
inside the docker-compose network.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.account import Account
from app.models.conversation import Conversation
from app.models.enums import SourceMode

MIGRATION_URL = "postgresql+asyncpg://radarin:radarin@db:5432/radarin_radar"
APP_URL = "postgresql+asyncpg://radar_app:radar_app_dev_only_change_me@db:5432/radarin_radar"
WORKER_URL = "postgresql+asyncpg://radar_worker:radar_worker_dev_only_change_me@db:5432/radarin_radar"


async def _try_connect(url: str):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Postgres not reachable at {url.split('@')[1]} ({exc}) — run inside docker-compose network")
    return engine


@pytest.fixture
async def migration_engine():
    engine = await _try_connect(MIGRATION_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine():
    engine = await _try_connect(APP_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def worker_engine():
    engine = await _try_connect(WORKER_URL)
    yield engine
    await engine.dispose()


async def _seed_two_accounts_with_conversations(migration_engine):
    """Inserts two accounts with one conversation each directly as the
    migration role (which owns the tables and bypasses RLS as a Postgres
    superuser), returning their ids. Uses the ORM table metadata (Core
    insert) rather than hand-written SQL so every NOT NULL/default column
    is filled in the same way the app itself would fill it."""
    account_a, account_b = uuid.uuid4(), uuid.uuid4()
    convo_a, convo_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with migration_engine.begin() as conn:
        for account_id in (account_a, account_b):
            await conn.execute(Account.__table__.insert().values(id=account_id, name="RLS test"))
        for convo_id, account_id in ((convo_a, account_a), (convo_b, account_b)):
            await conn.execute(
                Conversation.__table__.insert().values(
                    id=convo_id,
                    account_id=account_id,
                    source_mode=SourceMode.manual,
                    url="",
                    url_normalized=str(convo_id),
                    dedupe_hash=str(convo_id),
                    subreddit="agency",
                    language="en",
                    detected_at=now,
                )
            )
    return account_a, account_b, convo_a, convo_b


async def test_radar_app_role_has_no_bypassrls(app_engine):
    async with app_engine.connect() as conn:
        result = await conn.execute(text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user"))
        row = result.first()
        assert row.rolbypassrls is False
        assert row.rolsuper is False


async def test_radar_worker_role_has_no_bypassrls(worker_engine):
    async with worker_engine.connect() as conn:
        result = await conn.execute(text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user"))
        row = result.first()
        assert row.rolbypassrls is False
        assert row.rolsuper is False


async def test_radar_app_role_does_not_own_the_tables(app_engine):
    async with app_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT pg_get_userbyid(relowner) AS owner FROM pg_class WHERE relname = 'conversations'")
        )
        owner = result.scalar_one()
        assert owner != "radar_app"
        assert owner == "radarin"


async def test_migration_role_url_differs_from_app_role_url():
    """The migration role must never be the one the running API/worker use."""
    assert MIGRATION_URL != APP_URL
    assert MIGRATION_URL != WORKER_URL
    assert "radarin:radarin" in MIGRATION_URL
    assert "radar_app" in APP_URL
    assert "radar_worker" in WORKER_URL


async def test_radar_app_sees_zero_rows_without_any_account_context(migration_engine, app_engine):
    account_a, account_b, convo_a, convo_b = await _seed_two_accounts_with_conversations(migration_engine)
    try:
        async with app_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT count(*) FROM conversations WHERE id = :a OR id = :b"), {"a": convo_a, "b": convo_b}
            )
            assert result.scalar_one() == 0
    finally:
        async with migration_engine.begin() as conn:
            await conn.execute(text("DELETE FROM conversations WHERE account_id IN (:a, :b)"), {"a": account_a, "b": account_b})
            await conn.execute(text("DELETE FROM accounts WHERE id IN (:a, :b)"), {"a": account_a, "b": account_b})


async def test_radar_app_with_account_a_context_cannot_see_account_b(migration_engine, app_engine):
    account_a, account_b, convo_a, convo_b = await _seed_two_accounts_with_conversations(migration_engine)
    try:
        async with app_engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.account_id', :aid, false)"), {"aid": str(account_a)})
            visible = (
                await conn.execute(
                    text("SELECT id FROM conversations WHERE id = :a OR id = :b"), {"a": convo_a, "b": convo_b}
                )
            ).scalars().all()
            assert visible == [convo_a]
    finally:
        async with migration_engine.begin() as conn:
            await conn.execute(text("DELETE FROM conversations WHERE account_id IN (:a, :b)"), {"a": account_a, "b": account_b})
            await conn.execute(text("DELETE FROM accounts WHERE id IN (:a, :b)"), {"a": account_a, "b": account_b})


async def test_a_fresh_connection_never_inherits_a_previous_connections_account_context(app_engine):
    """'El pool no filtra account_id entre conexiones': two independent
    connections (as two independent requests would get from the pool) must
    never share GUC state — proves connection-level isolation regardless of
    whatever the app's own session-reset logic does."""
    fake_account = uuid.uuid4()
    async with app_engine.connect() as conn1:
        await conn1.execute(text("SELECT set_config('app.account_id', :aid, false)"), {"aid": str(fake_account)})
        value_on_conn1 = (await conn1.execute(text("SELECT current_setting('app.account_id', true)"))).scalar_one()
        assert value_on_conn1 == str(fake_account)

    async with app_engine.connect() as conn2:
        value_on_conn2 = (await conn2.execute(text("SELECT current_setting('app.account_id', true)"))).scalar_one()
        assert value_on_conn2 in (None, "")


async def test_two_concurrent_connections_keep_independent_account_context(app_engine):
    """'Dos solicitudes concurrentes mantienen aislamiento': runs two account
    contexts truly concurrently (asyncio.gather) on two separate connections
    and confirms neither ever observes the other's value mid-flight."""
    import asyncio

    account_x, account_y = uuid.uuid4(), uuid.uuid4()

    async def _hold_context(account_id: uuid.UUID, delay: float) -> str:
        async with app_engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.account_id', :aid, false)"), {"aid": str(account_id)})
            await asyncio.sleep(delay)
            return (await conn.execute(text("SELECT current_setting('app.account_id', true)"))).scalar_one()

    result_x, result_y = await asyncio.gather(_hold_context(account_x, 0.05), _hold_context(account_y, 0.01))
    assert result_x == str(account_x)
    assert result_y == str(account_y)


async def test_radar_worker_can_enumerate_accounts_but_still_needs_context_for_conversations(migration_engine, worker_engine):
    account_a, account_b, convo_a, convo_b = await _seed_two_accounts_with_conversations(migration_engine)
    try:
        async with worker_engine.connect() as conn:
            # The one narrow extra grant: listing account ids works with no context set.
            ids = (await conn.execute(text("SELECT id FROM accounts WHERE id = :a OR id = :b"), {"a": account_a, "b": account_b})).scalars().all()
            assert set(ids) == {account_a, account_b}

            # But conversations are still fully account-scoped for radar_worker —
            # the extra grant does not leak into any other table.
            visible = (await conn.execute(text("SELECT id FROM conversations WHERE id = :a OR id = :b"), {"a": convo_a, "b": convo_b})).scalars().all()
            assert visible == []

            await conn.execute(text("SELECT set_config('app.account_id', :aid, false)"), {"aid": str(account_a)})
            visible_a = (await conn.execute(text("SELECT id FROM conversations WHERE id = :a OR id = :b"), {"a": convo_a, "b": convo_b})).scalars().all()
            assert visible_a == [convo_a]
    finally:
        async with migration_engine.begin() as conn:
            await conn.execute(text("DELETE FROM conversations WHERE account_id IN (:a, :b)"), {"a": account_a, "b": account_b})
            await conn.execute(text("DELETE FROM accounts WHERE id IN (:a, :b)"), {"a": account_a, "b": account_b})


async def test_radar_app_cannot_list_accounts_it_does_not_own(migration_engine, app_engine):
    """Unlike radar_worker, radar_app has NO special accounts-listing grant
    — confirms the extra policy really is narrowly scoped to radar_worker."""
    account_a, account_b, convo_a, convo_b = await _seed_two_accounts_with_conversations(migration_engine)
    try:
        async with app_engine.connect() as conn:
            ids = (await conn.execute(text("SELECT id FROM accounts WHERE id = :a OR id = :b"), {"a": account_a, "b": account_b})).scalars().all()
            assert ids == []
    finally:
        async with migration_engine.begin() as conn:
            await conn.execute(text("DELETE FROM conversations WHERE account_id IN (:a, :b)"), {"a": account_a, "b": account_b})
            await conn.execute(text("DELETE FROM accounts WHERE id IN (:a, :b)"), {"a": account_a, "b": account_b})
