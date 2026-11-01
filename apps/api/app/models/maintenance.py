"""Property maintenance requests — Phase 2 (fourth slice, after Property
Records, Documents, and Inventories) of the property-management brief:
"a MaintenanceRequest register".

Scoped to Property, not Tenancy — unlike RentLedgerEntry or Inventory,
a maintenance issue ("boiler broken", "leaking roof") is fundamentally
about the property itself and can exist with no tenant involved at all
(a landlord's own routine maintenance). `tenancy_id` is an optional
pointer to which tenancy reported it, not the scoping key.
"""

import enum

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class MaintenancePriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"


class MaintenanceStatus(str, enum.Enum):
    REPORTED = "reported"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MaintenanceRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_requests"

    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    # SET NULL, not CASCADE: which tenancy reported this is incidental
    # context, not the thing the request belongs to — see this module's
    # docstring. (No endpoint deletes a Tenancy independently of its
    # Property today, so this only matters if that ever changes.)
    tenancy_id: Mapped[str | None] = mapped_column(ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        Enum(MaintenancePriority, native_enum=False, length=16), nullable=False, default=MaintenancePriority.MEDIUM
    )
    status: Mapped[str] = mapped_column(
        Enum(MaintenanceStatus, native_enum=False, length=16), nullable=False, default=MaintenanceStatus.REPORTED
    )
    reported_date: Mapped[object] = mapped_column(Date, nullable=False)
    resolved_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
