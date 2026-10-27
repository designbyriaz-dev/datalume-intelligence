"""Property Intelligence — Phase 1 (Property Records & Rent Ledger) of the
property-management brief: Property, Tenancy, and an append-only
RentLedgerEntry. No payment collection yet — ledger entries are recorded
by hand by a landlord/agent user, never moved by a payment provider.
Documents, inventories, maintenance, and a compliance engine are later
phases that attach to Property/Tenancy as the foundation these build on.

RentLedgerEntry is deliberately append-only (no update/delete endpoint —
see app/api/v1/routers/properties.py): a running balance reconstructed
from the full entry history is the only way a ledger can be trusted, the
same "every cleaning operation creates a new version, never overwrites"
principle this codebase already applies to datasets.
"""

import enum

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TenancyStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDED = "ended"


class RentFrequency(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class LedgerEntryType(str, enum.Enum):
    CHARGE = "charge"
    PAYMENT = "payment"
    ADJUSTMENT = "adjustment"
    REFUND = "refund"


class Property(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "properties"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    postcode: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="United Kingdom")
    # Deliberately a plain string, not an enum — property types vary too
    # much across commercial/residential/mixed-use portfolios to enumerate
    # up front (unlike Workspace.industry, a small fixed set this app
    # itself defines behaviour around).
    property_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # SET NULL, not CASCADE: this property belongs to its *workspace* —
    # deleting a contributor's account shouldn't delete a property they
    # added to a shared team workspace. See app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenancies: Mapped[list["Tenancy"]] = relationship(
        back_populates="property", cascade="all, delete-orphan", order_by="Tenancy.start_date.desc()"
    )


class Tenancy(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tenancies"

    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    rent_amount_gbp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    rent_frequency: Mapped[str] = mapped_column(Enum(RentFrequency, native_enum=False, length=16), nullable=False)
    start_date: Mapped[object] = mapped_column(Date, nullable=False)
    end_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TenancyStatus, native_enum=False, length=16), nullable=False, default=TenancyStatus.ACTIVE
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    property: Mapped["Property"] = relationship(back_populates="tenancies")
    ledger_entries: Mapped[list["RentLedgerEntry"]] = relationship(
        back_populates="tenancy", cascade="all, delete-orphan", order_by="RentLedgerEntry.entry_date"
    )


class RentLedgerEntry(UUIDPKMixin, TimestampMixin, Base):
    """Append-only by design — see this module's own docstring. A
    tenancy's balance (app/services/property_kpis.py) is always computed
    fresh from the full entry history, never stored/cached, so it can
    never drift from what the ledger actually says."""

    __tablename__ = "rent_ledger_entries"

    tenancy_id: Mapped[str] = mapped_column(ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False)
    entry_type: Mapped[str] = mapped_column(Enum(LedgerEntryType, native_enum=False, length=16), nullable=False)
    amount_gbp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    entry_date: Mapped[object] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenancy: Mapped["Tenancy"] = relationship(back_populates="ledger_entries")
