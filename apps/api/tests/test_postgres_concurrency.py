"""Real concurrent-write races against real Postgres — closes a gap
narrower than "never run against Postgres at all" (that gap was closed
in docs/CHECKLIST.md's "Post-Phase-7: verify the test suite against
real Postgres" section, which found and fixed a real datetime
timezone divergence). The one live concurrency proof that exists in
this codebase before this file — app/services/distributed_lock.py's
own write-up in docs/CHECKLIST.md's "Post-Phase-7: distributed
scheduler lock" section — raced two engines against real *SQLite*, not
Postgres. The claim "this holds under both SQLite and Postgres" was
reasoned from first principles (an atomic conditional UPDATE), never
demonstrated with a real race against Postgres specifically. This file
demonstrates it.

Skips the whole module unless POSTGRES_TEST_DATABASE_URL is set — same
pattern as test_s3_storage_r2.py/test_s3_storage_minio.py — since this
is about Postgres's own row-locking/MVCC semantics, not something
SQLite's single-writer model can stand in for.

Two things raced here:

1. distributed_lock.try_acquire_lock, using two genuinely independent
   AsyncEngine instances (not two coroutines sharing one connection —
   that would prove nothing about real multi-process concurrency) and
   an asyncio.Barrier so both reach the contended UPDATE/INSERT before
   either is allowed to proceed. Without the barrier, the event loop
   could just run one to completion before the other starts, which
   would pass without ever exercising a real race.

2. Rent Collection's webhook idempotency (ProcessedWebhookEvent's
   unique constraint on stripe_event_id) — the existing regression
   test in test_rent_collection.py posts the same payload sequentially
   twice. Here, two concurrent HTTP requests through the same ASGI app
   are issued via asyncio.gather; FastAPI's get_db override opens a
   fresh AsyncSession (a real, separate Postgres connection from the
   pool) per request, so this exercises two real overlapping
   transactions, not two sequential calls that happen to pass.
"""

import asyncio
import hashlib
import hmac
import json
import os
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.property import RentLedgerEntry
from app.models.rent_collection import ProcessedWebhookEvent, RentPaymentRequest
from app.services.distributed_lock import try_acquire_lock

POSTGRES_TEST_DATABASE_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="No real Postgres supplied via POSTGRES_TEST_DATABASE_URL — this file is specifically about "
    "Postgres's own concurrency semantics, so it does not fall back to SQLite the way other tests do.",
)

WEBHOOK_SECRET = "whsec_test_connect_secret_for_postgres_concurrency_testing"


async def test_only_one_concurrent_lock_acquirer_wins_against_real_postgres(db_session: AsyncSession) -> None:
    """The exact proof docs/CHECKLIST.md's distributed-lock section did
    against SQLite, redone against real Postgres. db_session is only
    depended on for its setup side effect (drop_all/create_all against
    the real database) — the actual race uses two fresh engines below,
    standing in for two separate API processes."""
    engine_a = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    engine_b = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    session_a = async_sessionmaker(engine_a, expire_on_commit=False, class_=AsyncSession)()
    session_b = async_sessionmaker(engine_b, expire_on_commit=False, class_=AsyncSession)()

    barrier = asyncio.Barrier(2)

    async def race(session: AsyncSession) -> str | None:
        await barrier.wait()
        return await try_acquire_lock(session, "postgres-concurrency-test-lock", lease_seconds=60)

    try:
        result_a, result_b = await asyncio.gather(race(session_a), race(session_b))
    finally:
        await session_a.close()
        await session_b.close()
        await engine_a.dispose()
        await engine_b.dispose()

    winners = [r for r in (result_a, result_b) if r is not None]
    losers = [r for r in (result_a, result_b) if r is None]
    assert len(winners) == 1, f"expected exactly one winner, got {(result_a, result_b)}"
    assert len(losers) == 1


async def test_concurrent_webhook_deliveries_for_the_same_event_credit_the_ledger_exactly_once_against_real_postgres(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Same scenario as test_rent_collection.py's
    test_duplicate_webhook_delivery_does_not_double_credit_ledger, but
    the two deliveries are issued concurrently (asyncio.gather) rather
    than sequentially, so this actually exercises two real, overlapping
    Postgres transactions racing on ProcessedWebhookEvent's unique
    constraint — not two calls that happen to pass because the first
    one always finishes before the second starts."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "pg_concurrency@example.com", "password": "correct-horse-battery", "full_name": "Test User"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "pg_concurrency@example.com", "password": "correct-horse-battery"}
    )
    token = login_resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "PG Concurrency Test WS", "industry": "general"}, headers=auth
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Concurrency Street", "city": "London", "postcode": "E1 6AN"},
        headers=auth,
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
        headers=auth,
    )
    tenancy_id = tenancy_resp.json()["id"]
    entry_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "charge", "amount_gbp": 1200.00, "entry_date": "2026-01-01"},
        headers=auth,
    )
    ledger_entry_id = entry_resp.json()["id"]

    session_id = "cs_test_pg_concurrency_session_123"
    payment_request = RentPaymentRequest(
        ledger_entry_id=ledger_entry_id,
        tenancy_id=tenancy_id,
        stripe_account_id="acct_test_pg_concurrency",
        stripe_checkout_session_id=session_id,
        amount_gbp=1200.00,
        tenant_email="tenant@example.com",
        checkout_url="https://checkout.stripe.com/test",
    )
    db_session.add(payment_request)
    await db_session.commit()

    payload = json.dumps(
        {
            "id": "evt_test_pg_concurrency_1",
            "type": "checkout.session.completed",
            "data": {"object": {"id": session_id, "payment_intent": "pi_test_pg_concurrency"}},
        }
    ).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
    stripe_signature = f"t={timestamp},v1={signature}"

    get_settings.cache_clear()
    os.environ["RENT_COLLECTION_ENABLED"] = "true"
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake_for_connect_webhook_signature_testing"
    os.environ["STRIPE_CONNECT_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    try:

        async def deliver():
            return await client.post(
                "/api/v1/rent-collection/webhook",
                content=payload,
                headers={"stripe-signature": stripe_signature, "Content-Type": "application/json"},
            )

        resp_a, resp_b = await asyncio.gather(deliver(), deliver())
    finally:
        del os.environ["RENT_COLLECTION_ENABLED"]
        del os.environ["STRIPE_SECRET_KEY"]
        del os.environ["STRIPE_CONNECT_WEBHOOK_SECRET"]
        get_settings.cache_clear()

    assert resp_a.status_code == 200, resp_a.text
    assert resp_b.status_code == 200, resp_b.text
    bodies = [resp_a.json(), resp_b.json()]
    handled_count = sum(1 for b in bodies if b.get("handled") is True)
    duplicate_count = sum(1 for b in bodies if b.get("duplicate") is True)
    assert handled_count == 1, f"expected exactly one real handler run, got {bodies}"
    assert duplicate_count == 1, f"expected exactly one duplicate rejection, got {bodies}"

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
    assert len(entries) == 1, "exactly one payment ledger entry must result from the real concurrent race"

    events = (await db_session.execute(select(ProcessedWebhookEvent))).scalars().all()
    assert len(events) == 1
