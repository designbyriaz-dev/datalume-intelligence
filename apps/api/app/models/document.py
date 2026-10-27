"""Property documents — Phase 2 of the property-management brief. A
generalized file attached to a Property (and optionally a specific
Tenancy within it), reusing the existing ObjectStorage abstraction
app/services/storage.py already provides for dataset uploads — this is
not a new storage backend, just a new kind of row pointing into it.

`document_type` is a constrained enum, not a free string like
`Property.property_type` — unlike a property type, a document's type is
meant to be matched against by name later (the compliance-rules engine
this phase's brief also calls for: "is there a valid, non-expired
gas_safety_certificate for this property" needs a known vocabulary to
match on, not arbitrary user text). `expiry_date` exists for exactly
that: most of these document types (gas safety certs, EICRs, EPCs,
deposit protection, right-to-rent checks) have a real statutory renewal
date in UK lettings, and that is the field a compliance check will read
— this phase only stores it, it does not yet evaluate it.
"""

import enum

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class DocumentType(str, enum.Enum):
    TENANCY_AGREEMENT = "tenancy_agreement"
    GAS_SAFETY_CERTIFICATE = "gas_safety_certificate"
    EICR = "eicr"
    EPC = "epc"
    DEPOSIT_PROTECTION_CERTIFICATE = "deposit_protection_certificate"
    RIGHT_TO_RENT_CHECK = "right_to_rent_check"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    INVENTORY_REPORT = "inventory_report"
    OTHER = "other"


class Document(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    # Nullable: a document can belong to the property itself (an EPC,
    # a buildings-insurance certificate — applies regardless of who the
    # current tenant is) or to one specific tenancy (a signed tenancy
    # agreement, a right-to-rent check for that tenant).
    tenancy_id: Mapped[str | None] = mapped_column(ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=True)
    document_type: Mapped[str] = mapped_column(
        Enum(DocumentType, native_enum=False, length=32), nullable=False, default=DocumentType.OTHER
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expiry_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    # SET NULL, not CASCADE: this document belongs to its *property* —
    # deleting the user who uploaded it shouldn't delete the document
    # itself. See app/services/account_deletion.py.
    uploaded_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
