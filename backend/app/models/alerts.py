import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import AccountOwned, Timestamped, UUIDPk


class AlertSettings(Base, UUIDPk, Timestamped, AccountOwned):
    __tablename__ = "alert_settings"

    email_recipient: Mapped[str] = mapped_column(String(320), default="")
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Madrid")
    daily_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_digest_time: Mapped[str] = mapped_column(String(5), default="09:00")  # HH:MM
    min_score_threshold: Mapped[int] = mapped_column(Integer, default=60)
    urgent_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    urgent_score_threshold: Mapped[int] = mapped_column(Integer, default=90)
    max_urgent_per_day: Mapped[int] = mapped_column(Integer, default=2)
    weekly_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertDelivery(Base, UUIDPk):
    __tablename__ = "alert_deliveries"

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # daily_digest | urgent | weekly_digest | test
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(300))
    body_html: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str] = mapped_column(String(320))
    provider: Mapped[str] = mapped_column(String(30))
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
