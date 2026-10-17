"""The business logic that reacts to a verified Stripe webhook event —
deliberately separated from app/services/stripe_billing.py so it can be
tested without a live Stripe account: a test only needs to construct a
plain dict shaped like a real Stripe event (and, at the router level, a
correctly-HMAC-signed payload — see tests/test_billing_webhook.py for
exactly how that's done without hitting Stripe at all).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plans import PLANS
from app.models.billing import Subscription, SubscriptionStatus
from app.services.audit import record_audit_event


def _plan_id_for_stripe_price(price_id: str) -> str | None:
    for plan in PLANS.values():
        if price_id in (plan.stripe_price_id_monthly, plan.stripe_price_id_annual):
            return plan.plan_id
    return None


def _billing_period_for_stripe_price(price_id: str) -> str | None:
    for plan in PLANS.values():
        if price_id == plan.stripe_price_id_monthly:
            return "monthly"
        if price_id == plan.stripe_price_id_annual:
            return "annual"
    return None


async def _get_subscription_by_id(db: AsyncSession, subscription_id: str) -> Subscription | None:
    return await db.get(Subscription, subscription_id)


async def _get_subscription_by_stripe_customer(db: AsyncSession, stripe_customer_id: str) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == stripe_customer_id)
    )
    return result.scalar_one_or_none()


async def handle_checkout_session_completed(db: AsyncSession, event_object: dict[str, Any]) -> None:
    subscription_id = event_object.get("client_reference_id")
    if not subscription_id:
        return  # not one of ours / malformed — nothing to do

    subscription = await _get_subscription_by_id(db, subscription_id)
    if subscription is None:
        return

    subscription.stripe_customer_id = event_object.get("customer")
    subscription.stripe_subscription_id = event_object.get("subscription")
    subscription.status = SubscriptionStatus.ACTIVE
    await db.commit()


async def handle_subscription_updated(db: AsyncSession, event_object: dict[str, Any]) -> None:
    stripe_subscription_id = event_object.get("id")
    stripe_customer_id = event_object.get("customer")

    subscription = None
    if stripe_subscription_id:
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        subscription = result.scalar_one_or_none()
    if subscription is None and stripe_customer_id:
        subscription = await _get_subscription_by_stripe_customer(db, stripe_customer_id)
    if subscription is None:
        return

    stripe_status = event_object.get("status")
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "trialing": SubscriptionStatus.TRIALING,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELED,
        "incomplete": SubscriptionStatus.INCOMPLETE,
        "incomplete_expired": SubscriptionStatus.CANCELED,
        "unpaid": SubscriptionStatus.PAST_DUE,
    }
    if stripe_status in status_map:
        new_status = status_map[stripe_status]
        # Recovered (a Stripe retry succeeded) — clear the dunning clock
        # so a *future* payment failure starts a fresh grace period
        # rather than being instantly overdue from a stale timestamp.
        # See app/services/dunning.py.
        if new_status == SubscriptionStatus.ACTIVE and subscription.status == SubscriptionStatus.PAST_DUE:
            subscription.past_due_since = None
        subscription.status = new_status

    items = event_object.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        if price_id:
            plan_id = _plan_id_for_stripe_price(price_id)
            if plan_id and plan_id != subscription.plan_id:
                old_plan_id = subscription.plan_id
                subscription.plan_id = plan_id
                subscription.billing_period = _billing_period_for_stripe_price(price_id)
                # Webhook-triggered, so there's no logged-in actor in the
                # usual sense — but every Subscription has exactly one
                # owner, either an organization or a user (see
                # Subscription's docstring), so the event is always
                # attributable to one of the two AuditLog subject fields.
                # A personal subscription's owner_user_id becomes
                # actor_user_id here not because they "did" anything (the
                # webhook did), but because that's the one AuditLog field
                # that makes the event show up in that user's own
                # GET /users/me/audit-log — the same way org_id makes an
                # org subscription's change show up in that org's log.
                await record_audit_event(
                    db,
                    event_type="billing.plan_changed",
                    actor_user_id=subscription.owner_user_id,
                    organization_id=subscription.organization_id,
                    metadata={"old_plan_id": old_plan_id, "new_plan_id": plan_id},
                )
            elif plan_id:
                subscription.billing_period = _billing_period_for_stripe_price(price_id)

    period_end = event_object.get("current_period_end")
    if period_end:
        subscription.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    subscription.cancel_at_period_end = bool(event_object.get("cancel_at_period_end", False))

    await db.commit()


async def handle_subscription_deleted(db: AsyncSession, event_object: dict[str, Any]) -> None:
    stripe_subscription_id = event_object.get("id")
    if not stripe_subscription_id:
        return
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return

    previous_plan_id = subscription.plan_id
    subscription.status = SubscriptionStatus.CANCELED
    subscription.past_due_since = None  # no longer meaningful once canceled
    # Downgrade to free rather than leaving the account on a paid plan_id
    # with a canceled Stripe subscription — quota enforcement reads
    # plan_id directly, so this is what actually takes the entitlements
    # away, not just the status flag.
    subscription.plan_id = "free"

    # Same reasoning as handle_subscription_updated's billing.plan_changed
    # above: owner_user_id/organization_id are mutually exclusive on
    # Subscription, so passing both unconditionally attributes this to
    # whichever one is actually set, for both personal and org accounts.
    await record_audit_event(
        db,
        event_type="billing.subscription_canceled",
        actor_user_id=subscription.owner_user_id,
        organization_id=subscription.organization_id,
        metadata={"previous_plan_id": previous_plan_id},
    )

    await db.commit()


async def handle_invoice_payment_failed(db: AsyncSession, event_object: dict[str, Any]) -> None:
    stripe_customer_id = event_object.get("customer")
    if not stripe_customer_id:
        return
    subscription = await _get_subscription_by_stripe_customer(db, stripe_customer_id)
    if subscription is None:
        return

    subscription.status = SubscriptionStatus.PAST_DUE
    # Only set on the FIRST failure of a dunning cycle — Stripe's own
    # smart retries fire several invoice.payment_failed events over the
    # grace period, and resetting the clock on each one would mean the
    # grace period never actually expires. See app/services/dunning.py,
    # which reads this to decide when the grace period is up.
    if subscription.past_due_since is None:
        subscription.past_due_since = datetime.now(timezone.utc)
    await db.commit()


_HANDLERS = {
    "checkout.session.completed": handle_checkout_session_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_failed": handle_invoice_payment_failed,
}


async def handle_stripe_event(db: AsyncSession, event: dict[str, Any]) -> bool:
    """Returns True if the event type was recognized and handled, False
    if it was ignored (Stripe sends many event types we don't act on —
    ignoring unknown ones is correct, not an error)."""
    handler = _HANDLERS.get(event.get("type", ""))
    if handler is None:
        return False
    await handler(db, event["data"]["object"])
    return True
