from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SchedulerLock(Base):
    """A tiny row-level lease lock (see app/services/distributed_lock.py)
    so only one API replica's in-process APScheduler job processes a
    given recurring task — e.g. scheduled_reports.py's
    run_due_scheduled_reports — at a time. Previously that job was
    documented as single-instance-only; this is what lets it run safely
    behind more than one replica.

    Deliberately not a UUIDPKMixin/TimestampMixin entity like the rest
    of this app's models: a lock is identified by a fixed, known id
    (e.g. "scheduled_reports"), not a generated one, and there's no
    "created by" concept worth an audit trail for a row whose own
    history (via locked_until/locked_by) is already a leasing state
    machine, not an event log."""

    __tablename__ = "scheduler_locks"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    locked_until: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
