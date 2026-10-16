import enum

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class DatasetVersionStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Dataset(UUIDPKMixin, TimestampMixin, Base):
    """A named, long-lived dataset within a workspace. Its actual content
    lives in one or more DatasetVersion rows — uploading a new file, or
    applying a cleaning transformation, creates a new version rather than
    mutating history, so earlier versions stay recoverable."""

    __tablename__ = "datasets"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version_number"
    )


class DatasetVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),)

    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(DatasetVersionStatus, native_enum=False, length=32),
        nullable=False,
        default=DatasetVersionStatus.PROCESSING,
    )

    # Populated for versions created by a file upload.
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Populated for versions created by applying a transformation to a
    # previous version (see Transformation below).
    derived_from_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
    tables: Mapped[list["DatasetTable"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class DatasetTable(UUIDPKMixin, TimestampMixin, Base):
    """One tabular sheet within a dataset version. A CSV upload produces
    exactly one; a multi-sheet XLSX upload produces one per worksheet."""

    __tablename__ = "dataset_tables"

    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full profiling output: column stats, inferred/suggested types, data
    # quality issues, quality score. See app/services/profiling.py for the
    # shape. Stored as JSON rather than normalized tables for now — this
    # is an intentional Phase 2 simplification, not the final schema from
    # the brief's full data model (see docs/ARCHITECTURE.md).
    profile: Mapped[dict] = mapped_column(JSON, nullable=False)

    # User-confirmed column types, keyed by column name, once they review
    # the inferred schema. None until confirmed.
    confirmed_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # User-confirmed industry field mapping (canonical_field -> actual
    # column name or null), once they review the automatic alias/token
    # matching in app/services/industry_matching.py. None until confirmed
    # — see get_effective_field_mapping in that module for the fallback
    # to automatic matching. Carried forward to new versions produced by
    # a cleaning operation (same as confirmed_schema), but NOT to a new
    # version produced by a fresh file upload (a new upload's columns
    # may be completely different).
    confirmed_field_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Where the actual row data for this table is stored (Parquet, inside
    # the same object storage as the raw upload).
    data_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)

    version: Mapped["DatasetVersion"] = relationship(back_populates="tables")


class Transformation(UUIDPKMixin, TimestampMixin, Base):
    """Audit trail entry for a cleaning operation that produced a new
    DatasetVersion from a previous one."""

    __tablename__ = "transformations"

    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    source_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    result_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    performed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
