"""Direct tests of app/services/dunning.py's downgrade_overdue_subscriptions
— same pattern as test_scheduled_reports.py: exercise the real scheduler
logic directly rather than waiting on wall-clock time or the real
APScheduler job."""

import datetime as dt

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Subscription, SubscriptionStatus
from app.services.distributed_lock import try_acquire_lock
from app.services.dunning import DEFAULT_GRACE_PERIOD, DUNNING_LOCK_ID, downgrade_overdue_subscriptions
from app.services.email import EmailMessage


async def _register_and_login(client: AsyncClient, email: str, full_name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": full_name},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _get_personal_subscription(client: AsyncClient, token: str) -> str:
    resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    return resp.json()["id"]


async def _mark_past_due(
    db_session: AsyncSession,
    subscription_id: str,
    *,
    since: dt.datetime,
    plan_id: str = "professional",
    stripe_subscription_id: str | None = "sub_overdue_test",
) -> Subscription:
    subscription = await db_session.get(Subscription, subscription_id)
    subscription.status = SubscriptionStatus.PAST_DUE
    subscription.past_due_since = since
    subscription.plan_id = plan_id
    subscription.stripe_subscription_id = stripe_subscription_id
    subscription.stripe_customer_id = "cus_overdue_test"
    await db_session.commit()
    return subscription


class _FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class _FakeStripeClient:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.canceled: list[str] = []
        self._raises = raises

    def cancel_subscription(self, *, stripe_subscription_id: str) -> None:
        if self._raises is not None:
            raise self._raises
        self.canceled.append(stripe_subscription_id)


async def test_downgrades_subscription_past_the_grace_period(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _register_and_login(client, "overdue1@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(db_session, subscription_id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1))

    downgraded = await downgrade_overdue_subscriptions(db_session, now=now)

    assert len(downgraded) == 1
    assert downgraded[0].id == subscription_id
    assert downgraded[0].plan_id == "free"
    assert downgraded[0].status == SubscriptionStatus.CANCELED
    assert downgraded[0].past_due_since is None


async def test_does_not_downgrade_subscription_still_within_the_grace_period(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "overdue2@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    # Only 1 day into a 7-day grace period — not due yet.
    await _mark_past_due(db_session, subscription_id, since=now - dt.timedelta(days=1))

    downgraded = await downgrade_overdue_subscriptions(db_session, now=now)

    assert downgraded == []
    subscription = await db_session.get(Subscription, subscription_id)
    assert subscription.plan_id == "professional"  # untouched
    assert subscription.status == SubscriptionStatus.PAST_DUE


async def test_ignores_active_subscriptions_regardless_of_past_due_since(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A subscription that recovered (status flipped back to ACTIVE) but
    somehow still has a stale past_due_since must not be downgraded —
    status is the authoritative gate, not just the timestamp."""
    token = await _register_and_login(client, "overdue3@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    subscription = await db_session.get(Subscription, subscription_id)
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.past_due_since = now - DEFAULT_GRACE_PERIOD - dt.timedelta(days=5)
    subscription.plan_id = "professional"
    await db_session.commit()

    downgraded = await downgrade_overdue_subscriptions(db_session, now=now)

    assert downgraded == []
    subscription = await db_session.get(Subscription, subscription_id)
    assert subscription.plan_id == "professional"


async def test_attempts_to_cancel_the_real_stripe_subscription(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _register_and_login(client, "overdue4@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(
        db_session,
        subscription_id,
        since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1),
        stripe_subscription_id="sub_cancel_me",
    )

    stripe_client = _FakeStripeClient()
    await downgrade_overdue_subscriptions(db_session, now=now, stripe_client=stripe_client)

    assert stripe_client.canceled == ["sub_cancel_me"]


async def test_local_downgrade_still_happens_even_if_stripe_cancel_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Best-effort: Stripe being unreachable must never block the local
    downgrade, which is what actually controls this app's own
    entitlements — mirrors test_email_send_failure_does_not_undo_report_
    generation's reasoning in test_scheduled_reports.py."""
    token = await _register_and_login(client, "overdue5@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(db_session, subscription_id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1))

    stripe_client = _FakeStripeClient(raises=RuntimeError("Stripe API unreachable (simulated)"))
    downgraded = await downgrade_overdue_subscriptions(db_session, now=now, stripe_client=stripe_client)

    assert len(downgraded) == 1
    assert downgraded[0].plan_id == "free"


async def test_sends_exactly_one_email_to_the_personal_subscription_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "overdue6@example.com", "Overdue Owner")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(db_session, subscription_id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1))

    sender = _FakeEmailSender()
    await downgrade_overdue_subscriptions(db_session, now=now, email_sender=sender)

    assert len(sender.sent) == 1
    assert sender.sent[0].to == "overdue6@example.com"
    assert "downgraded" in sender.sent[0].subject.lower()


async def test_sends_email_to_every_organization_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    owner_token = await _register_and_login(client, "orgowner@example.com", "Org Owner")
    org_resp = await client.post(
        "/api/v1/organizations", json={"name": "Overdue Org"}, headers=_auth(owner_token)
    )
    org_id = org_resp.json()["id"]

    # Invite a second user and promote them to OWNER too, so there are
    # two real owners to notify.
    second_token = await _register_and_login(client, "secondowner@example.com", "Second Owner")
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "secondowner@example.com", "role": "owner"},
        headers=_auth(owner_token),
    )

    from app.services.billing import get_or_create_subscription_for_organization

    subscription = await get_or_create_subscription_for_organization(db_session, org_id)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(db_session, subscription.id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1))

    sender = _FakeEmailSender()
    downgraded = await downgrade_overdue_subscriptions(db_session, now=now, email_sender=sender)

    assert len(downgraded) == 1
    recipients = {message.to for message in sender.sent}
    assert recipients == {"orgowner@example.com", "secondowner@example.com"}


async def test_audit_event_records_the_previous_plan_id(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _register_and_login(client, "overdue7@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(
        db_session, subscription_id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1), plan_id="business"
    )

    await downgrade_overdue_subscriptions(db_session, now=now)

    audit_resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
    events = [e for e in audit_resp.json() if e["event_type"] == "billing.downgraded_for_nonpayment"]
    assert len(events) == 1
    assert events[0]["event_metadata"]["previous_plan_id"] == "business"


async def test_skips_the_tick_when_another_replica_holds_the_lock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _register_and_login(client, "overdue8@example.com")
    subscription_id = await _get_personal_subscription(client, token)

    now = dt.datetime.now(dt.timezone.utc)
    await _mark_past_due(db_session, subscription_id, since=now - DEFAULT_GRACE_PERIOD - dt.timedelta(hours=1))

    other_replica_holder = await try_acquire_lock(db_session, DUNNING_LOCK_ID, now=now)
    assert other_replica_holder is not None

    downgraded = await downgrade_overdue_subscriptions(db_session, now=now)

    assert downgraded == []
    subscription = await db_session.get(Subscription, subscription_id)
    assert subscription.plan_id == "professional"  # completely untouched, lock skipped the whole tick
