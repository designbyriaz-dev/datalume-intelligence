from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.dataset import DatasetTable


class Report(UUIDPKMixin, TimestampMixin, Base):
    """A generated, downloadable report file. Only "data_quality" exists
    today (see app/services/reports.py) — the brief's other eleven report
    templates (Executive Intelligence, Financial Performance, etc.) are
    backlog and would mostly need the AI analyst's narrative generation,
    which isn't wired to a real model yet."""

    __tablename__ = "reports"

    dataset_table_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    generated_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    dataset_table: Mapped["DatasetTable"] = relationship()
