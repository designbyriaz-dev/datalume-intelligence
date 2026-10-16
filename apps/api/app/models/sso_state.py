from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class SSOLoginState(UUIDPKMixin, TimestampMixin, Base):
    """CSRF state for the OIDC authorization-code flow, stored server-side
    rather than in a cookie/session (this app has no session middleware).
    A row is created when /sso/login redirects to the identity provider,
    and consumed (deleted) when /sso/callback returns — one-time use,
    short-lived (see app/services/sso.py's STATE_EXPIRY)."""

    __tablename__ = "sso_login_states"

    state: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
