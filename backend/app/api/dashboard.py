import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account_id
from app.db import get_db
from app.models.conversation import Conversation
from app.models.enums import ConversationState
from app.models.jobs import ScheduledJobRun
from app.schemas import DashboardOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)

    async def count(*conditions):
        result = await session.execute(
            select(func.count()).select_from(Conversation).where(Conversation.account_id == account_id, *conditions)
        )
        return result.scalar_one()

    found_today = await count(Conversation.detected_at >= today_start)
    respond_now = await count(Conversation.recommended_action == "respond_now", Conversation.state.notin_([ConversationState.discarded]))
    review_today = await count(Conversation.recommended_action == "review_today", Conversation.state.notin_([ConversationState.discarded]))
    saved = await count(Conversation.state == ConversationState.saved)
    responded = await count(Conversation.state == ConversationState.responded)
    discarded = await count(Conversation.state == ConversationState.discarded)

    last_run = (
        await session.execute(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.job_name == "analyze_pending_conversations", ScheduledJobRun.status == "success")
            .order_by(ScheduledJobRun.finished_at.desc())
        )
    ).scalars().first()

    return DashboardOut(
        found_today=found_today, respond_now=respond_now, review_today=review_today, saved=saved,
        responded=responded, discarded=discarded, last_run_at=last_run.finished_at if last_run else None,
    )
