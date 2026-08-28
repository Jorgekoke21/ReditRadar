import asyncio
from datetime import datetime, timedelta, timezone
import uuid

import httpx
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.config import get_settings
from app.models.community import Community
from app.models.conversation import Conversation
from app.models.enums import SourceMode
from app.models.jobs import ScheduledJobRun
from app.models.reddit import RedditConnection
from app.services.crypto import encrypt_token
from app.services import reddit_client
from app.services.jobs import (
    JOB_REGISTRY,
    run_fetch_reddit_conversations,
    run_send_urgent_alerts,
    run_sync_deleted_reddit_content,
)
from app.worker import build_scheduler


class FakeRedditClient:
    def __init__(self, pages=None, by_id=None, page_sequences=None, fail_subreddits=None):
        self.pages = pages or {}
        self.page_sequences = page_sequences or {}
        self.fail_subreddits = set(fail_subreddits or [])
        self.by_id = by_id or {}
        self.calls = []
        self.delete_calls = []

    async def fetch_new_posts_page(self, settings, access_token, subreddit, *, limit, after=None):
        self.calls.append((subreddit, after, limit))
        if subreddit in self.fail_subreddits:
            raise RuntimeError(f"fake failure for {subreddit}")
        if subreddit in self.page_sequences:
            sequence = self.page_sequences[subreddit]
            index = int(after) if after else 0
            posts = sequence[index] if index < len(sequence) else []
            next_after = str(index + 1) if index + 1 < len(sequence) else None
        else:
            posts = self.pages.get(subreddit, [])
            next_after = None
        return reddit_client.RedditListingPage(
            posts=posts,
            after=next_after,
            rate_limit=reddit_client.RateLimitInfo(remaining=99, used=1, reset_seconds=599),
        )

    async def fetch_posts_by_ids(self, settings, access_token, post_ids):
        self.delete_calls.append(post_ids)
        return self.by_id, reddit_client.RateLimitInfo(remaining=98, used=2, reset_seconds=598)


def _settings(**updates):
    values = {
        "reddit_api_enabled": True,
        "reddit_client_id": "fake-client-id",
        "reddit_client_secret": "fake-client-secret",
        "reddit_token_encryption_key": "test-only-key",
        "reddit_fetch_limit": 50,
        "reddit_default_max_age_hours": 72,
    }
    values.update(updates)
    return get_settings().model_copy(update=values)


def _post(post_id="abc123", title="How can I prioritize leads for my agency?", body=None, hours=1, removed=False, subreddit="agency"):
    return reddit_client.RedditPost(
        id=post_id,
        subreddit=subreddit,
        title=title,
        selftext=body or "I need a practical tool to prioritize leads based on real signals for a small agency.",
        author="" if removed else "author",
        url=f"https://reddit.com/r/{subreddit}/comments/{post_id}/",
        permalink=f"/r/{subreddit}/comments/{post_id}/",
        created_utc=(datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp(),
        num_comments=4,
        score=12,
        removed=removed,
    )


async def _setup_account(client, db_session, auth_headers):
    me = await client.get("/api/auth/me", headers=auth_headers)
    account_id = uuid.UUID(me.json()["account_id"])
    await client.post(
        "/api/topics",
        json={
            "name": "Prioritize leads",
            "description": "lead prioritization",
            "keywords": ["prioritize leads"],
            "exclusions": [],
            "priority": "high",
        },
        headers=auth_headers,
    )
    await client.post("/api/communities", json={"name": "agency", "priority": "high"}, headers=auth_headers)
    settings = _settings()
    db_session.add(
        RedditConnection(
            account_id=account_id,
            reddit_username="fake-user",
            access_token_encrypted=encrypt_token(settings, "fake-access-token"),
            refresh_token_encrypted=encrypt_token(settings, "fake-refresh-token"),
            scopes="identity,read",
            is_active=True,
        )
    )
    await db_session.commit()
    return account_id, settings


async def test_reddit_disabled_makes_zero_adapter_calls(db_session):
    fake = FakeRedditClient(pages={"agency": [_post()]})
    result = await run_fetch_reddit_conversations(db_session, get_settings(), adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["external_calls"] == 0
    assert fake.calls == []


async def test_reddit_enabled_without_oauth_credentials_fails_safely(client, auth_headers, db_session):
    fake = FakeRedditClient(pages={"agency": [_post()]})
    settings = _settings(reddit_client_id="", reddit_client_secret="")
    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "failed"
    assert "REDDIT_CLIENT_ID" in result["error_message"]
    assert fake.calls == []


async def test_fetch_uses_active_communities_pipeline_and_persistent_watermark(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    same_post_twice = [_post(), _post()]
    fake = FakeRedditClient(pages={"agency": same_post_twice})
    first = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert first["status"] == "success"
    assert first["metrics"]["communities_reviewed"] == 1
    assert first["metrics"]["new_conversations"] == 1
    assert first["metrics"]["duplicates"] == 1
    assert first["metrics"]["analyzed"] == 1
    assert first["metrics"]["recommended"] == 1

    rows = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert len(rows) == 1

    community = (
        await db_session.execute(select(Community).where(Community.account_id == account_id))
    ).scalars().first()
    assert community.reddit_watermark_id == "abc123"
    assert community.reddit_rate_remaining == 99
    assert rows[0].community_id == community.id

    second = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert second["metrics"]["new_conversations"] == 0
    assert second["metrics"]["duplicates"] == 2
    assert len(fake.calls) == 2

    row = rows[0]
    row.raw_title = None
    row.raw_body = None
    row.raw_author = None
    row.raw_purged_at = datetime.now(timezone.utc)
    await db_session.commit()
    third = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert third["metrics"]["new_conversations"] == 0
    assert third["metrics"]["duplicates"] == 2
    rows_after_purge = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert len(rows_after_purge) == 1


async def test_one_community_failure_does_not_stop_the_other(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    await client.post("/api/communities", json={"name": "localseo", "priority": "medium"}, headers=auth_headers)
    fake = FakeRedditClient(
        pages={"localseo": [_post(post_id="healthy1", subreddit="localseo")]},
        fail_subreddits={"agency"},
    )

    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "failed"
    assert result["errors"] == 1
    assert result["metrics"]["errors_by_community"] == 1
    assert result["metrics"]["new_conversations"] == 1
    assert [call[0] for call in fake.calls] == ["agency", "localseo"]

    row = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.reddit_post_id == "healthy1",
            )
        )
    ).scalars().one()
    assert row.subreddit == "localseo"


async def test_fetch_reviews_multiple_communities_and_paginates(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    await client.post("/api/communities", json={"name": "localseo", "priority": "medium"}, headers=auth_headers)
    settings = settings.model_copy(update={"reddit_fetch_limit": 1, "reddit_max_pages_per_community": 3})
    fake = FakeRedditClient(
        page_sequences={
            "agency": [[_post(post_id="page1", hours=1)], [_post(post_id="page2", hours=2)]],
            "localseo": [[_post(post_id="other1", hours=1, subreddit="localseo")]],
        }
    )

    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["communities_reviewed"] == 2
    assert result["metrics"]["posts_retrieved"] == 3
    assert result["metrics"]["new_conversations"] == 3
    assert [call[1] for call in fake.calls] == [None, "1", None]

    rows = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert {row.reddit_post_id for row in rows} == {"page1", "page2", "other1"}


async def test_distinct_reddit_ids_with_same_title_and_subreddit_are_not_merged(client, auth_headers, db_session):
    """Two genuinely different Reddit posts can legitimately share a subreddit,
    the default fixture title, and the same calendar day — that must not
    collide into one conversation. The subreddit+title+day dedupe_hash exists
    to catch manual re-entry of a post with no id/url yet (app/services/dedupe.py);
    when a real, distinct reddit_post_id is known for each post, that is the
    stronger signal and both must be kept (regression for the bug where
    `uq_conversation_account_dedupe_hash` silently dropped the second post)."""
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    fake = FakeRedditClient(
        pages={"agency": [_post(post_id="dup-title-a", hours=1), _post(post_id="dup-title-b", hours=2)]}
    )

    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["posts_retrieved"] == 2
    assert result["metrics"]["new_conversations"] == 2
    assert result["metrics"]["duplicates"] == 0

    rows = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert {row.reddit_post_id for row in rows} == {"dup-title-a", "dup-title-b"}


async def test_same_post_repeated_across_pages_dedupes_by_reddit_id(client, auth_headers, db_session):
    """A post that shows up again on a later page (e.g. Reddit's listing
    shifting between calls) must still be recognized as the same conversation
    via reddit_post_id, not counted as a second new conversation."""
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    settings = settings.model_copy(update={"reddit_fetch_limit": 1, "reddit_max_pages_per_community": 3})
    repeated = _post(post_id="shifted", hours=1)
    fake = FakeRedditClient(page_sequences={"agency": [[repeated], [repeated]]})

    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["posts_retrieved"] == 2
    assert result["metrics"]["new_conversations"] == 1
    assert result["metrics"]["duplicates"] == 1

    rows = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].reddit_post_id == "shifted"


async def test_fetch_marks_removed_and_old_posts_discarded_before_analyzer(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    fake = FakeRedditClient(
        pages={
            "agency": [
                _post(post_id="removed1", removed=True),
                _post(post_id="old1", hours=100),
            ]
        }
    )
    result = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["new_conversations"] == 2
    assert result["metrics"]["discarded_before_analysis"] == 2

    rows = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.source_mode == SourceMode.reddit_api,
            )
        )
    ).scalars().all()
    assert {row.reddit_post_id for row in rows} == {"removed1", "old1"}
    assert all(row.state.value == "discarded" for row in rows)
    assert next(row for row in rows if row.reddit_post_id == "removed1").is_removed_upstream is True


async def test_fetch_feeds_urgent_alert_pipeline_without_external_email(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    await client.patch(
        "/api/alerts/settings",
        json={
            "email_recipient": "owner@example.com",
            "timezone": "Europe/Madrid",
            "daily_digest_enabled": True,
            "daily_digest_time": "09:00",
            "min_score_threshold": 60,
            "urgent_alerts_enabled": True,
            "urgent_score_threshold": 90,
            "max_urgent_per_day": 2,
            "weekly_digest_enabled": True,
        },
        headers=auth_headers,
    )
    fake = FakeRedditClient(pages={"agency": [_post(title="Any tool to prioritize leads for my agency?")]})
    fetched = await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    assert fetched["metrics"]["new_conversations"] == 1
    alerted = await run_send_urgent_alerts(db_session, settings)
    assert alerted["status"] == "success"
    assert alerted["processed"] == 1
    assert account_id is not None


async def test_sync_deleted_clears_raw_content_and_keeps_operational_data(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    post = _post(post_id="deleted1")
    fake = FakeRedditClient(pages={"agency": [post]}, by_id={"deleted1": _post(post_id="deleted1", removed=True)})
    await run_fetch_reddit_conversations(db_session, settings, adapter=fake)
    result = await run_sync_deleted_reddit_content(db_session, settings, adapter=fake)
    assert result["status"] == "success"
    assert result["metrics"]["deleted"] == 1

    row = (
        await db_session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.reddit_post_id == "deleted1",
            )
        )
    ).scalars().one()
    assert row.raw_title is None
    assert row.raw_body is None
    assert row.is_removed_upstream is True
    assert row.summary == "Contenido eliminado en Reddit"


async def test_backoff_retries_429_then_succeeds(monkeypatch):
    request = httpx.Request("GET", "https://oauth.reddit.com/r/agency/new")
    responses = [
        httpx.Response(429, headers={"retry-after": "0", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "3"}, request=request),
        httpx.Response(200, json={"data": {"children": []}}, request=request),
    ]
    class FakeHTTPClient:
        async def get(self, url, params):
            return responses.pop(0)
    sleeps = []
    async def no_sleep(value):
        sleeps.append(value)
    monkeypatch.setattr(reddit_client.asyncio, "sleep", no_sleep)
    response = await reddit_client._get_with_backoff(FakeHTTPClient(), "https://oauth.reddit.com/r/agency/new", {}, max_retries=1)
    assert response.status_code == 200
    assert len(sleeps) == 1
    assert sleeps[0] < 1


async def test_backoff_retries_500_and_timeout_then_succeeds(monkeypatch):
    request = httpx.Request("GET", "https://oauth.reddit.com/r/agency/new")
    responses = [
        httpx.Response(500, request=request),
        httpx.ReadTimeout("timeout", request=request),
        httpx.Response(200, json={"data": {"children": []}}, request=request),
    ]

    class FakeHTTPClient:
        async def get(self, url, params):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

    sleeps = []

    async def no_sleep(value):
        sleeps.append(value)

    monkeypatch.setattr(reddit_client.asyncio, "sleep", no_sleep)
    response = await reddit_client._get_with_backoff(
        FakeHTTPClient(), "https://oauth.reddit.com/r/agency/new", {}, max_retries=2
    )
    assert response.status_code == 200
    assert len(sleeps) == 2


async def test_scheduler_runs_job_automatically_and_survives_failed_callback(db_session):
    settings = _settings()
    calls = []
    done = asyncio.Event()
    from app.db import AsyncSessionLocal

    async def runner(job_name, run_settings):
        async with AsyncSessionLocal() as session:
            result = await JOB_REGISTRY[job_name](session, run_settings.model_copy(update={"reddit_client_id": "", "reddit_client_secret": ""}))
        calls.append(result)
        if len(calls) >= 2:
            done.set()
        return result

    scheduler = build_scheduler(
        settings,
        runner=runner,
        trigger_overrides={"fetch_reddit_conversations": IntervalTrigger(seconds=0.05)},
    )
    scheduler.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=2)
    finally:
        scheduler.shutdown(wait=False)
    assert len(calls) >= 2
    assert all(result["status"] == "failed" for result in calls[:2])
    rows = (
        await db_session.execute(
            select(ScheduledJobRun).where(ScheduledJobRun.job_name == "fetch_reddit_conversations")
        )
    ).scalars().all()
    assert len(rows) >= 2
