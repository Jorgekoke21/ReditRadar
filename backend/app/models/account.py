import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import Timestamped, UUIDPk


class Account(Base, UUIDPk, Timestamped):
    """A billing/ownership boundary. Single-user today, but every record
    hangs off account_id so multi-user never requires a data migration."""

    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(200), default="My workspace")

    profiles: Mapped[list["Profile"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Profile(Base, UUIDPk, Timestamped):
    """One row per Supabase auth user. profile.id == Supabase auth.users.id.

    email is deliberately NOT unique: identity is the Supabase-issued UUID
    (profiles.id) only — "no utilizar el email como identificador
    permanente". A unique constraint here would make email a de facto
    identity key (two different auth subjects could legitimately share an
    email across the dev-login and real-JWT paths, or in principle across
    future auth providers) and throw a raw IntegrityError instead of
    provisioning a second, distinct profile. Kept indexed for lookup speed."""

    __tablename__ = "profiles"

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")

    account: Mapped["Account"] = relationship(back_populates="profiles")
