"""Tests for Rent Collection v1 (Stripe Connect, pay-by-link) — see
docs/CHECKLIST.md's "Rent Collection v1" section for the full plan.

Same honesty boundary as tests/test_billing_webhook.py /
app/services/stripe_connect.py's own docstring: create_connected_account,
create_onboarding_link, and create_checkout_session_for_charge are never
called against a real Stripe account here — only the
503-when-disabled/unconfigured boundary and the webhook business logic
(hand-built, HMAC-signed payloads, exactly like test_billing_webhook.py)
are exercised. Live account creation, onboarding, and a real Checkout
payment are the account holder's own step, against their own approved
Stripe Connect platform application.
"""

import hashlib
import hmac
import json
import os
import time

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.property import RentLedgerEntry
from app.models.rent_collection import ProcessedWebhookEvent, RentPaymentRequest, WorkspaceStripeAccount

WEBHOOK_SECRET = "whsec_test_connect_secret_for_local_testing_only"


def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


async def _with_rent_collection_configured(client: AsyncClient, body_fn):
    """Mirrors test_billing_webhook.py's _with_stripe_configured. Sets
    rent_collection_enabled=True plus fake-but-present Stripe keys —
    webhook signature verification is pure local HMAC and never calls
    Stripe's API."""
    get_settings.cache_clear()
    os.environ["RENT_COLLECTION_ENABLED"] = "true"
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake_for_connect_webhook_signature_testing"
    os.environ["STRIPE_CONNECT_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    try:
        await body_fn()
    finally:
        del os.environ["RENT_COLLECTION_ENABLED"]
        del os.environ["STRIPE_SECRET_KEY"]
        del os.environ["STRIPE_CONNECT_WEBHOOK_SECRET"]
        get_settings.cache_clear()


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup_charge_entry(
    client: AsyncClient, token: str, *, organization_id: str | None = None, entry_type: str = "charge"
) -> tuple[str, str, str]:
    """Creates a workspace (personal, or under organization_id if given),
    a property, a tenancy with a tenant_email, and one ledger entry.
    Returns (workspace_id, tenancy_id, ledger_entry_id)."""
    ws_payload = {"name": "Rent Collection Test WS", "industry": "general"}
    if organization_id:
        ws_payload["organization_id"] = organization_id
    ws_resp = await client.post("/api/v1/workspaces", json=ws_payload, headers=_auth(token))
    workspace_id = ws_resp.json()["id"]

    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Test Street", "city": "London", "postcode": "E1 6AN"},
        headers=_auth(token),
    )
    property_id = prop_resp.json()["id"]

    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={
            "tenant_name": "Test Tenant",
            "tenant_email": "tenant@example.com",
            "rent_amount_gbp": 1200.00,
            "rent_frequency": "monthly",
            "start_date": "2026-01-01",
        },
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]

    entry_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": entry_type, "amount_gbp": 1200.00, "entry_date": "2026-01-01"},
        headers=_auth(token),
    )
    ledger_entry_id = entry_resp.json()["id"]

    return workspace_id, tenancy_id, ledger_entry_id


async def test_request_payment_returns_503_when_rent_collection_disabled(client: AsyncClient) -> None:
    """Default-off boundary — no env changes at all."""
    token = await _register_and_login(client, "rc_disabled@example.com")
    _, _, ledger_entry_id = await _setup_charge_entry(client, token)

    resp = await client.post(f"/api/v1/ledger-entries/{ledger_entry_id}/request-payment", headers=_auth(token))
    assert resp.status_code == 503


async def test_connect_account_returns_503_when_rent_collection_disabled(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rc_disabled2@example.com")
    workspace_id, _, _ = await _setup_charge_entry(client, token)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/rent-collection/connect-account", headers=_auth(token)
    )
    assert resp.status_code == 503


async def test_analyst_can_request_payment_but_not_connect_account(client: AsyncClient) -> None:
    """Security regression test, same shape as test_billing.py's
    test_non_manager_gets_403_not_503_on_checkout: authorization must be
    checked before the "is rent collection configured" dependency
    resolves. Rent Collection is NOT configured in this test
    environment — if the ordering were wrong, the Analyst would get 503
    (config detail) instead of 403 (denied) on the delete-level action,
    and the write-level action would wrongly 403 instead of reaching
    503. Proves both authz levels from app/api/v1/routers/
    rent_collection.py in one test: an Analyst (WORKSPACE_WRITE_ROLES)
    can request payment but cannot connect a bank account
    (ORG_MANAGE_ROLES-only)."""
    owner_token = await _register_and_login(client, "rc_owner@example.com")
    analyst_email = "rc_analyst@example.com"
    analyst_token = await _register_and_login(client, analyst_email)

    org_resp = await client.post("/api/v1/organizations", json={"name": "RC Org"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": analyst_email, "role": "analyst"},
        headers=_auth(owner_token),
    )

    workspace_id, _, ledger_entry_id = await _setup_charge_entry(
        client, owner_token, organization_id=org_id
    )

    write_level = await client.post(
        f"/api/v1/ledger-entries/{ledger_entry_id}/request-payment", headers=_auth(analyst_token)
    )
    assert write_level.status_code == 503  # authorized, reaches the "not configured" check

    delete_level = await client.post(
        f"/api/v1/workspaces/{workspace_id}/rent-collection/connect-account", headers=_auth(analyst_token)
    )
    assert delete_level.status_code == 403  # NOT authorized — blocked before config is even checked

    owner_delete_level = await client.post(
        f"/api/v1/workspaces/{workspace_id}/rent-collection/connect-account", headers=_auth(owner_token)
    )
    assert owner_delete_level.status_code == 503  # the org owner IS authorized for this


async def test_request_payment_rejects_non_charge_entry_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rc_nonchange@example.com")
    _, _, ledger_entry_id = await _setup_charge_entry(client, token, entry_type="adjustment")

    async def run():
        resp = await client.post(f"/api/v1/ledger-entries/{ledger_entry_id}/request-payment", headers=_auth(token))
        assert resp.status_code == 400

    await _with_rent_collection_configured(client, run)


async def test_webhook_rejects_invalid_connect_signature(client: AsyncClient) -> None:
    async def run():
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
        resp = await client.post(
            "/api/v1/rent-collection/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    await _with_rent_collection_configured(client, run)


async def test_duplicate_webhook_delivery_does_not_double_credit_ledger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The key regression test: Stripe explicitly documents
    at-least-once webhook delivery, and "create a ledger payment entry"
    is NOT naturally idempotent (unlike the existing billing webhook
    handlers) — this proves app/models/rent_collection.py's
    ProcessedWebhookEvent actually prevents a double credit."""
    token = await _register_and_login(client, "rc_dedup@example.com")
    _, tenancy_id, ledger_entry_id = await _setup_charge_entry(client, token)

    # Seed a RentPaymentRequest directly — this test is about webhook
    # dedup, not real onboarding (the checkout.session.completed
    # handler only looks up RentPaymentRequest by session id, not
    # WorkspaceStripeAccount, so no connect account row is needed here).
    session_id = "cs_test_dedup_session_123"

    payment_request = RentPaymentRequest(
        ledger_entry_id=ledger_entry_id,
        tenancy_id=tenancy_id,
        stripe_account_id="acct_test_dedup",
        stripe_checkout_session_id=session_id,
        amount_gbp=1200.00,
        tenant_email="tenant@example.com",
        checkout_url="https://checkout.stripe.com/test",
    )
    db_session.add(payment_request)
    await db_session.commit()

    payload = json.dumps(
        {
            "id": "evt_test_dedup_1",
            "type": "checkout.session.completed",
            "data": {"object": {"id": session_id, "payment_intent": "pi_test_dedup"}},
        }
    ).encode()

    async def first_delivery():
        resp = await client.post(
            "/api/v1/rent-collection/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["handled"] is True

    await _with_rent_collection_configured(client, first_delivery)

    async def second_delivery():
        resp = await client.post(
            "/api/v1/rent-collection/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["duplicate"] is True

    await _with_rent_collection_configured(client, second_delivery)

    entries = (
        (
            await db_session.execute(
                select(RentLedgerEntry).where(
                    RentLedgerEntry.tenancy_id == tenancy_id, RentLedgerEntry.entry_type == "payment"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1  # exactly one — not zero, not two

    events = (await db_session.execute(select(ProcessedWebhookEvent))).scalars().all()
    assert len(events) == 1  # the dedup table itself only has the one event row


async def test_account_updated_webhook_activates_connect_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "rc_activate@example.com")
    workspace_id, _, _ = await _setup_charge_entry(client, token)

    account_row = WorkspaceStripeAccount(workspace_id=workspace_id, stripe_account_id="acct_test_activate")
    db_session.add(account_row)
    await db_session.commit()

    payload = json.dumps(
        {
            "id": "evt_test_activate_1",
            "type": "account.updated",
            "data": {"object": {"id": "acct_test_activate", "charges_enabled": True, "payouts_enabled": True}},
        }
    ).encode()

    async def run():
        resp = await client.post(
            "/api/v1/rent-collection/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["handled"] is True

    await _with_rent_collection_configured(client, run)

    await db_session.refresh(account_row)
    assert account_row.charges_enabled is True
    assert account_row.status == "active"


async def test_checkout_session_expired_marks_payment_request_expired_not_ledger_entry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "rc_expired@example.com")
    _, tenancy_id, ledger_entry_id = await _setup_charge_entry(client, token)

    session_id = "cs_test_expired_session_123"
    payment_request = RentPaymentRequest(
        ledger_entry_id=ledger_entry_id,
        tenancy_id=tenancy_id,
        stripe_account_id="acct_test_expired",
        stripe_checkout_session_id=session_id,
        amount_gbp=1200.00,
        tenant_email="tenant@example.com",
        checkout_url="https://checkout.stripe.com/test",
    )
    db_session.add(payment_request)
    await db_session.commit()

    payload = json.dumps(
        {"id": "evt_test_expired_1", "type": "checkout.session.expired", "data": {"object": {"id": session_id}}}
    ).encode()

    async def run():
        resp = await client.post(
            "/api/v1/rent-collection/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["handled"] is True

    await _with_rent_collection_configured(client, run)

    await db_session.refresh(payment_request)
    assert payment_request.status == "expired"

    entries = (
        (await db_session.execute(select(RentLedgerEntry).where(RentLedgerEntry.tenancy_id == tenancy_id)))
        .scalars()
        .all()
    )
    assert all(e.entry_type != "payment" for e in entries)  # no payment entry was created
