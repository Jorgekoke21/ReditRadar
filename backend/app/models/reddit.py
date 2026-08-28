from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class RedditConnection(Base, UUIDPk, Timestamped, AccountOwned):
    """Per-account OAuth credentials for the official read-only Reddit adapter.

    Tokens are stored via Fernet symmetric encryption (REDDIT_TOKEN_ENCRYPTION_KEY),
    never in plaintext. `token_expires_at` is what the ingestion jobs check to
    decide whether to refresh before use (see services/jobs.py::
    _ensure_fresh_access_token) — Reddit access tokens are short-lived, so a
    connection is only usable as long as the refresh token keeps working.
    Nothing here is read while REDDIT_API_ENABLED=false."""

    __tablename__ = "reddit_connections"

    reddit_username: Mapped[str] = mapped_column(String(100), default="")
    scopes: Mapped[str] = mapped_column(String(300), default="")
    access_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class RedditOAuthState(Base, UUIDPk, Timestamped, AccountOwned):
    """Short-lived, single-use CSRF token for one Reddit OAuth attempt.

    The `state` parameter travels through the user's browser and comes back
    from Reddit, so it must never be trusted to *carry* the account id —
    anything the browser can hand us it can also forge. Instead the state is
    an opaque random value stored here and bound server-side to the account
    that started the flow; the callback identifies the account from the
    authenticated session and only checks that the returned state matches a
    row this same account created, is unexpired, and has not been consumed.
    """

    __tablename__ = "reddit_oauth_states"

    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
