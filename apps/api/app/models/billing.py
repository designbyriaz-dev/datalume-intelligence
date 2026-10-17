import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class BillingPeriod(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class Subscription(UUIDPKMixin, TimestampMixin, Base):
    """Exactly one of owner_user_id / organization_id is set, mirroring
    Workspace's personal-vs-organization split. Created automatically
    (on the free plan) when a user registers or an organization is
    created — see app/services/billing.py — so every billable entity
    always has exactly one Subscription row; there's no "no subscription"
    state to handle elsewhere in the app."""

    __tablename__ = "subscriptions"

    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )

    plan_id: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    status: Mapped[str] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=32),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    billing_period: Mapped[str | None] = mapped_column(
        Enum(BillingPeriod, native_enum=False, length=16), nullable=True
    )

    # Populated once this subscription has ever touched Stripe. All None
    # for an account still on the free plan.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_end: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # When this subscription first went PAST_DUE in its current dunning
    # cycle — set once on the first invoice.payment_failed webhook, left
    # untouched by any further failed-retry events in the same cycle
    # (Stripe's own smart retries fire several over the grace period),
    # and cleared the moment it recovers (back to ACTIVE) or the grace
    # period expires and it's downgraded. None whenever status isn't
    # PAST_DUE. See app/services/dunning.py.
    past_due_since: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usage_counters: Mapped[list["UsageCounter"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )


class UsageCounter(UUIDPKMixin, TimestampMixin, Base):
    """One row per (subscription, calendar month). analyses_count is the
    only metered-per-period quota today — max file size and max saved
    datasets are point-in-time checks, not period counters, so they don't
    need a row here (see app/services/billing.py)."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("subscription_id", "period_key", name="uq_usage_subscription_period"),)

    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    period_key: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    analyses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subscription: Mapped["Subscription"] = relationship(back_populates="usage_counters")
