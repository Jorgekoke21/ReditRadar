"""OAuth bridge: state validation, token refresh, and disconnect.

Every Reddit interaction here goes through a fake adapter or a monkeypatched
httpx transport - this suite makes zero real network calls, and
REDDIT_API_ENABLED stays false for the app under test (the OAuth settings are
injected per-test via a dependency override).
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models.reddit import RedditConnection, RedditOAuthState
from app.services import reddit_client
from app.services.crypto import decrypt_token, encrypt_token
from app.services.jobs import (
    _ensure_fresh_access_token,
    run_fetch_reddit_conversations,
    run_sync_deleted_reddit_content,
)

from tests.test_reddit_ingestion import FakeRedditClient, _post, _settings, _setup_account


def _enable_reddit(**updates):
    """Override the app's settings dependency so the OAuth routes are live.

    The real environment keeps REDDIT_API_ENABLED=false; only this override
    flips it, and only for the duration of one test.
    """
    settings = _settings(**updates)
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_settings, None)


class FakeTokenEndpoint:
    """Stands in for Reddit's /api/v1/access_token."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def install(self, monkeypatch):
        endpoint = self

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, data=None):
                endpoint.requests.append((url, data))
                status, payload = endpoint.responses.pop(0)
                if isinstance(payload, Exception):
                    raise payload
                return httpx.Response(status, json=payload, request=httpx.Request("POST", url))

        monkeypatch.setattr(reddit_client.httpx, "AsyncClient", _Client)
        return self


# --- state ---------------------------------------------------------------
async def test_authorize_url_contains_a_persisted_single_use_state(client, auth_headers, db_session):
    _enable_reddit()
    resp = await client.get("/api/reddit/connect", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = body["state"]

    assert len(state) >= 32
    assert f"state={state}" in body["authorize_url"]
    assert "duration=permanent" in body["authorize_url"]

    stored = (
        await db_session.execute(select(RedditOAuthState).where(RedditOAuthState.state == state))
    ).scalars().first()
    assert stored is not None
    assert stored.used_at is None
    assert stored.expires_at is not None


async def test_callback_rejects_unknown_state(client, auth_headers):
    _enable_reddit()
    resp = await client.post(
        "/api/reddit/callback", json={"code": "abc", "state": "never-issued"}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert "Invalid OAuth state" in resp.text


async def test_callback_rejects_expired_state(client, auth_headers, db_session, monkeypatch):
    _enable_reddit()
    connect = await client.get("/api/reddit/connect", headers=auth_headers)
    state = connect.json()["state"]

    record = (
        await db_session.execute(select(RedditOAuthState).where(RedditOAuthState.state == state))
    ).scalars().one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    endpoint = FakeTokenEndpoint([(200, {"access_token": "should-not-be-used"})]).install(monkeypatch)
    resp = await client.post("/api/reddit/callback", json={"code": "abc", "state": state}, headers=auth_headers)
    assert resp.status_code == 400
    assert "expired" in resp.text.lower()
    assert endpoint.requests == []  # never reached Reddit


async def test_callback_rejects_state_belonging_to_another_account(client, auth_headers, db_session, monkeypatch):
    _enable_reddit()
    connect = await client.get("/api/reddit/connect", headers=auth_headers)
    state = connect.json()["state"]

    # A second, unrelated account tries to redeem the first account's state.
    other = await client.post("/api/auth/dev-login", json={"email": f"other-{uuid.uuid4()}@example.com"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    endpoint = FakeTokenEndpoint([(200, {"access_token": "should-not-be-used"})]).install(monkeypatch)
    resp = await client.post("/api/reddit/callback", json={"code": "abc", "state": state}, headers=other_headers)
    assert resp.status_code == 400
    assert endpoint.requests == []


async def test_callback_state_is_single_use(client, auth_headers, monkeypatch):
    _enable_reddit()
    state = (await client.get("/api/reddit/connect", headers=auth_headers)).json()["state"]
    FakeTokenEndpoint(
        [
            (200, {"access_token": "tok-1", "refresh_token": "ref-1", "expires_in": 3600, "scope": "identity read"}),
            (200, {"access_token": "tok-2", "refresh_token": "ref-2", "expires_in": 3600}),
        ]
    ).install(monkeypatch)

    first = await client.post("/api/reddit/callback", json={"code": "c1", "state": state}, headers=auth_headers)
    assert first.status_code == 200, first.text

    second = await client.post("/api/reddit/callback", json={"code": "c2", "state": state}, headers=auth_headers)
    assert second.status_code == 400
    assert "already been used" in second.text


async def test_valid_callback_persists_an_active_encrypted_connection(client, auth_headers, db_session, monkeypatch):
    settings = _enable_reddit()
    state = (await client.get("/api/reddit/connect", headers=auth_headers)).json()["state"]
    FakeTokenEndpoint(
        [
            (
                200,
                {
                    "access_token": "plain-access",
                    "refresh_token": "plain-refresh",
                    "expires_in": 3600,
                    "scope": "identity read",
                },
            )
        ]
    ).install(monkeypatch)

    resp = await client.post("/api/reddit/callback", json={"code": "the-code", "state": state}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["connected"] is True

    connection = (await db_session.execute(select(RedditConnection))).scalars().one()
    assert connection.is_active is True
    # Stored ciphertext must not be the plaintext, and must decrypt back to it.
    assert connection.access_token_encrypted not in ("", "plain-access")
    assert connection.refresh_token_encrypted not in ("", "plain-refresh")
    assert decrypt_token(settings, connection.access_token_encrypted) == "plain-access"
    assert decrypt_token(settings, connection.refresh_token_encrypted) == "plain-refresh"
    assert connection.token_expires_at is not None


async def test_no_endpoint_ever_returns_a_token(client, auth_headers, monkeypatch):
    _enable_reddit()
    state = (await client.get("/api/reddit/connect", headers=auth_headers)).json()["state"]
    FakeTokenEndpoint(
        [(200, {"access_token": "super-secret-access", "refresh_token": "super-secret-refresh", "expires_in": 3600})]
    ).install(monkeypatch)

    callback = await client.post("/api/reddit/callback", json={"code": "c", "state": state}, headers=auth_headers)
    integrations = await client.get("/api/settings/integrations", headers=auth_headers)

    for resp in (callback, integrations):
        assert "super-secret-access" not in resp.text
        assert "super-secret-refresh" not in resp.text
        assert "access_token" not in resp.text


# --- refresh -------------------------------------------------------------
def _connection(account_id, settings, *, expires_in_seconds, access="current-access", refresh="current-refresh"):
    return RedditConnection(
        account_id=account_id,
        reddit_username="fake-user",
        access_token_encrypted=encrypt_token(settings, access),
        refresh_token_encrypted=encrypt_token(settings, refresh),
        token_expires_at=(
            None
            if expires_in_seconds is None
            else datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        ),
        scopes="identity,read",
        is_active=True,
    )


class RefreshingAdapter(FakeRedditClient):
    def __init__(self, payload=None, error=None, **kwargs):
        super().__init__(**kwargs)
        self.payload = payload
        self.error = error
        self.refresh_calls = []

    async def refresh_access_token(self, settings, refresh_token):
        self.refresh_calls.append(refresh_token)
        if self.error:
            raise self.error
        return self.payload


async def test_valid_token_is_not_refreshed(db_session):
    settings = _settings()
    adapter = RefreshingAdapter(payload={"access_token": "new"})
    connection = _connection(uuid.uuid4(), settings, expires_in_seconds=3600)

    token = await _ensure_fresh_access_token(db_session, settings, connection, adapter)

    assert token == "current-access"
    assert adapter.refresh_calls == []


async def test_token_close_to_expiry_is_refreshed(db_session):
    settings = _settings()
    adapter = RefreshingAdapter(payload={"access_token": "renewed", "expires_in": 3600})
    connection = _connection(uuid.uuid4(), settings, expires_in_seconds=120)
    db_session.add(connection)
    await db_session.commit()

    token = await _ensure_fresh_access_token(db_session, settings, connection, adapter)

    assert token == "renewed"
    assert adapter.refresh_calls == ["current-refresh"]


async def test_expired_token_is_refreshed_and_persisted(db_session):
    settings = _settings()
    adapter = RefreshingAdapter(
        payload={"access_token": "renewed", "refresh_token": "rotated", "expires_in": 3600}
    )
    connection = _connection(uuid.uuid4(), settings, expires_in_seconds=-60)
    db_session.add(connection)
    await db_session.commit()

    token = await _ensure_fresh_access_token(db_session, settings, connection, adapter)

    assert token == "renewed"
    assert decrypt_token(settings, connection.access_token_encrypted) == "renewed"
    # A rotated refresh token must replace the old one.
    assert decrypt_token(settings, connection.refresh_token_encrypted) == "rotated"
    assert connection.token_expires_at > datetime.now(timezone.utc)


async def test_refresh_without_rotation_keeps_the_existing_refresh_token(db_session):
    """Reddit usually omits refresh_token on refresh; overwriting it with an
    empty value would leave the connection unable to ever refresh again."""
    settings = _settings()
    adapter = RefreshingAdapter(payload={"access_token": "renewed", "expires_in": 3600})
    connection = _connection(uuid.uuid4(), settings, expires_in_seconds=-60)
    db_session.add(connection)
    await db_session.commit()

    await _ensure_fresh_access_token(db_session, settings, connection, adapter)

    assert decrypt_token(settings, connection.refresh_token_encrypted) == "current-refresh"


async def test_failed_refresh_does_not_kill_the_fetch_job(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    connection = (await db_session.execute(select(RedditConnection))).scalars().one()
    connection.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    adapter = RefreshingAdapter(
        error=reddit_client.RedditTokenRefreshError("Reddit token refresh failed: HTTP 400"),
        pages={"agency": [_post()]},
    )
    result = await run_fetch_reddit_conversations(db_session, settings, adapter=adapter)

    # Recorded as a failed run, but the job returned normally - the worker and
    # scheduler stay alive and the next tick retries.
    assert result["skipped"] is False
    assert result["status"] == "failed"
    assert result["errors"] == 1
    assert result["metrics"]["token_refresh_failures"] == 1
    assert adapter.calls == []  # never attempted a listing with a dead token
    assert "current-refresh" not in (result["error_message"] or "")


async def test_fetch_continues_after_a_successful_refresh(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    connection = (await db_session.execute(select(RedditConnection))).scalars().one()
    connection.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    adapter = RefreshingAdapter(
        payload={"access_token": "renewed-access", "expires_in": 3600},
        pages={"agency": [_post()]},
    )
    result = await run_fetch_reddit_conversations(db_session, settings, adapter=adapter)

    assert result["status"] == "success"
    assert adapter.refresh_calls == ["fake-refresh-token"]
    assert result["metrics"]["posts_retrieved"] == 1
    assert result["metrics"]["new_conversations"] == 1
    assert decrypt_token(settings, connection.access_token_encrypted) == "renewed-access"


async def test_deleted_sync_continues_after_a_successful_refresh(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)

    seeded = RefreshingAdapter(payload={"access_token": "x"}, pages={"agency": [_post(post_id="del1")]})
    await run_fetch_reddit_conversations(db_session, settings, adapter=seeded)

    connection = (await db_session.execute(select(RedditConnection))).scalars().one()
    connection.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    adapter = RefreshingAdapter(
        payload={"access_token": "renewed-access", "expires_in": 3600},
        by_id={"del1": _post(post_id="del1", removed=True)},
    )
    result = await run_sync_deleted_reddit_content(db_session, settings, adapter=adapter)

    assert result["status"] == "success"
    assert adapter.refresh_calls == ["fake-refresh-token"]
    assert result["metrics"]["checked"] >= 1
    assert result["metrics"]["token_refresh_failures"] == 0


# --- disconnect ----------------------------------------------------------
async def test_disconnect_destroys_credentials_but_keeps_conversations(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    adapter = RefreshingAdapter(payload={"access_token": "x"}, pages={"agency": [_post()]})
    await run_fetch_reddit_conversations(db_session, settings, adapter=adapter)

    before = (await client.get("/api/conversations", headers=auth_headers)).json()
    assert len(before) >= 1

    resp = await client.delete("/api/reddit/connection", headers=auth_headers)
    assert resp.status_code == 204

    connection = (await db_session.execute(select(RedditConnection))).scalars().one()
    await db_session.refresh(connection)
    assert connection.is_active is False
    assert connection.access_token_encrypted == ""
    assert connection.refresh_token_encrypted == ""
    assert connection.token_expires_at is None

    after = (await client.get("/api/conversations", headers=auth_headers)).json()
    assert len(after) == len(before)


async def test_connect_and_callback_are_refused_while_the_flag_is_off(client, auth_headers):
    """No override here: the app's real REDDIT_API_ENABLED=false must gate both."""
    assert (await client.get("/api/reddit/connect", headers=auth_headers)).status_code == 403
    assert (
        await client.post("/api/reddit/callback", json={"code": "c", "state": "s"}, headers=auth_headers)
    ).status_code == 403
