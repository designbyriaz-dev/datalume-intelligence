"""The dunning flow: the grace period between a subscription's payment
first failing and it being downgraded to the Free plan.

Independent of whatever Stripe's own dashboard-configured smart-retry
and auto-cancellation settings might also be doing — this app owns the
exact grace period (see DEFAULT_GRACE_PERIOD) and sends exactly one
email, deterministically, rather than depending on however a Stripe
dashboard happens to be configured for a given account. Once the grace
period expires, the Stripe subscription itself is also canceled
(best-effort — see downgrade_overdue_subscriptions), so Stripe and this
app agree the customer is no longer subscribed, not just this app's own
database.

Same pattern as app/services/scheduled_reports.py: a distributed lock
(app/services/distributed_lock.py) so only one API replica processes a
given tick, called from an APScheduler interval job in app/main.py, and
exercised directly by tests rather than through wall-clock waiting.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Subscription, SubscriptionStatus
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.services.audit import record_audit_event
from app.services.distributed_lock import release_lock, try_acquire_lock
from app.services.email import EmailMessage, EmailSender
from app.services.stripe_billing import StripeBillingClient

logger = logging.getLogger("datalume.dunning")

DUNNING_LOCK_ID = "dunning"
DEFAULT_GRACE_PERIOD = dt.timedelta(days=7)


async def _resolve_recipients(db: AsyncSession, subscription: Subscription) -> list[tuple[str, str]]:
    """Personal subscription: its one owner. Organization subscription:
    every member with the OWNER role (an org can have more than one) —
    the same role this app already treats as the one authorized to
    manage billing (see app/services/authz.py's ORG_MANAGE_ROLES)."""
    if subscription.owner_user_id is not None:
        user = await db.get(User, subscription.owner_user_id)
        return [(user.email, user.full_name)] if user is not None else []

    if subscription.organization_id is not None:
        result = await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == subscription.organization_id,
                Membership.role == MembershipRole.OWNER,
            )
        )
        return [(user.email, user.full_name) for user in result.scalars().all()]

    return []


async def downgrade_overdue_subscriptions(
    db: AsyncSession,
    *,
    now: dt.datetime | None = None,
    grace_period: dt.timedelta = DEFAULT_GRACE_PERIOD,
    email_sender: EmailSender | None = None,
    stripe_client: StripeBillingClient | None = None,
) -> list[Subscription]:
    now = now or dt.datetime.now(dt.timezone.utc)

    holder = await try_acquire_lock(db, DUNNING_LOCK_ID, now=now)
    if holder is None:
        # Another replica's tick already holds this lock — skip rather
        # than risk two replicas downgrading (and double-emailing) the
        # same subscription.
        return []

    try:
        return await _downgrade_overdue_subscriptions_locked(
            db, now=now, grace_period=grace_period, email_sender=email_sender, stripe_client=stripe_client
        )
    finally:
        await release_lock(db, DUNNING_LOCK_ID, holder)


async def _downgrade_overdue_subscriptions_locked(
    db: AsyncSession,
    *,
    now: dt.datetime,
    grace_period: dt.timedelta,
    email_sender: EmailSender | None,
    stripe_client: StripeBillingClient | None,
) -> list[Subscription]:
    cutoff = now - grace_period
    result = await db.execute(
        select(Subscription).where(
            Subscription.status == SubscriptionStatus.PAST_DUE,
            Subscription.past_due_since.is_not(None),
            Subscription.past_due_since <= cutoff,
        )
    )
    overdue = list(result.scalars().all())

    downgraded: list[Subscription] = []
    for subscription in overdue:
        previous_plan_id = subscription.plan_id

        if stripe_client is not None and subscription.stripe_subscription_id:
            # Best-effort: the local downgrade (the part that actually
            # controls this app's own entitlements) must still happen
            # even if Stripe is unreachable or the subscription was
            # already canceled on Stripe's side for some other reason.
            try:
                stripe_client.cancel_subscription(stripe_subscription_id=subscription.stripe_subscription_id)
            except Exception as exc:  # noqa: BLE001 - see comment above
                logger.warning(
                    "Failed to cancel Stripe subscription %s during dunning downgrade: %s",
                    subscription.stripe_subscription_id,
                    exc,
                )

        subscription.plan_id = "free"
        subscription.status = SubscriptionStatus.CANCELED
        subscription.past_due_since = None
        subscription.cancel_at_period_end = False

        await record_audit_event(
            db,
            event_type="billing.downgraded_for_nonpayment",
            actor_user_id=subscription.owner_user_id,
            organization_id=subscription.organization_id,
            metadata={"previous_plan_id": previous_plan_id},
        )

        downgraded.append(subscription)

        if email_sender is not None:
            # Delivery is best-effort and independent of the downgrade
            # itself — mirrors scheduled_reports.py's email handling: a
            # failed send must never undo (or block committing) the
            # downgrade that already happened.
            for recipient_email, recipient_name in await _resolve_recipients(db, subscription):
                try:
                    email_sender.send(
                        EmailMessage(
                            to=recipient_email,
                            subject="DataLume: your subscription has been downgraded",
                            text_body=(
                                f"Hi {recipient_name},\n\n"
                                "We were unable to collect payment for your DataLume subscription "
                                "after several attempts, so it has now been downgraded to the Free "
                                "plan.\n\n"
                                "You can resubscribe at any time from your billing settings.\n\n"
                                "— DataLume Intelligence"
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - record, don't crash the tick
                    logger.warning("Failed to send dunning downgrade email to %s: %s", recipient_email, exc)

    await db.commit()
    return downgraded
