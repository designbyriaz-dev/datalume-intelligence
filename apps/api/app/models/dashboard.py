from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Dashboard(UUIDPKMixin, TimestampMixin, Base):
    """A named, persisted arrangement of widgets against one dataset
    table. Only the widget *configuration* (what to show) is stored here
    — values are always computed live on read, the same way a KPI
    dashboard or an /analyze call is, never cached/stale data pretending
    to be current."""

    __tablename__ = "dashboards"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # SET NULL, not CASCADE: this dashboard belongs to its *workspace*
    # — deleting a contributor's account shouldn't delete a dashboard
    # they built for a shared team. See app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan", order_by="DashboardWidget.position"
    )
    comments: Mapped[list["DashboardComment"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan", order_by="DashboardComment.created_at"
    )


class DashboardWidget(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_widgets"

    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    widget_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "kpi" | "chart"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # For widget_type="kpi": {"kpi_id": "total_rent_roll"}
    # For widget_type="chart": {"operation": "group_aggregate", "parameters": {...}}
    # (operation must be a name in app/services/tools.py's TOOLS registry)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="widgets")


class DashboardComment(UUIDPKMixin, TimestampMixin, Base):
    """Collaboration on a shared dashboard — any workspace member
    (including read-only Viewer/Auditor roles) can comment, since
    discussing data is a read-level activity, not a mutation of it. Only
    the comment's own author can delete it (no moderation roles for this
    first pass)."""

    __tablename__ = "dashboard_comments"

    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    # SET NULL, not CASCADE: a comment thread shouldn't vanish because
    # its author later deleted their account. A null-author comment
    # simply can no longer be deleted via the "only the author" rule
    # above — see app/services/account_deletion.py.
    author_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="comments")
