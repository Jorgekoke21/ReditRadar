from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class RedditConnection(Base, UUIDPk, Timestamped, AccountOwned):
    """Stores OAuth state for the (currently inert) official Reddit adapter.
    Tokens are stored via Fernet symmetric encryption (REDDIT_TOKEN_ENCRYPTION_KEY),
    never in plaintext. Nothing here is used while REDDIT_API_ENABLED=false."""

    __tablename__ = "reddit_connections"

    reddit_username: Mapped[str] = mapped_column(String(100), default="")
    scopes: Mapped[str] = mapped_column(String(300), default="")
    access_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
