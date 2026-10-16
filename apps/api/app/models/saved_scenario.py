from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.workspace import Workspace


class SavedScenario(UUIDPKMixin, TimestampMixin, Base):
    """A named set of scenario adjustments (e.g. "rent +10%") a user can
    re-run later without re-entering them. adjustments is a JSON array of
    {column, adjustment_type, value} objects — the same shape as
    app/schemas/scenario.py's ScenarioAdjustmentIn, validated through
    that schema at both save and run time so a stored row can never hold
    an adjustment the computation layer wouldn't also accept fresh."""

    __tablename__ = "saved_scenarios"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    adjustments: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    workspace: Mapped["Workspace"] = relationship()
