"""Tests the Stripe webhook endpoint end-to-end, including real HMAC
signature verification — without ever calling Stripe. We know the
webhook secret (we set it ourselves via env var) and Stripe's signing
scheme is public: `t=<unix_ts>,v1=<hex hmac_sha256(f"{ts}.{payload}", secret)>`.
This exercises the exact same verification code path
(stripe.Webhook.construct_event) that a real Stripe-sent webhook would
hit — only the "is this truly from Stripe's servers" trust question is
untested, not the cryptographic verification itself or the business
logic that reacts to the event.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.billing import Subscription

WEBHOOK_SECRET = "whsec_test_secret_for_local_testing_only"


def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


async def _with_stripe_configured(client: AsyncClient, body_fn):
    """Sets fake-but-present Stripe env vars for the duration of body_fn.
    STRIPE_SECRET_KEY doesn't need to be a real key — constructing and
    verifying a webhook signature is a pure local HMAC operation that
    never calls Stripe's API."""
    get_settings.cache_clear()
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake_for_webhook_signature_testing"
    os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    try:
        await body_fn()
    finally:
        del os.environ["STRIPE_SECRET_KEY"]
        del os.environ["STRIPE_WEBHOOK_SECRET"]
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


async def test_webhook_rejects_invalid_signature(client: AsyncClient) -> None:
    async def run():
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    await _with_stripe_configured(client, run)


async def test_webhook_checkout_completed_activates_subscription(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    subscription_id = sub_resp.json()["id"]

    async def run():
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": subscription_id,
                        "customer": "cus_test123",
                        "subscription": "sub_test123",
                    }
                },
            }
        ).encode()
        signature = _sign(payload, WEBHOOK_SECRET)
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": signature, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["handled"] is True

    await _with_stripe_configured(client, run)

    sub_resp2 = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert sub_resp2.json()["status"] == "active"


async def test_webhook_subscription_updated_changes_plan_and_status(client: AsyncClient) -> None:
    get_settings.cache_clear()
    os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"] = "price_professional_monthly_test"
    get_settings.cache_clear()
    try:
        # Reload the plan registry's price-id lookup by re-importing is
        # unnecessary — PLANS is built at import time from os.environ, so
        # for this test we patch the registry entry directly instead.
        from app.core import plans as plans_module

        original = plans_module.PLANS["professional"]
        patched = plans_module.PlanLimits(
            **{**original.__dict__, "stripe_price_id_monthly": "price_professional_monthly_test"}
        )
        plans_module.PLANS["professional"] = patched
        try:
            token = await _register_and_login(client, "owner2@example.com")
            sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
            subscription_id = sub_resp.json()["id"]

            # First attach a Stripe customer/subscription via checkout.session.completed.
            async def activate():
                payload = json.dumps(
                    {
                        "type": "checkout.session.completed",
                        "data": {
                            "object": {
                                "client_reference_id": subscription_id,
                                "customer": "cus_test456",
                                "subscription": "sub_test456",
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, activate)

            async def update():
                payload = json.dumps(
                    {
                        "type": "customer.subscription.updated",
                        "data": {
                            "object": {
                                "id": "sub_test456",
                                "customer": "cus_test456",
                                "status": "active",
                                "current_period_end": 1999999999,
                                "cancel_at_period_end": False,
                                "items": {"data": [{"price": {"id": "price_professional_monthly_test"}}]},
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, update)

            final = await client.get("/api/v1/billing/subscription", headers=_auth(token))
            body = final.json()
            assert body["plan_id"] == "professional"
            assert body["billing_period"] == "monthly"
            assert body["usage"]["analyses_limit"] == 100  # professional plan's limit, not free's
        finally:
            plans_module.PLANS["professional"] = original
    finally:
        del os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"]
        get_settings.cache_clear()


async def test_webhook_subscription_updated_audit_logs_personal_plan_change(client: AsyncClient) -> None:
    """The gap this closes: a *personal* (non-org) subscription's plan
    change previously wasn't audit-logged at all — only org subscriptions
    were, since the handler used to skip the call entirely when
    subscription.organization_id was unset. Proves the fix end-to-end:
    the resulting AuditLog row is actually retrievable through the real
    GET /users/me/audit-log endpoint, not just present in the database."""
    get_settings.cache_clear()
    os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"] = "price_professional_monthly_personal_test"
    get_settings.cache_clear()
    try:
        from app.core import plans as plans_module

        original = plans_module.PLANS["professional"]
        patched = plans_module.PlanLimits(
            **{**original.__dict__, "stripe_price_id_monthly": "price_professional_monthly_personal_test"}
        )
        plans_module.PLANS["professional"] = patched
        try:
            token = await _register_and_login(client, "personalplanchange@example.com")
            sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
            subscription_id = sub_resp.json()["id"]

            async def activate():
                payload = json.dumps(
                    {
                        "type": "checkout.session.completed",
                        "data": {
                            "object": {
                                "client_reference_id": subscription_id,
                                "customer": "cus_personal_test",
                                "subscription": "sub_personal_test",
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, activate)

            async def update():
                payload = json.dumps(
                    {
                        "type": "customer.subscription.updated",
                        "data": {
                            "object": {
                                "id": "sub_personal_test",
                                "customer": "cus_personal_test",
                                "status": "active",
                                "current_period_end": 1999999999,
                                "cancel_at_period_end": False,
                                "items": {
                                    "data": [{"price": {"id": "price_professional_monthly_personal_test"}}]
                                },
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, update)

            audit_resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
            assert audit_resp.status_code == 200
            events = [e for e in audit_resp.json() if e["event_type"] == "billing.plan_changed"]
            assert len(events) == 1
            assert events[0]["organization_id"] is None
            assert events[0]["event_metadata"]["old_plan_id"] == "free"
            assert events[0]["event_metadata"]["new_plan_id"] == "professional"
        finally:
            plans_module.PLANS["professional"] = original
    finally:
        del os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"]
        get_settings.cache_clear()


async def test_webhook_subscription_deleted_downgrades_to_free(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    subscription_id = sub_resp.json()["id"]

    async def activate():
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": subscription_id,
                        "customer": "cus_test789",
                        "subscription": "sub_test789",
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, activate)

    async def delete():
        payload = json.dumps(
            {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_test789"}}}
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, delete)

    final = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    body = final.json()
    assert body["plan_id"] == "free"
    assert body["status"] == "canceled"

    audit_resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
    events = [e for e in audit_resp.json() if e["event_type"] == "billing.subscription_canceled"]
    assert len(events) == 1
    assert events[0]["organization_id"] is None


async def test_webhook_subscription_deleted_audit_logs_the_plan_it_was_canceled_from(
    client: AsyncClient,
) -> None:
    """Cancellation wasn't audit-logged at all before this (not even
    partially, unlike the plan-change gap fixed just above it) — this
    specifically proves previous_plan_id is captured *before* the
    handler resets plan_id to "free", by canceling from a paid plan
    rather than from free (where a before/after mixup would be
    invisible)."""
    get_settings.cache_clear()
    os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"] = "price_professional_monthly_cancel_test"
    get_settings.cache_clear()
    try:
        from app.core import plans as plans_module

        original = plans_module.PLANS["professional"]
        patched = plans_module.PlanLimits(
            **{**original.__dict__, "stripe_price_id_monthly": "price_professional_monthly_cancel_test"}
        )
        plans_module.PLANS["professional"] = patched
        try:
            token = await _register_and_login(client, "cancelfrompaid@example.com")
            sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
            subscription_id = sub_resp.json()["id"]

            async def activate():
                payload = json.dumps(
                    {
                        "type": "checkout.session.completed",
                        "data": {
                            "object": {
                                "client_reference_id": subscription_id,
                                "customer": "cus_cancel_test",
                                "subscription": "sub_cancel_test",
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, activate)

            async def upgrade():
                payload = json.dumps(
                    {
                        "type": "customer.subscription.updated",
                        "data": {
                            "object": {
                                "id": "sub_cancel_test",
                                "customer": "cus_cancel_test",
                                "status": "active",
                                "current_period_end": 1999999999,
                                "cancel_at_period_end": False,
                                "items": {"data": [{"price": {"id": "price_professional_monthly_cancel_test"}}]},
                            }
                        },
                    }
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, upgrade)

            pre_cancel = await client.get("/api/v1/billing/subscription", headers=_auth(token))
            assert pre_cancel.json()["plan_id"] == "professional"

            async def delete():
                payload = json.dumps(
                    {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_cancel_test"}}}
                ).encode()
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
                )
                assert resp.status_code == 200

            await _with_stripe_configured(client, delete)

            audit_resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
            events = [e for e in audit_resp.json() if e["event_type"] == "billing.subscription_canceled"]
            assert len(events) == 1
            assert events[0]["event_metadata"]["previous_plan_id"] == "professional"
        finally:
            plans_module.PLANS["professional"] = original
    finally:
        del os.environ["STRIPE_PRICE_ID_PROFESSIONAL_MONTHLY"]
        get_settings.cache_clear()


async def test_webhook_invoice_payment_failed_marks_past_due_and_starts_grace_period(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "pastdue1@example.com")
    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    subscription_id = sub_resp.json()["id"]

    async def activate():
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": subscription_id,
                        "customer": "cus_pastdue1",
                        "subscription": "sub_pastdue1",
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, activate)

    before = dt.datetime.now(dt.timezone.utc)

    async def fail():
        payload = json.dumps(
            {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_pastdue1"}}}
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, fail)

    final = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    body = final.json()
    assert body["status"] == "past_due"
    assert body["past_due_since"] is not None

    # Real timestamp from "now", not a placeholder — checked against the
    # DB's own value directly (not the API's JSON, which round-trips
    # through SQLite's naive-datetime serialization — see
    # docs/CHECKLIST.md's "Post-Phase-7: verify the test suite against
    # real Postgres" section) using the same tzinfo-matching idiom
    # established there and in app/services/email_tokens.py/sso.py.
    subscription = await db_session.get(Subscription, subscription_id)
    assert subscription.past_due_since >= before.replace(tzinfo=subscription.past_due_since.tzinfo) - dt.timedelta(
        seconds=5
    )

    # The API's own computed field: exactly 7 days after past_due_since.
    from app.services.dunning import DEFAULT_GRACE_PERIOD

    assert body["downgrade_scheduled_for"] is not None
    expected = subscription.past_due_since + DEFAULT_GRACE_PERIOD
    actual = dt.datetime.fromisoformat(body["downgrade_scheduled_for"]).replace(tzinfo=expected.tzinfo)
    assert abs((actual - expected).total_seconds()) < 1


async def test_webhook_invoice_payment_failed_does_not_reset_an_already_running_grace_period(
    client: AsyncClient,
) -> None:
    """Stripe's own smart retries fire several invoice.payment_failed
    events across the grace period — the second (and third, ...) one
    must not push the dunning clock back out, or the grace period would
    never actually expire."""
    token = await _register_and_login(client, "pastdue2@example.com")
    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    subscription_id = sub_resp.json()["id"]

    async def activate():
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": subscription_id,
                        "customer": "cus_pastdue2",
                        "subscription": "sub_pastdue2",
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, activate)

    async def fail():
        payload = json.dumps(
            {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_pastdue2"}}}
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, fail)
    first = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    first_past_due_since = first.json()["past_due_since"]

    await _with_stripe_configured(client, fail)  # a second failed-retry event
    second = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert second.json()["past_due_since"] == first_past_due_since


async def test_webhook_subscription_recovering_to_active_clears_the_grace_period(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pastdue3@example.com")
    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    subscription_id = sub_resp.json()["id"]

    async def activate():
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": subscription_id,
                        "customer": "cus_pastdue3",
                        "subscription": "sub_pastdue3",
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, activate)

    async def fail():
        payload = json.dumps(
            {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_pastdue3"}}}
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, fail)
    mid = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert mid.json()["status"] == "past_due"
    assert mid.json()["past_due_since"] is not None

    async def recover():
        payload = json.dumps(
            {
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_pastdue3",
                        "customer": "cus_pastdue3",
                        "status": "active",
                        "current_period_end": 1999999999,
                        "cancel_at_period_end": False,
                        "items": {"data": []},
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    await _with_stripe_configured(client, recover)

    final = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    body = final.json()
    assert body["status"] == "active"
    assert body["past_due_since"] is None


async def test_webhook_ignores_unhandled_event_types(client: AsyncClient) -> None:
    async def run():
        payload = json.dumps({"type": "some.unhandled.event", "data": {"object": {}}}).encode()
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["handled"] is False

    await _with_stripe_configured(client, run)
