from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_stripe_client_dep
from app.core.config import get_settings
from app.core.plans import PLANS, get_plan
from app.db.session import get_db
from app.models.billing import Subscription, UsageCounter
from app.models.user import User
from app.schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PlanOut,
    PortalSessionRequest,
    PortalSessionResponse,
    SubscriptionOut,
    UsageOut,
)
from app.services import billing
from app.services.authz import require_membership, require_org_manager
from app.services.stripe_billing import StripeBillingClient
from app.services.webhook_handlers import handle_stripe_event

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
async def list_plans() -> list[dict]:
    """Public: the pricing page needs this before a user has even
    registered. No quota or billing data here, just the static registry
    from app/core/plans.py."""
    return [
        {
            "plan_id": p.plan_id,
            "name": p.name,
            "monthly_price_gbp": p.monthly_price_gbp,
            "max_analyses_per_month": p.max_analyses_per_month,
            "max_upload_size_bytes": p.max_upload_size_bytes,
            "max_saved_datasets": p.max_saved_datasets,
            "max_team_members": p.max_team_members,
            "self_serve": p.stripe_price_id_monthly is not None or p.plan_id == "free",
        }
        for p in PLANS.values()
    ]


async def _resolve_subscription_read(
    organization_id: str | None, current_user: User, db: AsyncSession
) -> Subscription:
    if organization_id:
        await require_membership(db, current_user.id, organization_id)
        return await billing.get_or_create_subscription_for_organization(db, organization_id)
    return await billing.get_or_create_subscription_for_user(db, current_user.id)


async def _resolve_subscription_write(
    organization_id: str | None, current_user: User, db: AsyncSession
) -> Subscription:
    if organization_id:
        await require_org_manager(db, current_user.id, organization_id)
        return await billing.get_or_create_subscription_for_organization(db, organization_id)
    return await billing.get_or_create_subscription_for_user(db, current_user.id)


async def _to_subscription_out(db: AsyncSession, subscription: Subscription) -> SubscriptionOut:
    plan = billing.plan_for(subscription)
    period_key = billing.current_period_key()
    result = await db.execute(
        select(UsageCounter).where(
            UsageCounter.subscription_id == subscription.id, UsageCounter.period_key == period_key
        )
    )
    counter = result.scalar_one_or_none()
    analyses_used = counter.analyses_count if counter else 0

    return SubscriptionOut(
        id=subscription.id,
        owner_user_id=subscription.owner_user_id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        billing_period=subscription.billing_period,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        usage=UsageOut(
            period_key=period_key,
            analyses_used=analyses_used,
            analyses_limit=plan.max_analyses_per_month,
            resets_at=billing.next_usage_reset(subscription, period_key),
        ),
    )


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    organization_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    subscription = await _resolve_subscription_read(organization_id, current_user, db)
    return await _to_subscription_out(db, subscription)


async def _require_checkout_access(
    payload: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    """Resolves the target subscription and checks the caller is allowed
    to manage its billing — declared as its own dependency, and listed
    BEFORE get_stripe_client_dep in the endpoints below, so an
    unauthorized caller gets 403, not a 503 revealing "Stripe isn't
    configured" before authorization was even checked. Same fix, same
    reason, as app/api/v1/routers/ai_analyst.py's _require_askable_table."""
    return await _resolve_subscription_write(payload.organization_id, current_user, db)


async def _require_portal_access(
    payload: PortalSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    return await _resolve_subscription_write(payload.organization_id, current_user, db)


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    subscription: Subscription = Depends(_require_checkout_access),
    current_user: User = Depends(get_current_user),
    stripe_client: StripeBillingClient = Depends(get_stripe_client_dep),
) -> CheckoutSessionResponse:
    try:
        plan = get_plan(payload.plan_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    price_id = plan.stripe_price_id_monthly if payload.billing_period == "monthly" else plan.stripe_price_id_annual
    if not price_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The {plan.name} plan has no self-serve {payload.billing_period} price configured "
            "(set STRIPE_PRICE_ID_... env vars once the Stripe product catalog exists), or it's "
            "Enterprise/contact-sales only.",
        )

    settings = get_settings()
    result = stripe_client.create_checkout_session(
        price_id=price_id,
        customer_email=current_user.email,
        client_reference_id=subscription.id,
        success_url=f"{settings.frontend_base_url}/dashboard?checkout=success",
        cancel_url=f"{settings.frontend_base_url}/pricing?checkout=cancelled",
        existing_stripe_customer_id=subscription.stripe_customer_id,
    )
    return CheckoutSessionResponse(checkout_url=result.checkout_url)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    payload: PortalSessionRequest,
    subscription: Subscription = Depends(_require_portal_access),
    stripe_client: StripeBillingClient = Depends(get_stripe_client_dep),
) -> PortalSessionResponse:
    if not subscription.stripe_customer_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No billing account yet — subscribe to a paid plan first via /billing/checkout-session.",
        )

    settings = get_settings()
    result = stripe_client.create_billing_portal_session(
        stripe_customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.frontend_base_url}/dashboard",
    )
    return PortalSessionResponse(portal_url=result.portal_url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeBillingClient = Depends(get_stripe_client_dep),
) -> dict:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "STRIPE_WEBHOOK_SECRET not configured.")

    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_client.construct_webhook_event(payload, signature_header, settings.stripe_webhook_secret)
    except Exception as exc:  # stripe raises its own SignatureVerificationError / ValueError
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid webhook signature: {exc}") from exc

    event_dict = event if isinstance(event, dict) else event.to_dict()
    handled = await handle_stripe_event(db, event_dict)
    return {"received": True, "handled": handled}
