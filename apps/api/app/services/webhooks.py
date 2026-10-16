"""Outbound webhook delivery. Uses httpx so dispatch_event is testable
with httpx.MockTransport — a real HTTP request/response cycle through
httpx's own machinery, with no real network call and no extra test
dependency (see tests/test_webhooks.py).

No retry queue: a failed delivery (network error or non-2xx response) is
recorded on the subscription (last_delivery_error) and nothing more.
Building real retry-with-backoff needs a job queue, which this
single-process deployment doesn't have yet (the brief's background-job
infrastructure is still Redis-provisioned-but-unused — see Phase 2's
CHECKLIST entry). Treat this as "we tell you what happened," not "we
guarantee delivery."
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookSubscription

WEBHOOK_EVENT_TYPES = {"dataset.uploaded", "report.generated"}


def generate_webhook_secret() -> str:
    return "whsub_" + secrets.token_urlsafe(32)


def sign_payload(secret: str, payload_json: str, timestamp: int | None = None) -> str:
    """Same scheme Stripe uses to sign webhooks to us — see
    app/services/stripe_billing.py and tests/test_billing_webhook.py.
    Reusing a well-known scheme means an integrator's existing
    Stripe-webhook verification code is usually a copy-paste away from
    verifying ours too."""
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload_json}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


async def dispatch_event(
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    *,
    event_type: str,
    workspace_id: str,
    payload: dict[str, Any],
) -> list[WebhookSubscription]:
    """Finds every active subscription on this workspace subscribed to
    event_type, POSTs a signed payload to each, and records the outcome.
    Delivery failures are caught and recorded per-subscription — one
    broken webhook endpoint never raises out of the caller's request."""
    if event_type not in WEBHOOK_EVENT_TYPES:
        raise ValueError(f"Unregistered webhook event_type: {event_type!r}")

    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.workspace_id == workspace_id, WebhookSubscription.is_active.is_(True)
        )
    )
    candidates = [s for s in result.scalars().all() if event_type in s.event_types]

    body = {"event_type": event_type, "workspace_id": workspace_id, "data": payload}
    payload_json = json.dumps(body, sort_keys=True, default=str)

    delivered: list[WebhookSubscription] = []
    for subscription in candidates:
        signature = sign_payload(subscription.secret, payload_json)
        try:
            response = await http_client.post(
                subscription.url,
                content=payload_json,
                headers={"Content-Type": "application/json", "X-DataLume-Signature": signature},
                timeout=10.0,
            )
            subscription.last_delivery_status = response.status_code
            subscription.last_delivery_error = None if response.is_success else f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            subscription.last_delivery_status = None
            subscription.last_delivery_error = str(exc)

        subscription.last_delivery_at = datetime.now(timezone.utc)
        delivered.append(subscription)

    if delivered:
        await db.commit()

    return delivered


async def send_test_delivery(db: AsyncSession, http_client: httpx.AsyncClient, subscription: WebhookSubscription) -> None:
    """Sends a synthetic delivery to exactly this subscription, bypassing
    its event_types filter — lets an integrator verify their endpoint
    works right after setting it up, without waiting for a real event."""
    payload_json = json.dumps(
        {"event_type": "test", "workspace_id": subscription.workspace_id, "data": {"message": "Test delivery from DataLume Intelligence."}},
        sort_keys=True,
    )
    signature = sign_payload(subscription.secret, payload_json)
    try:
        response = await http_client.post(
            subscription.url,
            content=payload_json,
            headers={"Content-Type": "application/json", "X-DataLume-Signature": signature},
            timeout=10.0,
        )
        subscription.last_delivery_status = response.status_code
        subscription.last_delivery_error = None if response.is_success else f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        subscription.last_delivery_status = None
        subscription.last_delivery_error = str(exc)

    subscription.last_delivery_at = datetime.now(timezone.utc)
    await db.commit()
