from datetime import datetime, timezone

from app.config import get_settings
from app.models.alerts import AlertDelivery
from app.services.jobs import run_send_daily_digest, run_send_urgent_alerts, run_send_weekly_digest


async def _make_topic(client, headers):
    await client.post(
        "/api/topics",
        json={
            "name": "Priorizar leads",
            "description": "test topic",
            "keywords": ["prioritize leads", "priorizar leads"],
            "exclusions": [],
            "priority": "high",
        },
        headers=headers,
    )


async def _make_high_score_conversation(client, headers, n: int):
    payload = {
        "subreddit": "agency",
        "title": f"Any tool to prioritize leads number {n}?",
        "body": "Looking for a tool to prioritize leads based on real signals",
        "num_comments": 0,
        "language": "en",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    r = await client.post("/api/conversations/manual", json=payload, headers=headers)
    assert r.status_code == 201
    return r.json()


async def test_urgent_alerts_respect_daily_cap_and_avoid_duplicates(client, auth_headers, db_session):
    await _make_topic(client, auth_headers)
    convos = [await _make_high_score_conversation(client, auth_headers, i) for i in range(3)]
    assert all(c["score_total"] >= 90 for c in convos), [c["score_total"] for c in convos]

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

    settings = get_settings()
    first_run = await run_send_urgent_alerts(db_session, settings)
    assert first_run["processed"] == 2  # capped even though 3 conversations qualify

    second_run = await run_send_urgent_alerts(db_session, settings)
    assert second_run["processed"] == 0  # cap already hit for today, no duplicate sends

    preview = await client.get("/api/alerts/preview", headers=auth_headers)
    urgent_deliveries = [d for d in preview.json() if d["kind"] == "urgent"]
    assert len(urgent_deliveries) == 2
    assert all(d["sent"] is False for d in urgent_deliveries)  # console provider: preview only, not "sent"


async def test_daily_digest_skips_when_no_recipient_configured(client, auth_headers, db_session):
    await _make_topic(client, auth_headers)
    await _make_high_score_conversation(client, auth_headers, 1)

    settings = get_settings()
    result = await run_send_daily_digest(db_session, settings)
    assert result["processed"] == 0  # AlertSettings.email_recipient defaults to ""


async def test_daily_digest_sent_once_recipient_configured(client, auth_headers, db_session):
    await _make_topic(client, auth_headers)
    await _make_high_score_conversation(client, auth_headers, 1)

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

    settings = get_settings()
    result = await run_send_daily_digest(db_session, settings)
    assert result["processed"] == 1


async def test_weekly_digest_persists_a_real_delivery_with_correct_stats(client, auth_headers, db_session):
    await _make_topic(client, auth_headers)
    convo = await _make_high_score_conversation(client, auth_headers, 1)

    await client.post(f"/api/conversations/{convo['id']}/actions?action_type=marked_responded", headers=auth_headers)
    await client.post(
        f"/api/conversations/{convo['id']}/outcome",
        json={"result": "conversation_started", "notes": "", "upvotes": None, "reply_count": None,
              "attributed_visits": None, "attributed_signups": None},
        headers=auth_headers,
    )

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

    settings = get_settings()
    result = await run_send_weekly_digest(db_session, settings)
    assert result["processed"] == 1
    assert result["status"] == "success"

    from sqlalchemy import select

    delivery = (
        await db_session.execute(select(AlertDelivery).where(AlertDelivery.kind == "weekly_digest"))
    ).scalars().first()
    assert delivery is not None
    assert delivery.sent is False  # console provider: never falsely claims delivery
    assert "Resumen semanal" in delivery.subject


async def test_weekly_digest_skips_when_disabled(client, auth_headers, db_session):
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
            "weekly_digest_enabled": False,
        },
        headers=auth_headers,
    )
    settings = get_settings()
    result = await run_send_weekly_digest(db_session, settings)
    assert result["processed"] == 0
