"""Subscription resolution and server-side quota enforcement. Nothing in
this module touches Stripe — it's pure DB + the plan registry
(app/core/plans.py), so it works (and is tested) with zero external
dependencies. Stripe-specific code lives in app/services/stripe_billing.py
and is only reached once a subscription actually needs to change plan.

Every quota check here runs server-side, in the request path, before the
action it gates — per the brief's explicit instruction not to rely on
frontend-only restrictions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plans import DEFAULT_PLAN_ID, PlanLimits, get_plan
from app.models.billing import Subscription, UsageCounter
from app.models.dataset import Dataset
from app.models.workspace import Workspace


class QuotaExceededError(Exception):
    """Raised when an action would exceed the current plan's limits.
    Routers translate this into a 402 Payment Required."""


def current_period_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def get_or_create_subscription_for_user(db: AsyncSession, user_id: str) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.owner_user_id == user_id))
    subscription = result.scalar_one_or_none()
    if subscription is not None:
        return subscription

    subscription = Subscription(owner_user_id=user_id, plan_id=DEFAULT_PLAN_ID)
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_or_create_subscription_for_organization(db: AsyncSession, organization_id: str) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.organization_id == organization_id))
    subscription = result.scalar_one_or_none()
    if subscription is not None:
        return subscription

    subscription = Subscription(organization_id=organization_id, plan_id=DEFAULT_PLAN_ID)
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_subscription_for_workspace(db: AsyncSession, workspace: Workspace) -> Subscription:
    if workspace.owner_user_id is not None:
        return await get_or_create_subscription_for_user(db, workspace.owner_user_id)
    if workspace.organization_id is not None:
        return await get_or_create_subscription_for_organization(db, workspace.organization_id)
    raise ValueError("Workspace has no owner")


def plan_for(subscription: Subscription) -> PlanLimits:
    return get_plan(subscription.plan_id)


async def count_saved_datasets(db: AsyncSession, subscription: Subscription) -> int:
    """Counts datasets across every workspace owned by this subscription's
    billing entity (a user's personal workspaces, or an organization's
    shared workspaces) — the cap is account-wide, not per-workspace, per
    the brief's "N saved datasets" plan descriptions."""
    if subscription.owner_user_id is not None:
        condition = Workspace.owner_user_id == subscription.owner_user_id
    elif subscription.organization_id is not None:
        condition = Workspace.organization_id == subscription.organization_id
    else:
        raise ValueError("Subscription has no owner")

    result = await db.execute(
        select(func.count(Dataset.id)).join(Workspace, Dataset.workspace_id == Workspace.id).where(condition)
    )
    return result.scalar_one()


async def check_upload_allowed(db: AsyncSession, subscription: Subscription, file_size_bytes: int) -> None:
    plan = plan_for(subscription)

    if file_size_bytes > plan.max_upload_size_bytes:
        raise QuotaExceededError(
            f"File is {file_size_bytes} bytes, which exceeds the {plan.name} plan's "
            f"{plan.max_upload_size_bytes}-byte upload limit. Upgrade your plan for larger uploads."
        )

    if plan.max_saved_datasets is not None:
        current_count = await count_saved_datasets(db, subscription)
        if current_count >= plan.max_saved_datasets:
            raise QuotaExceededError(
                f"The {plan.name} plan allows at most {plan.max_saved_datasets} saved datasets "
                f"(you have {current_count}). Upgrade your plan or delete an existing dataset."
            )


async def _get_or_create_usage_counter(db: AsyncSession, subscription_id: str, period_key: str) -> UsageCounter:
    result = await db.execute(
        select(UsageCounter).where(
            UsageCounter.subscription_id == subscription_id, UsageCounter.period_key == period_key
        )
    )
    counter = result.scalar_one_or_none()
    if counter is not None:
        return counter

    counter = UsageCounter(subscription_id=subscription_id, period_key=period_key, analyses_count=0)
    db.add(counter)
    await db.flush()
    return counter


async def check_and_increment_analysis_quota(db: AsyncSession, subscription: Subscription) -> UsageCounter:
    """Raises QuotaExceededError (without incrementing) if the account is
    already at its monthly limit; otherwise increments and returns the
    counter. Caller is expected to commit."""
    plan = plan_for(subscription)
    period_key = current_period_key()
    counter = await _get_or_create_usage_counter(db, subscription.id, period_key)

    if plan.max_analyses_per_month is not None and counter.analyses_count >= plan.max_analyses_per_month:
        raise QuotaExceededError(
            f"The {plan.name} plan allows {plan.max_analyses_per_month} analyses per month, and "
            f"you've used all {counter.analyses_count} for {period_key}. Upgrade your plan or wait "
            "until next month."
        )

    counter.analyses_count += 1
    return counter
