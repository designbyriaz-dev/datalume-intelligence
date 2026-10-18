from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.workspace import Workspace


class ScheduledReport(UUIDPKMixin, TimestampMixin, Base):
    """A recurring report generation schedule. Processed by
    app/services/scheduled_reports.py's run_due_scheduled_reports, which
    runs both on a real in-process APScheduler job (see app/main.py) and
    directly in tests (no waiting on wall-clock time required — tests
    just set next_run_at into the past and call the function)."""

    __tablename__ = "scheduled_reports"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)  # "daily" | "weekly" | "monthly"
    next_run_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Email delivery is a separate concern from generation — a report can
    # generate successfully (last_run_at/last_error above) while delivery
    # fails (wrong address, SMTP outage), or vice versa isn't possible
    # (delivery is only attempted after a successful generation). Kept as
    # its own pair of columns, mirroring WebhookSubscription's
    # last_delivery_at/last_delivery_error, so a user can tell "this isn't
    # running" apart from "it's running, but the emails aren't arriving."
    last_email_sent_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_email_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # SET NULL, not CASCADE: the schedule belongs to its *workspace* —
    # deleting the creator's account shouldn't delete a schedule a
    # shared team still relies on. Once null, run_due_scheduled_reports
    # still generates the report but has no one to email it to — see
    # app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    workspace: Mapped["Workspace"] = relationship()
