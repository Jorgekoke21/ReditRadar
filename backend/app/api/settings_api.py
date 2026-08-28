import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_account_id
from app.db import get_db
from app.models.reddit import RedditConnection
from app.models.jobs import ScheduledJobRun
from app.schemas import IntegrationsStatusOut
from app.services.jobs import JOB_FREQUENCIES

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/integrations", response_model=IntegrationsStatusOut)
async def integrations_status(
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    connection = (
        await session.execute(
            select(RedditConnection).where(RedditConnection.account_id == account_id, RedditConnection.is_active.is_(True))
        )
    ).scalars().first()

    latest_reddit_run = (
        await session.execute(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.job_name == "fetch_reddit_conversations")
            .order_by(ScheduledJobRun.finished_at.desc())
        )
    ).scalars().first()
    reddit_metrics = (latest_reddit_run.metrics or {}) if latest_reddit_run else {}
    return IntegrationsStatusOut(
        reddit_api_enabled=settings.reddit_api_enabled,
        reddit_connected=connection is not None,
        reddit_credentials_configured=bool(
            settings.reddit_client_id and settings.reddit_client_secret and settings.reddit_encryption_key_is_safe
        ),
        reddit_last_run_at=latest_reddit_run.finished_at if latest_reddit_run else None,
        reddit_last_success=bool(latest_reddit_run and latest_reddit_run.status == "success"),
        reddit_posts_retrieved=int(reddit_metrics.get("posts_retrieved", 0)),
        reddit_new_conversations=int(reddit_metrics.get("new_conversations", 0)),
        reddit_duplicates=int(reddit_metrics.get("duplicates", 0)),
        reddit_communities_reviewed=int(reddit_metrics.get("communities_reviewed", 0)),
        reddit_errors=int(reddit_metrics.get("errors_by_community", 0)),
        reddit_rate_remaining=reddit_metrics.get("rate_remaining"),
        reddit_rate_used=reddit_metrics.get("rate_used"),
        reddit_rate_reset_seconds=reddit_metrics.get("rate_reset_seconds"),
        reddit_next_run_frequency=JOB_FREQUENCIES["fetch_reddit_conversations"],
        ai_analysis_enabled=settings.ai_analysis_enabled and bool(settings.ai_api_key),
        ai_provider=settings.ai_provider,
        email_provider=settings.email_provider,
        email_configured=settings.email_provider in ("smtp", "resend")
        and bool(settings.smtp_host or settings.resend_api_key),
        auth_mode=settings.auth_mode,
        dev_auth_bypass=settings.is_development_auth_allowed,
        supabase_configured=bool(settings.supabase_url and settings.supabase_jwt_secret),
        raw_content_retention_hours=settings.raw_content_retention_hours,
    )
