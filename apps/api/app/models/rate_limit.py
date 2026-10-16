from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin


class RateLimitWindow(UUIDPKMixin, Base):
    """One fixed-window request counter — see app/services/rate_limit.py
    for how it's read and incremented. bucket_key is caller-defined,
    typically "{route}:{client_ip}" (e.g. "login:203.0.113.5"), so the
    same table serves every rate-limited endpoint rather than one table
    per endpoint.

    Rows aren't deleted when their window ends, only when they age out
    via the periodic cleanup job in app/main.py — a window that's past
    is simply never matched again by check_rate_limit's query, so a
    stale row is inert, not incorrect, between cleanups."""

    __tablename__ = "rate_limit_windows"
    __table_args__ = (UniqueConstraint("bucket_key", "window_start", name="uq_rate_limit_bucket_window"),)

    bucket_key: Mapped[str] = mapped_column(String(255), nullable=False)
    window_start: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
