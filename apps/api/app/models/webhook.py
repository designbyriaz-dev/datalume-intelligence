from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.workspace import Workspace


class WebhookSubscription(UUIDPKMixin, TimestampMixin, Base):
    """An outbound webhook: when a subscribed event happens in this
    workspace, we POST a signed JSON payload to `url`. Signed the same
    way Stripe signs webhooks to us (app/services/stripe_billing.py /
    webhook_handlers.py) — `t=<unix_ts>,v1=<hex hmac_sha256>` — so an
    integrator can verify authenticity with the same well-known scheme
    their own Stripe integration already knows how to check.

    No retry queue: a failed delivery is recorded (last_delivery_error)
    but not retried. See app/services/webhooks.py's module docstring."""

    __tablename__ = "webhook_subscriptions"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # SET NULL, not CASCADE: the webhook belongs to its *workspace* —
    # deleting the creator's account shouldn't delete a webhook a
    # shared team's integration still depends on. See
    # app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    last_delivery_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workspace: Mapped["Workspace"] = relationship()
