import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, JSON, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import Priority
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class Topic(Base, UUIDPk, Timestamped, AccountOwned):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_topic_account_name"),)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[str] = mapped_column(String(100), default="es,en")
    priority: Mapped[Priority] = mapped_column(Enum(Priority, native_enum=False), default=Priority.medium)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    positive_examples: Mapped[list] = mapped_column(JSON, default=list)
    negative_examples: Mapped[list] = mapped_column(JSON, default=list)

    keywords: Mapped[list["TopicKeyword"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    exclusions: Mapped[list["TopicExclusion"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class TopicKeyword(Base, UUIDPk):
    __tablename__ = "topic_keywords"

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    phrase: Mapped[str] = mapped_column(String(200))

    topic: Mapped["Topic"] = relationship(back_populates="keywords")


class TopicExclusion(Base, UUIDPk):
    __tablename__ = "topic_exclusions"

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    phrase: Mapped[str] = mapped_column(String(200))

    topic: Mapped["Topic"] = relationship(back_populates="exclusions")
