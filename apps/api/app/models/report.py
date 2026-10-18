from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.dataset import DatasetTable


class Report(UUIDPKMixin, TimestampMixin, Base):
    """A generated, downloadable report file. `report_type` is a free
    string, not a DB enum — see app/services/reports.py for every
    `generate_*_report_pdf` function and app/api/v1/routers/reports.py
    for the endpoint that creates each `report_type` value. Most are
    deterministic KPI-table reports; "executive_intelligence" is the one
    exception with an AI-generated narrative section (real LLM call, not
    scaffolding — see that report's own docstring)."""

    __tablename__ = "reports"

    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    # SET NULL, not CASCADE: this report belongs to its *dataset table*
    # — deleting the user who generated it shouldn't delete the report
    # itself. See app/services/account_deletion.py.
    generated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    dataset_table: Mapped["DatasetTable"] = relationship()
