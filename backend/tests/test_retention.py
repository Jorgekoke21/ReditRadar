import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.models.conversation import Conversation
from app.services.jobs import run_purge_expired_reddit_content


async def _create_manual(client, headers, title="Retention test conversation about crm leads"):
    await client.post(
        "/api/topics",
        json={
            "name": "CRM barato",
            "description": "test topic",
            "keywords": ["crm barato", "priorizar leads"],
            "exclusions": [],
            "priority": "high",
        },
        headers=headers,
    )
    payload = {
        "subreddit": "agency",
        "title": title,
        "body": "buscamos un crm barato para priorizar leads",
        "num_comments": 0,
        "language": "es",
    }
    r = await client.post("/api/conversations/manual", json=payload, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _as_aware(dt: datetime) -> datetime:
    # SQLite (used only in this portable test suite) doesn't persist tzinfo;
    # Postgres does. Normalize so the assertion works against either backend.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def test_manual_conversation_gets_48h_expiry(client, auth_headers, db_session):
    convo_id = await _create_manual(client, auth_headers)
    row = (await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(convo_id)))).scalars().first()
    assert row.expires_at is not None
    delta = _as_aware(row.expires_at) - datetime.now(timezone.utc)
    assert timedelta(hours=47) < delta <= timedelta(hours=48, minutes=5)


async def test_purge_job_clears_raw_content_but_keeps_operational_fields(client, auth_headers, db_session):
    convo_id = await _create_manual(client, auth_headers)

    row = (await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(convo_id)))).scalars().first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    settings = get_settings()
    result = await run_purge_expired_reddit_content(db_session, settings)
    assert result["status"] == "success"
    assert result["processed"] == 1

    await db_session.refresh(row)
    assert row.raw_title is None
    assert row.raw_body is None
    assert row.raw_purged_at is not None
    # operational data must survive the purge
    assert row.score_total is not None
    assert row.summary != ""


async def test_purge_job_is_idempotent_noop_on_second_run(client, auth_headers, db_session):
    convo_id = await _create_manual(client, auth_headers)
    row = (await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(convo_id)))).scalars().first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    settings = get_settings()
    first = await run_purge_expired_reddit_content(db_session, settings)
    second = await run_purge_expired_reddit_content(db_session, settings)
    assert first["processed"] == 1
    assert second["processed"] == 0  # already purged, nothing left to do


async def test_manual_purge_endpoint_deletes_raw_content_immediately(client, auth_headers):
    convo_id = await _create_manual(client, auth_headers)
    r = await client.delete(f"/api/conversations/{convo_id}/raw-content", headers=auth_headers)
    assert r.status_code == 204

    detail = await client.get(f"/api/conversations/{convo_id}", headers=auth_headers)
    body = detail.json()
    assert body["raw_title"] is None
    assert body["raw_purged"] is True
