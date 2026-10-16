"""A tiny database-row lease lock so only one API replica processes a
given recurring job at a time — needed once an app might run more than
one instance of app/main.py's in-process APScheduler (see
scheduled_reports.py's module docstring: this was previously documented
as single-instance-only).

Acquiring is a single conditional UPDATE, not a SELECT then an UPDATE,
so it stays atomic under concurrent transactions from separate
processes sharing the same database: the database itself serializes the
row-level write, and a second transaction racing the first re-evaluates
the WHERE clause against the post-commit row rather than stale data it
read earlier. That holds the same way under SQLite's single-writer
semantics as it does under Postgres's row-level locking, which is why
this app's tests exercise the exact same code path production runs,
rather than mocking locking out.

The lock row is created lazily on first use (handling the race between
two replicas' first-ever acquire via a unique-constraint violation)
instead of being seeded by a migration — tests build their schema
straight from the SQLAlchemy models (see tests/conftest.py), bypassing
Alembic entirely, so migration-only seed data would never exist there.

Lease-based, not held until explicitly released: a lease has a TTL, so
a replica that crashes mid-job without releasing doesn't lock every
other replica out forever — the next acquire attempt, once the TTL has
passed, treats the expired lease as free. A well-behaved caller still
releases explicitly as soon as it's done, via release_lock, so the next
tick doesn't have to wait out the full lease.

try_acquire_lock returns a per-acquisition holder token (not just a
bool) and release_lock requires that same token, only clearing the row
if it still matches. Without that, a caller whose acquire attempt
*failed* could still call release_lock and — since an unconditional
release has no way to tell "I never held this" from "I'm done with
this" — wipe out a lease another replica is actively relying on.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduler_lock import SchedulerLock

DEFAULT_LEASE_SECONDS = 240  # shorter than the 5-minute scheduler tick interval in app/main.py


async def try_acquire_lock(
    db: AsyncSession,
    lock_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: dt.datetime | None = None,
) -> str | None:
    """Attempts to acquire lock_id for lease_seconds. Returns a holder
    token (truthy) if acquired — pass this same token to release_lock
    when done — or None if another holder currently has a live lease on
    it. Commits (or rolls back) on every path, so this must be called
    with no other uncommitted work pending on `db`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    holder = str(uuid.uuid4())
    until = now + dt.timedelta(seconds=lease_seconds)

    result = await db.execute(
        update(SchedulerLock)
        .where(SchedulerLock.id == lock_id)
        .where((SchedulerLock.locked_until.is_(None)) | (SchedulerLock.locked_until < now))
        .values(locked_until=until, locked_by=holder)
    )
    if result.rowcount == 1:
        await db.commit()
        return holder

    # No row was updated — either the lock row doesn't exist yet (first
    # use anywhere) or it exists with a still-live lease held by someone
    # else. Distinguish the two: only the first case is worth trying to
    # create.
    existing = await db.get(SchedulerLock, lock_id)
    if existing is not None:
        await db.rollback()
        return None

    db.add(SchedulerLock(id=lock_id, locked_until=until, locked_by=holder))
    try:
        await db.commit()
        return holder
    except IntegrityError:
        # Lost the race to create the row to another replica doing the
        # exact same thing at the same instant — they hold the lock for
        # this tick, not us.
        await db.rollback()
        return None


async def release_lock(db: AsyncSession, lock_id: str, holder: str) -> None:
    """Releases lock_id immediately rather than waiting out its lease,
    so the next acquire attempt — this replica's next tick, or another
    replica's — doesn't have to wait for the full lease_seconds. Only
    clears the row if it's still held by `holder` (the token
    try_acquire_lock returned), so calling this after a failed acquire,
    or after the lease already expired and someone else re-acquired it,
    safely does nothing rather than clobbering that other holder's
    active lease."""
    await db.execute(
        update(SchedulerLock)
        .where(SchedulerLock.id == lock_id)
        .where(SchedulerLock.locked_by == holder)
        .values(locked_until=None, locked_by=None)
    )
    await db.commit()
