"""The compliance-rules engine — Phase 2's final slice (after Property
Records, Documents, Inventories, Maintenance requests) of the
property-management brief.

Deliberately a *configurable checklist tool*, not a legal-compliance
oracle: a `ComplianceRule` is something the landlord/agent defines for
themselves ("we require a valid gas safety certificate on file"), not a
claim by this app about what UK lettings law requires. The master brief
is explicit about this boundary — "do not invent certifications... or
claim accreditation without verification" and "flag provisions requiring
legal review" — so this engine never asserts that a property genuinely
*is* legally compliant, only whether it satisfies the checks the account
holder configured, using the brief's own careful, non-committal status
vocabulary (ComplianceStatus in app/services/compliance.py) rather than
a blunt pass/fail.

Only one check type exists for v1: DOCUMENT_REQUIRED, evaluated against
the Document rows already built (expiry_date and all) — see that
module's docstring for the status mapping. Results are computed fresh on
every request, never persisted — the same "always reflects current
state, never goes stale" choice already made for rent-ledger balances
and the industry KPI packs, not a new pattern.
"""

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.document import DocumentType


class ComplianceCheckType(str, enum.Enum):
    DOCUMENT_REQUIRED = "document_required"


class ComplianceRule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "compliance_rules"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[str] = mapped_column(
        Enum(ComplianceCheckType, native_enum=False, length=32),
        nullable=False,
        default=ComplianceCheckType.DOCUMENT_REQUIRED,
    )
    # Only meaningful for check_type=DOCUMENT_REQUIRED today; nullable
    # so the column doesn't need to change shape when a second
    # check_type is eventually added with different parameters.
    document_type: Mapped[str | None] = mapped_column(
        Enum(DocumentType, native_enum=False, length=32), nullable=True
    )
    requires_non_expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # How many days before expiry a document starts showing as
    # "potential issue" rather than "passes" — a early-warning window,
    # not a grace period after expiry (that's always "action may be
    # overdue" regardless of this value).
    warning_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
