"""Reddit OAuth bridge.

The `state` parameter makes a round trip through the user's browser and comes
back from Reddit, so nothing it carries can be trusted. Rather than encoding
the account id into it, `/connect` stores an opaque random value bound
server-side to the calling account, and `/callback` — which the *frontend*
calls with the user's own session — identifies the account from that session
and merely checks the returned state matches an unexpired, unconsumed row
belonging to it. That makes a forged or replayed state useless.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_account_id
from app.db import get_db
from app.models.reddit import RedditConnection, RedditOAuthState
from app.schemas import RedditCallbackIn, RedditConnectOut, RedditConnectionOut
from app.services import reddit_client
from app.services.crypto import encrypt_token

router = APIRouter(prefix="/api/reddit", tags=["reddit"])

STATE_TTL_MINUTES = 10


def _disabled() -> HTTPException:
    return HTTPException(
        403,
        "REDDIT_API_ENABLED=false — read-only Reddit access is not active. "
        "See docs/reddit-access-request.md for what's required to enable it.",
    )


@router.get("/connect", response_model=RedditConnectOut)
async def connect(
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Issue an authorize URL plus a single-use state bound to this account."""
    if not settings.reddit_api_enabled:
        raise _disabled()

    state = secrets.token_urlsafe(32)
    authorize_url = reddit_client.build_authorize_url(settings, state)
    session.add(
        RedditOAuthState(
            account_id=account_id,
            state=state,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES),
        )
    )
    await session.commit()
    return RedditConnectOut(authorize_url=authorize_url, state=state)


@router.post("/callback", response_model=RedditConnectionOut)
async def callback(
    body: RedditCallbackIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Complete OAuth from the frontend callback page, over an authenticated call.

    The account comes from the session, never from the request body — a
    caller cannot complete someone else's connection by naming their account.
    """
    if not settings.reddit_api_enabled:
        raise _disabled()

    now = datetime.now(timezone.utc)
    record = (
        await session.execute(
            select(RedditOAuthState).where(
                RedditOAuthState.state == body.state,
                RedditOAuthState.account_id == account_id,
            )
        )
    ).scalars().first()
    if record is None:
        raise HTTPException(400, "Invalid OAuth state")
    if record.used_at is not None:
        raise HTTPException(400, "This OAuth state has already been used")
    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(400, "OAuth state has expired; start the connection again")

    # Consumed before the exchange: a code that fails to exchange must not
    # leave the state reusable for another attempt.
    record.used_at = now
    await session.commit()

    try:
        token_data = await reddit_client.exchange_code_for_token(settings, body.code)
    except reddit_client.RedditAPIError as exc:
        raise HTTPException(502, f"Reddit rejected the authorization: {exc}")

    connection = (
        await session.execute(select(RedditConnection).where(RedditConnection.account_id == account_id))
    ).scalars().first()
    if not connection:
        connection = RedditConnection(account_id=account_id)
        session.add(connection)

    connection.access_token_encrypted = encrypt_token(settings, token_data["access_token"])
    refresh_token = token_data.get("refresh_token") or ""
    if refresh_token or not connection.refresh_token_encrypted:
        connection.refresh_token_encrypted = encrypt_token(settings, refresh_token)
    connection.scopes = token_data.get("scope", "")
    expires_in = token_data.get("expires_in")
    try:
        lifetime = int(expires_in) if expires_in is not None else 3600
    except (TypeError, ValueError):
        lifetime = 3600
    connection.token_expires_at = now + timedelta(seconds=lifetime)
    connection.is_active = True
    await session.commit()
    await session.refresh(connection)
    return RedditConnectionOut(
        connected=True, scopes=connection.scopes, token_expires_at=connection.token_expires_at
    )


@router.delete("/connection", status_code=204)
async def disconnect(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    """Deactivate the connection and destroy the stored tokens.

    The row itself is kept (it carries the reddit_username and scopes for the
    audit trail) but is left with no credentials and is_active=False, so the
    ingestion jobs skip it. Conversations already ingested are untouched —
    disconnecting is not a data deletion.
    """
    connection = (
        await session.execute(select(RedditConnection).where(RedditConnection.account_id == account_id))
    ).scalars().first()
    if connection:
        connection.access_token_encrypted = ""
        connection.refresh_token_encrypted = ""
        connection.token_expires_at = None
        connection.scopes = ""
        connection.is_active = False
        await session.commit()
