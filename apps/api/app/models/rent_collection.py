"""Rent Collection v1 (Stripe Connect, pay-by-link) — see
docs/CHECKLIST.md's "Rent Collection v1" section for the full plan this
implements. Gated behind settings.rent_collection_enabled (default
False, see app/services/stripe_connect.py) and deliberately scoped:
one-off payment links per existing RentLedgerEntry charge, no recurring
auto-debit, no tenant portal.

WorkspaceStripeAccount: one Stripe Connect account per workspace.
RentPaymentRequest: one row per "Request payment" click, linking a
specific charge entry to a specific Stripe Checkout Session.
ProcessedWebhookEvent: the idempotency guard for Connect webhook
redelivery — see its own docstring for why this feature needs one when
app/services/webhook_handlers.py's existing billing webhooks don't.
"""

import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ConnectAccountStatus(str, enum.Enum):
    PENDING = "pending"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    RESTRICTED = "restricted"


class RentPaymentRequestStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELED = "canceled"


class WorkspaceStripeAccount(UUIDPKMixin, TimestampMixin, Base):
    """One Stripe Connect account per workspace — CASCADE on workspace
    delete (unlike created_by_user_id's SET NULL below): the account
    belongs to the workspace, and a row with no workspace left to
    collect rent for is meaningless."""

    __tablename__ = "workspace_stripe_accounts"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        Enum(ConnectAccountStatus, native_enum=False, length=16),
        nullable=False,
        default=ConnectAccountStatus.PENDING,
    )
    charges_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    payouts_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    # SET NULL, not CASCADE — same reasoning as Property/Tenancy's own
    # created_by_user_id: the account belongs to the workspace, not
    # whoever happened to click "Connect bank account".
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class RentPaymentRequest(UUIDPKMixin, TimestampMixin, Base):
    """One per "Request payment" click on a charge ledger entry. The
    charge entry itself never changes (the ledger stays append-only,
    see app/models/property.py) — this is the audit trail of "we asked
    Stripe to collect this", independent of whether it ever gets paid.
    """

    __tablename__ = "rent_payment_requests"

    ledger_entry_id: Mapped[str] = mapped_column(
        ForeignKey("rent_ledger_entries.id", ondelete="CASCADE"), nullable=False
    )
    tenancy_id: Mapped[str] = mapped_column(ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False)
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_gbp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(RentPaymentRequestStatus, native_enum=False, length=16),
        nullable=False,
        default=RentPaymentRequestStatus.PENDING,
    )
    tenant_email: Mapped[str] = mapped_column(String(320), nullable=False)
    checkout_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Set once the webhook creates the resulting payment ledger entry —
    # answers "which ledger row did this request produce" directly,
    # without re-deriving it from amount/date matching.
    resulting_ledger_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("rent_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    ledger_entry: Mapped["RentLedgerEntry"] = relationship(foreign_keys=[ledger_entry_id])


class ProcessedWebhookEvent(UUIDPKMixin, TimestampMixin, Base):
    """Dedup guard for Stripe Connect webhook redelivery. Stripe
    explicitly documents at-least-once delivery — app/services/
    webhook_handlers.py's existing billing webhooks have no equivalent
    table because every handler there is naturally idempotent
    (overwrite-style updates). "Create a rent-ledger payment entry" is
    NOT naturally idempotent — redelivery would double-credit a
    tenant's payment — so this table makes that append-only operation
    idempotent too: the caller inserts the Stripe event id here (unique
    constraint) *before* dispatching to a handler, inside the same
    transaction as the handler's own writes, so a race between two
    redeliveries fails on the second INSERT rather than both racing
    past a SELECT-then-INSERT check.

    Scoped to Connect webhooks only, not the existing billing webhook
    (which doesn't need it and is left unmodified)."""

    __tablename__ = "processed_webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
