"""Unit tests for the rate-limit primitive (app/services/rate_limit.py)
and integration tests proving the auth endpoints it's wired into
(app/api/v1/routers/auth.py) actually enforce a 429 — the "no rate
limiting on auth endpoints" gap this closes."""

import datetime as dt
import os

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.rate_limit import RateLimitWindow
from app.services.rate_limit import check_rate_limit, purge_expired_windows


async def test_requests_within_the_limit_are_all_allowed(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for _ in range(5):
        allowed = await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=now)
        assert allowed is True


async def test_the_request_that_exceeds_the_limit_is_rejected(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for _ in range(5):
        await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=now)

    sixth = await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=now)
    assert sixth is False


async def test_a_new_window_resets_the_count(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for _ in range(5):
        await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=now)
    assert await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=now) is False

    next_window = now + dt.timedelta(seconds=61)
    assert await check_rate_limit(db_session, bucket_key="x", max_requests=5, window_seconds=60, now=next_window) is True


async def test_different_bucket_keys_are_independent(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for _ in range(5):
        await check_rate_limit(db_session, bucket_key="a", max_requests=5, window_seconds=60, now=now)
    assert await check_rate_limit(db_session, bucket_key="a", max_requests=5, window_seconds=60, now=now) is False

    # A different bucket (e.g. a different client IP, or a different
    # endpoint) must not be affected by "a" being maxed out.
    assert await check_rate_limit(db_session, bucket_key="b", max_requests=5, window_seconds=60, now=now) is True


async def test_purge_expired_windows_removes_only_old_rows(db_session: AsyncSession) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    old = now - dt.timedelta(hours=7)
    await check_rate_limit(db_session, bucket_key="old", max_requests=100, window_seconds=60, now=old)
    await check_rate_limit(db_session, bucket_key="recent", max_requests=100, window_seconds=60, now=now)

    deleted = await purge_expired_windows(db_session, older_than=now - dt.timedelta(hours=6))
    assert deleted == 1

    remaining = (await db_session.execute(select(RateLimitWindow))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].bucket_key == "recent"


async def test_login_endpoint_returns_429_after_its_limit_is_exceeded(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "ratelimited@example.com", "password": "correct-horse-battery", "full_name": "Rate Limited"},
    )

    # The configured limit is 10 requests / 5 minutes per IP (see
    # app/api/v1/routers/auth.py's _login_rate_limit) — all requests in
    # this test share the test client's fixed address, so they all land
    # in the same bucket.
    last_status = None
    for _ in range(11):
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "ratelimited@example.com", "password": "correct-horse-battery"}
        )
        last_status = resp.status_code

    assert last_status == 429


async def test_login_rate_limit_does_not_fire_before_the_threshold(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "notlimited@example.com", "password": "correct-horse-battery", "full_name": "Not Limited"},
    )

    for _ in range(10):
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "notlimited@example.com", "password": "correct-horse-battery"}
        )
        assert resp.status_code == 200


async def test_forwarded_headers_are_ignored_outside_production(client: AsyncClient) -> None:
    """In dev (the test client's own environment), app/api/deps.py's
    `_client_ip` must use the direct connection address and ignore any
    client-supplied X-Real-Ip/X-Forwarded-For — honoring them here
    would let a forged header split one real client across unlimited
    buckets, defeating rate limiting entirely. A different forged
    X-Real-Ip per request must NOT create independent buckets; all
    requests should still land in the one shared bucket, same as if no
    header were sent at all."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "devheaders@example.com", "password": "correct-horse-battery", "full_name": "Dev Headers"},
    )

    last_status = None
    for i in range(11):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "devheaders@example.com", "password": "correct-horse-battery"},
            headers={"X-Real-Ip": f"9.9.9.{i}"},  # a different value every request
        )
        last_status = resp.status_code

    assert last_status == 429  # still shares one bucket — the header was ignored


async def test_production_rate_limit_keys_on_x_real_ip(client: AsyncClient) -> None:
    """Verified live against the real Railway deployment (not assumed)
    that its edge rewrites X-Real-Ip/X-Forwarded-For rather than
    passing through a client-supplied value — see `_client_ip`'s
    docstring in app/api/deps.py. With that confirmed, production
    should key on X-Real-Ip, so two different real clients (two
    different X-Real-Ip values) must get independent buckets."""
    get_settings.cache_clear()
    os.environ["ENVIRONMENT"] = "production"
    try:
        await client.post(
            "/api/v1/auth/register",
            json={"email": "prodheaders1@example.com", "password": "correct-horse-battery", "full_name": "A"},
        )
        await client.post(
            "/api/v1/auth/register",
            json={"email": "prodheaders2@example.com", "password": "correct-horse-battery", "full_name": "B"},
        )

        for _ in range(11):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "prodheaders1@example.com", "password": "correct-horse-battery"},
                headers={"X-Real-Ip": "203.0.113.1"},
            )
        assert resp.status_code == 429  # client 1's bucket is now exhausted

        # A different real client (different X-Real-Ip) must be unaffected.
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "prodheaders2@example.com", "password": "correct-horse-battery"},
            headers={"X-Real-Ip": "203.0.113.2"},
        )
        assert resp.status_code == 200
    finally:
        del os.environ["ENVIRONMENT"]
        get_settings.cache_clear()


async def test_production_rate_limit_falls_back_to_leftmost_x_forwarded_for(client: AsyncClient) -> None:
    """Without X-Real-Ip, production must use X-Forwarded-For's
    leftmost entry — the original client, per the live-verified
    behavior that Railway's edge appends its own hop(s) after the real
    address rather than letting a client-supplied value through
    unchanged. Two requests with the same leftmost address but
    different trailing (edge-hop) addresses must share one bucket."""
    get_settings.cache_clear()
    os.environ["ENVIRONMENT"] = "production"
    try:
        await client.post(
            "/api/v1/auth/register",
            json={"email": "xffuser@example.com", "password": "correct-horse-battery", "full_name": "XFF"},
        )

        last_status = None
        for hop in range(11):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "xffuser@example.com", "password": "correct-horse-battery"},
                headers={"X-Forwarded-For": f"198.51.100.7, 100.64.0.{hop}"},
            )
            last_status = resp.status_code

        assert last_status == 429  # same leftmost client IP each time -> one bucket
    finally:
        del os.environ["ENVIRONMENT"]
        get_settings.cache_clear()
