import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class EmailTokenPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    ORG_INVITE = "org_invite"


class EmailToken(UUIDPKMixin, TimestampMixin, Base):
    """A one-time-use token emailed to someone — one shape covers all
    three purposes above (verify an email, reset a password, accept an
    org invite as a brand-new account) rather than three near-identical
    tables. `user_id` is set for the first two (an existing account);
    `target_email`/`organization_id`/`role` are set for ORG_INVITE
    instead, since no account exists yet to attach the invite to.

    Only a SHA-256 hash of the raw token is ever stored — same rationale
    as ApiKey: the raw value only needs to exist inside the email itself,
    never read back out of the database."""

    __tablename__ = "email_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(Enum(EmailTokenPurpose, native_enum=False, length=32), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    target_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
