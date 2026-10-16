"""Fixed-window request rate limiting, backed by a database table
rather than Redis. This app's `redis_url` setting exists in
app/core/config.py but nothing actually connects to a real Redis
instance anywhere yet (the setting's own comment points at a
`app/services/queue.py` that was never built) — a correctness-critical
feature like rate limiting shouldn't depend on an unconfirmed piece of
infrastructure when the database already used for everything else
works just as well, identically under SQLite (dev/tests) and Postgres
(prod).

check_rate_limit uses the same atomic
conditional-UPDATE-then-insert-with-IntegrityError-fallback idiom as
app/services/distributed_lock.py, not a plain SELECT-then-write —
correctness matters here specifically because the scenario being
defended against (many near-simultaneous requests from the same
client) is exactly the scenario a naive read-then-write race would
fail under.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_limit import RateLimitWindow


def _window_start(now: dt.datetime, window_seconds: int) -> dt.datetime:
    epoch_seconds = int(now.timestamp())
    bucket_seconds = epoch_seconds - (epoch_seconds % window_seconds)
    return dt.datetime.fromtimestamp(bucket_seconds, tz=dt.timezone.utc)


async def check_rate_limit(
    db: AsyncSession,
    *,
    bucket_key: str,
    max_requests: int,
    window_seconds: int,
    now: dt.datetime | None = None,
) -> bool:
    """Atomically records one request against bucket_key's current fixed
    window and returns whether that window is still within
    max_requests (inclusive) after counting this one. Commits on every
    path, so this must be called with no other uncommitted work pending
    on `db`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    window_start = _window_start(now, window_seconds)

    result = await db.execute(
        update(RateLimitWindow)
        .where(RateLimitWindow.bucket_key == bucket_key, RateLimitWindow.window_start == window_start)
        .values(count=RateLimitWindow.count + 1)
    )
    if result.rowcount == 0:
        db.add(RateLimitWindow(bucket_key=bucket_key, window_start=window_start, count=1))
        try:
            await db.commit()
        except IntegrityError:
            # Another request for the same bucket's first-ever window
            # created the row between our UPDATE (which matched
            # nothing) and our INSERT — retry the UPDATE, which will
            # now find their row.
            await db.rollback()
            await db.execute(
                update(RateLimitWindow)
                .where(RateLimitWindow.bucket_key == bucket_key, RateLimitWindow.window_start == window_start)
                .values(count=RateLimitWindow.count + 1)
            )
            await db.commit()
    else:
        await db.commit()

    current = await db.scalar(
        select(RateLimitWindow.count).where(
            RateLimitWindow.bucket_key == bucket_key, RateLimitWindow.window_start == window_start
        )
    )
    return (current or 0) <= max_requests


async def purge_expired_windows(db: AsyncSession, *, older_than: dt.datetime) -> int:
    """Deletes rate-limit window rows that ended before older_than.
    Called periodically (see app/main.py) rather than on every request,
    since an expired window is already inert (never matched by
    check_rate_limit's query again) — cleanup is purely about not
    growing the table forever, not correctness."""
    result = await db.execute(delete(RateLimitWindow).where(RateLimitWindow.window_start < older_than))
    await db.commit()
    return result.rowcount or 0
