from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.dataset import DatasetTable


class AnalysisRun(UUIDPKMixin, TimestampMixin, Base):
    """A single execution of a deterministic analytical tool (see
    app/services/analytics.py) against one DatasetTable. Persisting every
    run is what makes "saved analyses" true — nothing special has to
    happen to save one; running it saves it."""

    __tablename__ = "analysis_runs"

    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    # SET NULL, not CASCADE: deleting the user who ran this analysis
    # shouldn't delete the saved result itself — see
    # app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    dataset_table: Mapped["DatasetTable"] = relationship()
