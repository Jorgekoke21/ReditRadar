import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_account_id
from app.db import get_db
from app.models.topic import Topic, TopicExclusion, TopicKeyword
from app.schemas import TopicIn, TopicOut

router = APIRouter(prefix="/api/topics", tags=["topics"])


def _to_out(topic: Topic) -> TopicOut:
    return TopicOut(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        languages=topic.languages,
        priority=topic.priority.value if hasattr(topic.priority, "value") else topic.priority,
        is_active=topic.is_active,
        keywords=[k.phrase for k in topic.keywords],
        exclusions=[e.phrase for e in topic.exclusions],
        positive_examples=topic.positive_examples or [],
        negative_examples=topic.negative_examples or [],
    )


@router.get("", response_model=list[TopicOut])
async def list_topics(account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)):
    rows = (
        await session.execute(
            select(Topic)
            .options(selectinload(Topic.keywords), selectinload(Topic.exclusions))
            .where(Topic.account_id == account_id)
            .order_by(Topic.priority, Topic.name)
        )
    ).scalars().all()
    return [_to_out(t) for t in rows]


@router.post("", response_model=TopicOut, status_code=201)
async def create_topic(
    body: TopicIn, account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    topic = Topic(
        account_id=account_id,
        name=body.name,
        description=body.description,
        languages=body.languages,
        priority=body.priority,
        is_active=body.is_active,
        positive_examples=body.positive_examples,
        negative_examples=body.negative_examples,
    )
    topic.keywords = [TopicKeyword(phrase=p) for p in body.keywords]
    topic.exclusions = [TopicExclusion(phrase=p) for p in body.exclusions]
    session.add(topic)
    await session.commit()
    await session.refresh(topic, attribute_names=["keywords", "exclusions"])
    return _to_out(topic)


@router.patch("/{topic_id}", response_model=TopicOut)
async def update_topic(
    topic_id: uuid.UUID,
    body: TopicIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    topic = (
        await session.execute(
            select(Topic)
            .options(selectinload(Topic.keywords), selectinload(Topic.exclusions))
            .where(Topic.id == topic_id, Topic.account_id == account_id)
        )
    ).scalars().first()
    if not topic:
        raise HTTPException(404, "Topic not found")

    topic.name = body.name
    topic.description = body.description
    topic.languages = body.languages
    topic.priority = body.priority
    topic.is_active = body.is_active
    topic.positive_examples = body.positive_examples
    topic.negative_examples = body.negative_examples
    topic.keywords = [TopicKeyword(phrase=p) for p in body.keywords]
    topic.exclusions = [TopicExclusion(phrase=p) for p in body.exclusions]
    await session.commit()
    await session.refresh(topic, attribute_names=["keywords", "exclusions"])
    return _to_out(topic)


@router.delete("/{topic_id}", status_code=204)
async def delete_topic(
    topic_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    topic = (
        await session.execute(select(Topic).where(Topic.id == topic_id, Topic.account_id == account_id))
    ).scalars().first()
    if not topic:
        raise HTTPException(404, "Topic not found")
    await session.delete(topic)
    await session.commit()
