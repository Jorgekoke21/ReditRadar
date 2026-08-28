import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    ConversationState,
    DraftVariant,
    MentionRadarin,
    OutcomeResult,
    PromotionRisk,
    RecommendedAction,
    SourceMode,
)
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class Conversation(Base, UUIDPk, Timestamped, AccountOwned):
    """Operational + temporary-raw fields live on the same row; raw_* columns
    are nulled out by the purge job (or immediately by the user) while every
    operational column survives so dedupe, history and metrics keep working.
    See docs/data-model.md ('Retention model') for the rationale."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("account_id", "reddit_post_id", name="uq_conversation_account_reddit_post"),
        UniqueConstraint("account_id", "dedupe_hash", name="uq_conversation_account_dedupe_hash"),
    )

    source_mode: Mapped[SourceMode] = mapped_column(Enum(SourceMode, native_enum=False))
    reddit_post_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    url: Mapped[str] = mapped_column(String(1000))
    url_normalized: Mapped[str] = mapped_column(String(1000), index=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True)
    subreddit: Mapped[str] = mapped_column(String(100), index=True)
    language: Mapped[str] = mapped_column(String(10), default="en")

    # --- temporary raw content (purged, see purge_expired_reddit_content) ---
    raw_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # --- operational data (kept indefinitely) ---
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    num_comments: Mapped[int] = mapped_column(Integer, default=0)
    reddit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_removed_upstream: Mapped[bool] = mapped_column(Boolean, default=False)

    state: Mapped[ConversationState] = mapped_column(
        Enum(ConversationState, native_enum=False), default=ConversationState.new, index=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("communities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    summary: Mapped[str] = mapped_column(Text, default="")
    problem_detected: Mapped[str] = mapped_column(Text, default="")
    score_total: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recommended_action: Mapped[RecommendedAction | None] = mapped_column(
        Enum(RecommendedAction, native_enum=False), nullable=True, index=True
    )
    promotion_risk: Mapped[PromotionRisk | None] = mapped_column(
        Enum(PromotionRisk, native_enum=False), nullable=True
    )
    is_analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    analysis: Mapped["ConversationAnalysis | None"] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", uselist=False
    )
    scores: Mapped[list["ConversationScore"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationScore.created_at.desc()"
    )
    drafts: Mapped[list["ReplyDraft"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    actions: Mapped[list["ConversationAction"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationAction.created_at.desc()"
    )
    outcome: Mapped["ConversationOutcome | None"] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", uselist=False
    )

    @property
    def display_title(self) -> str:
        """Falls back to the non-identifying summary once raw content is purged."""
        return self.raw_title or self.summary or "(contenido original eliminado)"


class ConversationAnalysis(Base, UUIDPk, Timestamped):
    __tablename__ = "conversation_analysis"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    analyzer: Mapped[str] = mapped_column(String(50))  # "rules" | "llm:<provider>:<model>"
    audience_type: Mapped[str] = mapped_column(String(200), default="")
    problem_detected: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(200), default="")
    topic_ids: Mapped[list] = mapped_column(JSON, default=list)
    can_add_value: Mapped[bool] = mapped_column(Boolean, default=False)
    value_angle: Mapped[str] = mapped_column(Text, default="")
    tool_request: Mapped[bool] = mapped_column(Boolean, default=False)
    radarin_fit: Mapped[str] = mapped_column(String(50), default="")
    promotion_risk: Mapped[PromotionRisk] = mapped_column(Enum(PromotionRisk, native_enum=False))
    recommended_action: Mapped[RecommendedAction] = mapped_column(Enum(RecommendedAction, native_enum=False))
    mention_radarin: Mapped[MentionRadarin] = mapped_column(Enum(MentionRadarin, native_enum=False))
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped["Conversation"] = relationship(back_populates="analysis")


class ConversationScore(Base, UUIDPk, Timestamped):
    __tablename__ = "conversation_scores"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    total: Mapped[int] = mapped_column(Integer)
    audience_fit: Mapped[int] = mapped_column(Integer, default=0)
    problem_fit: Mapped[int] = mapped_column(Integer, default=0)
    request_intent: Mapped[int] = mapped_column(Integer, default=0)
    value_potential: Mapped[int] = mapped_column(Integer, default=0)
    recency: Mapped[int] = mapped_column(Integer, default=0)
    low_competition: Mapped[int] = mapped_column(Integer, default=0)
    community_priority: Mapped[int] = mapped_column(Integer, default=0)
    promotion_risk_penalty: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(50))

    conversation: Mapped["Conversation"] = relationship(back_populates="scores")


class ReplyDraft(Base, UUIDPk, Timestamped):
    __tablename__ = "reply_drafts"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    variant: Mapped[DraftVariant] = mapped_column(Enum(DraftVariant, native_enum=False))
    language: Mapped[str] = mapped_column(String(10), default="en")
    body: Mapped[str] = mapped_column(Text)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="drafts")


class ConversationAction(Base, UUIDPk):
    __tablename__ = "conversation_actions"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=None, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="actions")


class ConversationOutcome(Base, UUIDPk, Timestamped):
    __tablename__ = "conversation_outcomes"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_text_used: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    upvotes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributed_visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributed_signups: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[OutcomeResult] = mapped_column(Enum(OutcomeResult, native_enum=False), default=OutcomeResult.no_result)

    conversation: Mapped["Conversation"] = relationship(back_populates="outcome")
