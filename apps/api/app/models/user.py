from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Platform-admin status. No API path grants this — see
    # scripts/grant_admin.py — so there is no self-service privilege
    # escalation route; it requires direct database access, matching the
    # brief's "tightly restricted" requirement for admin capability.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # mfa_secret holds a pending (unconfirmed) or active TOTP secret —
    # set by /auth/mfa/setup, but mfa_enabled only flips to True once
    # /auth/mfa/enable confirms the user actually has it in an
    # authenticator app (a correct code was produced from it), not
    # merely that setup was requested.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(32), nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")
