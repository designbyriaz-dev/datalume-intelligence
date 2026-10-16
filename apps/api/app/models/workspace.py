import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class IndustryType(str, enum.Enum):
    GENERAL = "general"
    COMMERCIAL_PROPERTY = "commercial_property"
    RESIDENTIAL_PROPERTY = "residential_property"
    SOCIAL_HOUSING = "social_housing"
    BUSINESS_FINANCE = "business_finance"
    PUBLIC_SECTOR = "public_sector"
    EDUCATION = "education"
    OPERATIONS_LOGISTICS = "operations_logistics"
    OTHER = "other"


class Workspace(UUIDPKMixin, TimestampMixin, Base):
    """A workspace is owned either by a single user (personal) or by an
    organization (shared). Exactly one of owner_user_id / organization_id
    is set; this is enforced in the service layer rather than a DB
    constraint because SQLite (used in tests) has limited CHECK support.
    """

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(Enum(IndustryType, native_enum=False, length=64), nullable=False)

    # Overrides the 12-month default used by the "leases expiring" /
    # "overdue inspection" industry KPIs (app/services/industry_kpis.py)
    # and the matching PDF report sections. NULL means "use the default" —
    # not every workspace needs an opinion on this.
    kpi_window_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )

    owner: Mapped["User | None"] = relationship()
    organization: Mapped["Organization | None"] = relationship(back_populates="workspaces")
