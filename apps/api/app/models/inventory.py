"""Check-in / check-out property inventories — Phase 2 (second slice,
after Documents) of the property-management brief. An Inventory is a
point-in-time condition record for a Tenancy (check-in, check-out, or a
mid-term inspection), made up of per-room/item InventoryItem rows.

Scoped to Tenancy, not Property directly — the same reasoning
RentLedgerEntry already follows (see app/models/property.py): an
inventory only makes sense against a specific tenant's occupancy period,
so the property is always reachable via tenancy.property_id rather than
duplicated here.

The brief's "diff view" (app/services/inventory_compare.py) is what this
model exists to support: comparing a tenancy's check-in inventory against
its check-out inventory to surface condition changes, missing items, and
new damage — the central use case for an inventory in UK lettings.
"""

import enum

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class InventoryType(str, enum.Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    MID_TERM = "mid_term"


class ItemCondition(str, enum.Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    DAMAGED = "damaged"
    MISSING = "missing"


class Inventory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inventories"

    tenancy_id: Mapped[str] = mapped_column(ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False)
    inventory_type: Mapped[str] = mapped_column(Enum(InventoryType, native_enum=False, length=16), nullable=False)
    inspection_date: Mapped[object] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="inventory", cascade="all, delete-orphan", order_by="InventoryItem.room, InventoryItem.item_name"
    )


class InventoryItem(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inventory_items"

    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id", ondelete="CASCADE"), nullable=False)
    room: Mapped[str] = mapped_column(String(255), nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    condition: Mapped[str] = mapped_column(Enum(ItemCondition, native_enum=False, length=16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    inventory: Mapped["Inventory"] = relationship(back_populates="items")
