from datetime import datetime, timezone

from app.config import get_settings
from app.models.jobs import ScheduledJobRun
from app.services.jobs import run_fetch_reddit_conversations, run_sync_deleted_reddit_content


async def test_job_lock_skips_when_already_running(db_session):
    db_session.add(ScheduledJobRun(job_name="recalculate_scores", status="running", started_at=datetime.now(timezone.utc)))
    await db_session.commit()

    from app.services.jobs import run_recalculate_scores

    settings = get_settings()
    result = await run_recalculate_scores(db_session, settings)
    assert result["skipped"] is True
    assert result["reason"] == "already_running"


async def test_fetch_reddit_conversations_is_a_noop_when_disabled(db_session):
    settings = get_settings()
    assert settings.reddit_api_enabled is False
    result = await run_fetch_reddit_conversations(db_session, settings)
    assert result["status"] == "success"
    assert result["processed"] == 0


async def test_sync_deleted_reddit_content_is_a_noop_when_disabled(db_session):
    settings = get_settings()
    result = await run_sync_deleted_reddit_content(db_session, settings)
    assert result["status"] == "success"
    assert result["processed"] == 0


async def test_reddit_connect_endpoint_blocked_when_disabled(client, auth_headers):
    resp = await client.get("/api/reddit/connect", headers=auth_headers)
    assert resp.status_code == 403


async def test_jobs_and_diagnostics_require_admin_allowlist(client, auth_headers):
    from app.config import get_settings
    from app.main import app

    original_override = app.dependency_overrides.get(get_settings)
    admin_settings = get_settings().model_copy(update={"job_admin_emails": "admin@example.com"})
    app.dependency_overrides[get_settings] = lambda: admin_settings
    try:
        forbidden = await client.get("/api/jobs", headers=auth_headers)
        assert forbidden.status_code == 403

        login = await client.post("/api/auth/dev-login", json={"email": "admin@example.com"})
        assert login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        allowed = await client.get("/api/jobs/diagnostics", headers=admin_headers)
        assert allowed.status_code == 200
        assert len(allowed.json()["registered_jobs"]) == 8

        run = await client.post("/api/jobs/fetch_reddit_conversations/run", headers=admin_headers)
        assert run.status_code == 200
    finally:
        if original_override is None:
            app.dependency_overrides.pop(get_settings, None)
        else:
            app.dependency_overrides[get_settings] = original_override
