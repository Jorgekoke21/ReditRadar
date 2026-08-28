import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account_id
from app.db import get_db
from app.models.community import Community
from app.models.conversation import Conversation, ConversationOutcome
from app.models.enums import ConversationState, OutcomeResult
from app.models.topic import Topic
from app.schemas import ConversationListItemOut

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryOut(BaseModel):
    responded_conversations: list[ConversationListItemOut]
    best_communities: list[dict]
    top_topics: list[dict]
    average_score: float
    conversations_started: int
    attributed_signups: int
    attributed_visits: int


@router.get("", response_model=HistoryOut)
async def get_history(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    responded = (
        await session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id, Conversation.state == ConversationState.responded
            )
        )
    ).scalars().all()

    topic_ids = {c.topic_id for c in responded if c.topic_id}
    topics_by_id = {}
    if topic_ids:
        topic_rows = (await session.execute(select(Topic).where(Topic.id.in_(topic_ids)))).scalars().all()
        topics_by_id = {t.id: t.name for t in topic_rows}

    items = [
        ConversationListItemOut(
            id=c.id, subreddit=c.subreddit, title=c.display_title, summary=c.summary,
            problem_detected=c.problem_detected, language=c.language, state=c.state.value,
            score_total=c.score_total, recommended_action=c.recommended_action.value if c.recommended_action else None,
            promotion_risk=c.promotion_risk.value if c.promotion_risk else None, topic_id=c.topic_id,
            topic_name=topics_by_id.get(c.topic_id), published_at=c.published_at, detected_at=c.detected_at,
            num_comments=c.num_comments, url=c.url, source_mode=c.source_mode.value, is_demo=c.is_demo,
            raw_purged=c.raw_purged_at is not None,
        )
        for c in responded
    ]

    communities = (await session.execute(select(Community).where(Community.account_id == account_id))).scalars().all()
    best_communities = sorted(
        [{"name": c.name, "opportunities_found": c.opportunities_found, "responses_made": c.responses_made} for c in communities],
        key=lambda x: x["responses_made"], reverse=True,
    )[:5]

    all_analyzed = (
        await session.execute(select(Conversation).where(Conversation.account_id == account_id, Conversation.is_analyzed.is_(True)))
    ).scalars().all()
    topic_counts: dict[str, int] = {}
    for c in all_analyzed:
        if c.topic_id:
            name = topics_by_id.get(c.topic_id)
            if not name:
                t = (await session.execute(select(Topic).where(Topic.id == c.topic_id))).scalars().first()
                name = t.name if t else str(c.topic_id)
                topics_by_id[c.topic_id] = name
            topic_counts[name] = topic_counts.get(name, 0) + 1
    top_topics = sorted([{"name": k, "count": v} for k, v in topic_counts.items()], key=lambda x: x["count"], reverse=True)[:5]

    scored = [c.score_total for c in all_analyzed if c.score_total is not None]
    average_score = round(sum(scored) / len(scored), 1) if scored else 0.0

    outcomes = (
        await session.execute(
            select(ConversationOutcome).where(ConversationOutcome.conversation_id.in_([c.id for c in responded]))
        )
    ).scalars().all() if responded else []
    conversations_started = sum(1 for o in outcomes if o.result == OutcomeResult.conversation_started)
    attributed_signups = sum(o.attributed_signups or 0 for o in outcomes)
    attributed_visits = sum(o.attributed_visits or 0 for o in outcomes)

    return HistoryOut(
        responded_conversations=items, best_communities=best_communities, top_topics=top_topics,
        average_score=average_score, conversations_started=conversations_started,
        attributed_signups=attributed_signups, attributed_visits=attributed_visits,
    )
