"""Unit tests for the lease-lock primitive in
app/services/distributed_lock.py, independent of scheduled reports (its
only consumer today, but the primitive itself is generic)."""

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.distributed_lock import release_lock, try_acquire_lock


async def test_second_acquire_is_blocked_while_lease_is_live(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)

    first = await try_acquire_lock(db_session, "x", lease_seconds=60, now=now)
    assert first is not None

    second = await try_acquire_lock(db_session, "x", lease_seconds=60, now=now + dt.timedelta(seconds=1))
    assert second is None


async def test_acquire_succeeds_again_once_the_lease_expires(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)

    first = await try_acquire_lock(db_session, "x", lease_seconds=1, now=now)
    assert first is not None

    later = now + dt.timedelta(seconds=2)
    second = await try_acquire_lock(db_session, "x", lease_seconds=60, now=later)
    assert second is not None
    assert second != first


async def test_release_allows_immediate_reacquire(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)

    holder = await try_acquire_lock(db_session, "x", lease_seconds=300, now=now)
    assert holder is not None

    await release_lock(db_session, "x", holder)

    # Same instant — would fail if release hadn't actually cleared it,
    # since the 300s lease wouldn't have expired yet.
    reacquired = await try_acquire_lock(db_session, "x", lease_seconds=60, now=now)
    assert reacquired is not None


async def test_release_with_stale_holder_token_does_not_clobber_the_new_holder(db_session: AsyncSession) -> None:
    """The exact bug this design avoids: a caller that acquired the lock,
    had its lease expire, and only *then* calls release — after someone
    else has already legitimately re-acquired — must not wipe out that
    new holder's active lease."""
    now = dt.datetime.now(dt.timezone.utc)

    stale_holder = await try_acquire_lock(db_session, "x", lease_seconds=1, now=now)
    assert stale_holder is not None

    later = now + dt.timedelta(seconds=2)
    new_holder = await try_acquire_lock(db_session, "x", lease_seconds=300, now=later)
    assert new_holder is not None
    assert new_holder != stale_holder

    # The original holder finally gets around to releasing its
    # (already-expired, already-superseded) lease.
    await release_lock(db_session, "x", stale_holder)

    # The new holder's lease must still be intact.
    still_blocked = await try_acquire_lock(db_session, "x", lease_seconds=60, now=later + dt.timedelta(seconds=1))
    assert still_blocked is None


async def test_different_lock_ids_are_independent(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)

    a = await try_acquire_lock(db_session, "a", lease_seconds=300, now=now)
    b = await try_acquire_lock(db_session, "b", lease_seconds=300, now=now)
    assert a is not None
    assert b is not None
    assert a != b
