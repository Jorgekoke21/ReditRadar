import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account_id
from app.db import get_db
from app.models.community import Community
from app.schemas import CommunityIn, CommunityOut

router = APIRouter(prefix="/api/communities", tags=["communities"])


@router.get("", response_model=list[CommunityOut])
async def list_communities(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    rows = (
        await session.execute(
            select(Community).where(Community.account_id == account_id).order_by(Community.priority, Community.name)
        )
    ).scalars().all()
    return rows


@router.post("", response_model=CommunityOut, status_code=201)
async def create_community(
    body: CommunityIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    # CommunityIn canonicalizes the name, so "SaaS", "r/SaaS" and "/r/saas"
    # all collide here rather than creating near-duplicate watch entries.
    # Checked explicitly so the caller gets a 409 instead of the raw
    # IntegrityError from uq_community_account_name.
    existing = (
        await session.execute(
            select(Community).where(
                Community.account_id == account_id,
                func.lower(Community.name) == body.name.lower(),
            )
        )
    ).scalars().first()
    if existing:
        raise HTTPException(409, f"Community 'r/{existing.name}' is already on the watch list")

    community = Community(account_id=account_id, **body.model_dump())
    session.add(community)
    await session.commit()
    await session.refresh(community)
    return community


@router.patch("/{community_id}", response_model=CommunityOut)
async def update_community(
    community_id: uuid.UUID,
    body: CommunityIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    community = (
        await session.execute(
            select(Community).where(Community.id == community_id, Community.account_id == account_id)
        )
    ).scalars().first()
    if not community:
        raise HTTPException(404, "Community not found")
    for key, value in body.model_dump().items():
        setattr(community, key, value)
    await session.commit()
    await session.refresh(community)
    return community


@router.delete("/{community_id}", status_code=204)
async def delete_community(
    community_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    community = (
        await session.execute(
            select(Community).where(Community.id == community_id, Community.account_id == account_id)
        )
    ).scalars().first()
    if not community:
        raise HTTPException(404, "Community not found")
    await session.delete(community)
    await session.commit()
