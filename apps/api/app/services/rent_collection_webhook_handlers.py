"""Business logic reacting to a verified Stripe Connect webhook event.
Deliberately separate from app/services/webhook_handlers.py (the
existing billing webhook dispatch): Connect events arrive on a
different endpoint with a different signing secret, and critically,
the handlers here are NOT naturally idempotent the way the existing
billing handlers are (overwrite-style updates). Dedup happens one layer
up, in app/api/v1/routers/rent_collection.py's webhook endpoint, via
app/models/rent_collection.py's ProcessedWebhookEvent — this module
assumes it is only ever called once per real event."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.resolvers import get_tenancy_chain_or_404
from app.models.property import LedgerEntryType, RentLedgerEntry
from app.models.rent_collection import ConnectAccountStatus, RentPaymentRequest, RentPaymentRequestStatus, WorkspaceStripeAccount
from app.services.audit import record_audit_event


async def _get_payment_request_by_session(db: AsyncSession, session_id: str) -> RentPaymentRequest | None:
    result = await db.execute(
        select(RentPaymentRequest).where(RentPaymentRequest.stripe_checkout_session_id == session_id)
    )
    return result.scalar_one_or_none()


async def handle_checkout_session_completed(db: AsyncSession, event_object: dict[str, Any]) -> None:
    session_id = event_object.get("id")
    if not session_id:
        return
    payment_request = await _get_payment_request_by_session(db, session_id)
    if payment_request is None:
        return  # not one of ours
    if payment_request.status == RentPaymentRequestStatus.PAID.value:
        return  # already credited — belt-and-suspenders alongside the router-level event dedup

    payment_request.stripe_payment_intent_id = event_object.get("payment_intent")
    payment_request.status = RentPaymentRequestStatus.PAID.value

    ledger_entry = RentLedgerEntry(
        tenancy_id=payment_request.tenancy_id,
        entry_type=LedgerEntryType.PAYMENT.value,
        amount_gbp=payment_request.amount_gbp,
        entry_date=date.today(),
        description=f"Stripe payment received (Checkout Session {session_id})",
        created_by_user_id=None,  # webhook-triggered, no human actor
    )
    db.add(ledger_entry)
    await db.flush()
    payment_request.resulting_ledger_entry_id = ledger_entry.id

    _, _, workspace = await get_tenancy_chain_or_404(db, payment_request.tenancy_id)
    await record_audit_event(
        db,
        event_type="rent_collection.payment_received",
        actor_user_id=None,
        workspace_id=workspace.id,
        metadata={
            "payment_request_id": payment_request.id,
            "ledger_entry_id": ledger_entry.id,
            "amount_gbp": float(payment_request.amount_gbp),
        },
    )
    await db.commit()


async def handle_checkout_session_expired(db: AsyncSession, event_object: dict[str, Any]) -> None:
    session_id = event_object.get("id")
    if not session_id:
        return
    payment_request = await _get_payment_request_by_session(db, session_id)
    if payment_request is None or payment_request.status != RentPaymentRequestStatus.PENDING.value:
        return
    payment_request.status = RentPaymentRequestStatus.EXPIRED.value
    await db.commit()


async def handle_account_updated(db: AsyncSession, event_object: dict[str, Any]) -> None:
    stripe_account_id = event_object.get("id")
    if not stripe_account_id:
        return
    result = await db.execute(
        select(WorkspaceStripeAccount).where(WorkspaceStripeAccount.stripe_account_id == stripe_account_id)
    )
    account_row = result.scalar_one_or_none()
    if account_row is None:
        return

    was_active = account_row.charges_enabled
    account_row.charges_enabled = bool(event_object.get("charges_enabled", False))
    account_row.payouts_enabled = bool(event_object.get("payouts_enabled", False))

    if account_row.charges_enabled:
        account_row.status = ConnectAccountStatus.ACTIVE.value
        if not was_active:
            await record_audit_event(
                db,
                event_type="rent_collection.connect_account_activated",
                actor_user_id=None,
                workspace_id=account_row.workspace_id,
                metadata={"stripe_account_id": stripe_account_id},
            )
    elif event_object.get("requirements", {}).get("disabled_reason"):
        account_row.status = ConnectAccountStatus.RESTRICTED.value

    await db.commit()


_HANDLERS = {
    "checkout.session.completed": handle_checkout_session_completed,
    "checkout.session.expired": handle_checkout_session_expired,
    "account.updated": handle_account_updated,
}


async def handle_rent_collection_event(db: AsyncSession, event: dict[str, Any]) -> bool:
    handler = _HANDLERS.get(event.get("type", ""))
    if handler is None:
        return False
    await handler(db, event["data"]["object"])
    return True
