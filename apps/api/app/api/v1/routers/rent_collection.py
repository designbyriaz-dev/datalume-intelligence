import html
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_email_sender_optional_dep, get_stripe_connect_client_dep
from app.api.resolvers import get_ledger_entry_chain_or_404, get_tenancy_chain_or_404, get_workspace_or_404
from app.core.config import get_settings
from app.db.session import get_db
from app.models.property import LedgerEntryType, Property, RentLedgerEntry, Tenancy
from app.models.rent_collection import ProcessedWebhookEvent, RentPaymentRequest, WorkspaceStripeAccount
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.rent_collection import ConnectAccountOut, ConnectOnboardingLinkOut, PaymentRequestOut
from app.services.audit import record_audit_event
from app.services.authz import require_workspace_access, require_workspace_delete_access, require_workspace_write_access
from app.services.email import EmailMessage, EmailSender
from app.services.email_templates import branded_cta_email_html
from app.services.rent_collection_webhook_handlers import handle_rent_collection_event
from app.services.stripe_connect import StripeConnectClient

router = APIRouter(tags=["rent-collection"])


async def _get_connect_account_or_404(db: AsyncSession, workspace_id: str) -> WorkspaceStripeAccount:
    result = await db.execute(
        select(WorkspaceStripeAccount).where(WorkspaceStripeAccount.workspace_id == workspace_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No Stripe Connect account for this workspace yet — connect one first."
        )
    return account


async def _require_connect_account_access(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deliberately require_workspace_delete_access, not write — see
    docs/CHECKLIST.md's Rent Collection v1 plan for why: connecting
    where real tenant money lands is account-level and financially
    sensitive, closer in blast radius to deleting the workspace than to
    recording a ledger entry. Declared as its own dependency and listed
    BEFORE get_stripe_connect_client_dep below, so an unauthorized
    caller gets 403, not a 503 revealing "Stripe isn't configured" —
    same fix as app/api/v1/routers/billing.py's _require_checkout_access."""
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_delete_access(db, current_user.id, workspace)


async def _require_payment_request_access(
    ledger_entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[RentLedgerEntry, Tenancy, Property, Workspace]:
    """Write-level, not delete-level — requesting payment for an
    already-authorized charge doesn't touch *where* money goes (that's
    locked behind _require_connect_account_access above), only *that*
    a specific charge gets a payment link. Same ordering-fix reasoning
    as _require_connect_account_access: declared before
    get_stripe_connect_client_dep in the endpoint below."""
    chain = await get_ledger_entry_chain_or_404(db, ledger_entry_id)
    _, _, _, workspace = chain
    await require_workspace_write_access(db, current_user.id, workspace)
    return chain


@router.post(
    "/workspaces/{workspace_id}/rent-collection/connect-account",
    response_model=ConnectOnboardingLinkOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_connect_account(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(_require_connect_account_access),
    stripe_connect: StripeConnectClient = Depends(get_stripe_connect_client_dep),
) -> ConnectOnboardingLinkOut:
    settings = get_settings()
    result = await db.execute(
        select(WorkspaceStripeAccount).where(WorkspaceStripeAccount.workspace_id == workspace_id)
    )
    account_row = result.scalar_one_or_none()

    if account_row is None:
        stripe_account_id = stripe_connect.create_connected_account(workspace_id=workspace_id)
        account_row = WorkspaceStripeAccount(
            workspace_id=workspace_id,
            stripe_account_id=stripe_account_id,
            created_by_user_id=current_user.id,
        )
        db.add(account_row)
        await record_audit_event(
            db,
            event_type="rent_collection.connect_account_created",
            actor_user_id=current_user.id,
            workspace_id=workspace_id,
            metadata={"stripe_account_id": stripe_account_id},
        )
        await db.commit()

    link = stripe_connect.create_onboarding_link(
        stripe_account_id=account_row.stripe_account_id,
        refresh_url=f"{settings.frontend_base_url}/dashboard/workspaces/{workspace_id}?connect=refresh",
        return_url=f"{settings.frontend_base_url}/dashboard/workspaces/{workspace_id}?connect=return",
    )
    return ConnectOnboardingLinkOut(onboarding_url=link.onboarding_url)


@router.post(
    "/workspaces/{workspace_id}/rent-collection/connect-account/refresh-link",
    response_model=ConnectOnboardingLinkOut,
)
async def refresh_connect_onboarding_link(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(_require_connect_account_access),
    stripe_connect: StripeConnectClient = Depends(get_stripe_connect_client_dep),
) -> ConnectOnboardingLinkOut:
    settings = get_settings()
    account_row = await _get_connect_account_or_404(db, workspace_id)
    link = stripe_connect.create_onboarding_link(
        stripe_account_id=account_row.stripe_account_id,
        refresh_url=f"{settings.frontend_base_url}/dashboard/workspaces/{workspace_id}?connect=refresh",
        return_url=f"{settings.frontend_base_url}/dashboard/workspaces/{workspace_id}?connect=return",
    )
    return ConnectOnboardingLinkOut(onboarding_url=link.onboarding_url)


@router.get(
    "/workspaces/{workspace_id}/rent-collection/connect-account",
    response_model=ConnectAccountOut,
)
async def get_connect_account(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStripeAccount:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)
    return await _get_connect_account_or_404(db, workspace_id)


@router.post(
    "/ledger-entries/{ledger_entry_id}/request-payment",
    response_model=PaymentRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_payment(
    ledger_entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    access: tuple[RentLedgerEntry, Tenancy, Property, Workspace] = Depends(_require_payment_request_access),
    stripe_connect: StripeConnectClient = Depends(get_stripe_connect_client_dep),
    email_sender: EmailSender | None = Depends(get_email_sender_optional_dep),
) -> RentPaymentRequest:
    entry, tenancy, property_, workspace = access

    if entry.entry_type != LedgerEntryType.CHARGE.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment can only be requested for a charge entry.")
    if not tenancy.tenant_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This tenancy has no tenant email on file.")

    account_row = await _get_connect_account_or_404(db, workspace.id)
    if not account_row.charges_enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This workspace's Stripe account isn't ready to accept payments yet."
        )

    settings = get_settings()
    result = stripe_connect.create_checkout_session_for_charge(
        stripe_account_id=account_row.stripe_account_id,
        amount_gbp=float(entry.amount_gbp),
        description=f"Rent - {property_.address_line1}",
        tenant_email=tenancy.tenant_email,
        success_url=f"{settings.frontend_base_url}/pay/success",
        cancel_url=f"{settings.frontend_base_url}/pay/cancelled",
        metadata={"ledger_entry_id": entry.id, "tenancy_id": tenancy.id},
    )

    payment_request = RentPaymentRequest(
        ledger_entry_id=entry.id,
        tenancy_id=tenancy.id,
        stripe_account_id=account_row.stripe_account_id,
        stripe_checkout_session_id=result.checkout_session_id,
        amount_gbp=entry.amount_gbp,
        tenant_email=tenancy.tenant_email,
        checkout_url=result.checkout_url,
        created_by_user_id=current_user.id,
    )
    db.add(payment_request)
    await record_audit_event(
        db,
        event_type="rent_collection.payment_requested",
        actor_user_id=current_user.id,
        workspace_id=workspace.id,
        metadata={"ledger_entry_id": entry.id, "amount_gbp": float(entry.amount_gbp)},
    )
    await db.commit()
    await db.refresh(payment_request)

    if email_sender:  # best-effort — same optional-dep convention as registration emails
        email_sender.send(
            EmailMessage(
                to=tenancy.tenant_email,
                subject=f"Rent payment requested - £{entry.amount_gbp:.2f}",
                text_body=f"A rent payment has been requested. Pay here: {result.checkout_url}",
                html_body=branded_cta_email_html(
                    heading="A rent payment has been requested",
                    intro_html=(
                        f"<strong>{html.escape(property_.address_line1)}</strong> "
                        f"&mdash; £{entry.amount_gbp:.2f} due."
                    ),
                    button_label="Pay now",
                    button_url=result.checkout_url,
                    footer_note="If you weren't expecting this, contact your landlord or agent directly.",
                ),
            )
        )
    return payment_request


@router.get("/tenancies/{tenancy_id}/payment-requests", response_model=list[PaymentRequestOut])
async def list_payment_requests(
    tenancy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RentPaymentRequest]:
    tenancy, property_, workspace = await get_tenancy_chain_or_404(db, tenancy_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(RentPaymentRequest)
        .where(RentPaymentRequest.tenancy_id == tenancy_id)
        .order_by(RentPaymentRequest.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/rent-collection/webhook")
async def rent_collection_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_connect: StripeConnectClient = Depends(get_stripe_connect_client_dep),
) -> dict:
    settings = get_settings()
    if not settings.stripe_connect_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "STRIPE_CONNECT_WEBHOOK_SECRET not configured.")

    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe_connect.construct_webhook_event(payload, signature_header, settings.stripe_connect_webhook_secret)
    except Exception as exc:  # stripe raises its own SignatureVerificationError / ValueError
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid webhook signature: {exc}") from exc

    event_dict = event if isinstance(event, dict) else event.to_dict()
    event_id = event_dict.get("id")
    if not event_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Event missing id.")

    # Idempotency: insert-or-detect-duplicate BEFORE dispatching. The
    # UNIQUE constraint on stripe_event_id makes the race-safe case (two
    # redeliveries arriving concurrently) fail on the second INSERT
    # rather than both racing past a SELECT-then-INSERT check. See
    # app/models/rent_collection.py's ProcessedWebhookEvent docstring.
    try:
        db.add(
            ProcessedWebhookEvent(
                stripe_event_id=event_id,
                event_type=event_dict.get("type", ""),
                processed_at=datetime.now(timezone.utc),
            )
        )
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"received": True, "handled": False, "duplicate": True}

    handled = await handle_rent_collection_event(db, event_dict)
    await db.commit()
    return {"received": True, "handled": handled}
