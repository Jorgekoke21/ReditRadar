import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_account_id
from app.db import get_db
from app.models.reddit import RedditConnection
from app.services import reddit_client
from app.services.crypto import encrypt_token

router = APIRouter(prefix="/api/reddit", tags=["reddit"])


@router.get("/connect")
async def connect(settings: Settings = Depends(get_settings), _account=Depends(get_current_account_id)):
    if not settings.reddit_api_enabled:
        raise HTTPException(
            403,
            "REDDIT_API_ENABLED=false — read-only Reddit access is not active. "
            "See docs/reddit-access-request.md for what's required to enable it.",
        )
    state = secrets.token_urlsafe(16)
    return {"authorize_url": reddit_client.build_authorize_url(settings, state), "state": state}


@router.get("/callback")
async def callback(
    code: str,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.reddit_api_enabled:
        raise HTTPException(403, "REDDIT_API_ENABLED=false")
    token_data = await reddit_client.exchange_code_for_token(settings, code)

    connection = (
        await session.execute(select(RedditConnection).where(RedditConnection.account_id == account_id))
    ).scalars().first()
    if not connection:
        connection = RedditConnection(account_id=account_id)
        session.add(connection)

    connection.access_token_encrypted = encrypt_token(settings, token_data["access_token"])
    connection.refresh_token_encrypted = encrypt_token(settings, token_data.get("refresh_token", ""))
    connection.scopes = token_data.get("scope", "")
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
    connection.is_active = True
    await session.commit()
    return {"connected": True}


@router.delete("/connection", status_code=204)
async def disconnect(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    connection = (
        await session.execute(select(RedditConnection).where(RedditConnection.account_id == account_id))
    ).scalars().first()
    if connection:
        await session.delete(connection)
        await session.commit()
