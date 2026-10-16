from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.user import User


class ApiKey(UUIDPKMixin, TimestampMixin, Base):
    """A personal access token: always authenticates as the specific user
    who created it (same model as a GitHub PAT), not a separate
    org-scoped principal with its own permission set. Keeping it this
    simple avoids building a second, parallel authorization system
    alongside the Membership-role one — an API key request goes through
    exactly the same require_workspace_access/require_workspace_write_access
    checks a browser-session request would, just authenticated
    differently. Only a SHA-256 hash of the key is ever stored; the raw
    value is shown to the user exactly once, at creation."""

    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship()
