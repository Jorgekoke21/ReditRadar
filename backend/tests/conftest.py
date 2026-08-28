"""Test fixtures. Runs against a throwaway SQLite file DB (not Postgres) so
the suite needs no external services — every model uses portable SQLAlchemy
types (Uuid, JSON, Enum(native_enum=False)) specifically so this works.
Postgres-only features (the RLS policies in migration 0002) are exercised
manually against the real docker-compose stack instead; see docs/testing.md.
"""

import os
import uuid

# All three role-specific URLs must be forced to the same SQLite file —
# otherwise docker-compose's baked-in DATABASE_APP_URL/DATABASE_MIGRATION_URL
# env vars (set for the real Postgres roles) win over DATABASE_URL, since
# Settings.resolved_app_url() prefers the role-specific var when present.
_TEST_DB_URL = "sqlite+aiosqlite:///./test_radar.db"
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["DATABASE_APP_URL"] = _TEST_DB_URL
os.environ["DATABASE_MIGRATION_URL"] = _TEST_DB_URL
os.environ["DATABASE_WORKER_URL"] = _TEST_DB_URL
os.environ["AUTH_MODE"] = "development"
# Matches tests/jwt_helpers.py exactly — lets tests mint real, signature-
# verified tokens against the same contract a real Supabase project uses,
# while AUTH_MODE stays "development" so dev-login also keeps working for
# the rest of the suite.
os.environ["SUPABASE_URL"] = "https://local-test-project.supabase.co"
os.environ["SUPABASE_JWT_SECRET"] = "local-only-test-jwt-secret-do-not-use-in-production-1234567890"
os.environ["AI_ANALYSIS_ENABLED"] = "false"
os.environ["REDDIT_API_ENABLED"] = "false"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import AsyncSessionLocal, Base, engine, get_db
from app.main import app


@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    resp = await client.post("/api/auth/dev-login", json={"email": f"test-{uuid.uuid4()}@example.com"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
