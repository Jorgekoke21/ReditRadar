import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import Priority, SelfPromoPolicy, TriState
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class Community(Base, UUIDPk, Timestamped, AccountOwned):
    __tablename__ = "communities"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_community_account_name"),)

    name: Mapped[str] = mapped_column(String(100))  # e.g. "agency" (no r/ prefix)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    group: Mapped[str] = mapped_column(String(50), default="leads")  # leads | learning
    priority: Mapped[Priority] = mapped_column(Enum(Priority, native_enum=False), default=Priority.medium)
    primary_language: Mapped[str] = mapped_column(String(10), default="en")
    allows_links: Mapped[TriState] = mapped_column(Enum(TriState, native_enum=False), default=TriState.unknown)
    allows_self_promo: Mapped[SelfPromoPolicy] = mapped_column(
        Enum(SelfPromoPolicy, native_enum=False), default=SelfPromoPolicy.unknown
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    rules_url: Mapped[str] = mapped_column(String(500), default="")
    rules_last_reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    opportunities_found: Mapped[int] = mapped_column(Integer, default=0)
    responses_made: Mapped[int] = mapped_column(Integer, default=0)
    historical_outcome: Mapped[str] = mapped_column(Text, default="")
    reddit_watermark_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reddit_watermark_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reddit_last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reddit_last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reddit_last_error: Mapped[str] = mapped_column(Text, default="")
    reddit_rate_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
    reddit_rate_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    reddit_rate_reset_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class WatchProfile(Base, UUIDPk, Timestamped, AccountOwned):
    __tablename__ = "watch_profiles"

    name: Mapped[str] = mapped_column(String(200))
    languages: Mapped[str] = mapped_column(String(200), default="es,en")  # comma separated ISO codes
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_age_hours: Mapped[int] = mapped_column(Integer, default=72)

    communities: Mapped[list["WatchProfileCommunity"]] = relationship(
        back_populates="watch_profile", cascade="all, delete-orphan"
    )


class WatchProfileCommunity(Base, UUIDPk):
    __tablename__ = "watch_profile_communities"
    __table_args__ = (UniqueConstraint("watch_profile_id", "community_id", name="uq_watch_profile_community"),)

    watch_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("watch_profiles.id", ondelete="CASCADE"), index=True
    )
    community_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("communities.id", ondelete="CASCADE"), index=True
    )

    watch_profile: Mapped["WatchProfile"] = relationship(back_populates="communities")
