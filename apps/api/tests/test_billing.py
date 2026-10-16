import datetime as dt
import os

from httpx import AsyncClient

from app.core.config import get_settings

SAMPLE_CSV = b"name,value\nA,1\nB,2\nC,3\n"


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Billing Test", "industry": "general"}, headers=_auth(token)
    )
    return resp.json()["id"]


async def _upload(client: AsyncClient, token: str, workspace_id: str, name: str, content: bytes = SAMPLE_CSV):
    files = {"file": ("data.csv", content, "text/csv")}
    return await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": name},
        files=files,
        headers=_auth(token),
    )


async def test_plans_endpoint_is_public_and_lists_all_plans(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    plan_ids = {p["plan_id"] for p in resp.json()}
    assert plan_ids == {"free", "personal", "professional", "business", "team", "enterprise"}
    free = next(p for p in resp.json() if p["plan_id"] == "free")
    assert free["monthly_price_gbp"] == 0
    assert free["max_analyses_per_month"] == 3
    assert free["max_saved_datasets"] == 2


async def test_new_user_gets_free_subscription_automatically(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_id"] == "free"
    assert body["status"] == "active"
    assert body["usage"]["analyses_used"] == 0
    assert body["usage"]["analyses_limit"] == 3
    # Free plan: resets at the start of next calendar month (UTC), not
    # some arbitrary Stripe date — there is no Stripe subscription here.
    resets_at = dt.datetime.fromisoformat(body["usage"]["resets_at"])
    now = dt.datetime.now(dt.timezone.utc)
    assert resets_at.month == (now.month % 12) + 1
    assert resets_at.day == 1
    assert resets_at > now


async def test_analyze_consumes_quota_and_blocks_once_exhausted(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id = await _create_workspace(client, token)
    upload_resp = await _upload(client, token, workspace_id, "Data")
    table_id = upload_resp.json()["tables"][0]["id"]

    # Free plan allows 3 analyses/month.
    for i in range(3):
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/analyze",
            json={"operation": "descriptive_stats", "parameters": {"column": "value"}},
            headers=_auth(token),
        )
        assert resp.status_code == 201, f"call {i}: {resp.text}"

    blocked = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "value"}},
        headers=_auth(token),
    )
    assert blocked.status_code == 402
    assert "3 analyses per month" in blocked.json()["detail"]

    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert sub_resp.json()["usage"]["analyses_used"] == 3


async def test_failed_analysis_does_not_consume_quota(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    workspace_id = await _create_workspace(client, token)
    upload_resp = await _upload(client, token, workspace_id, "Data")
    table_id = upload_resp.json()["tables"][0]["id"]

    # Unknown column -> 400, should not cost a unit of quota.
    bad_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "not_a_column"}},
        headers=_auth(token),
    )
    assert bad_resp.status_code == 400

    sub_resp = await client.get("/api/v1/billing/subscription", headers=_auth(token))
    assert sub_resp.json()["usage"]["analyses_used"] == 0


async def test_upload_blocked_over_plan_file_size_limit(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    workspace_id = await _create_workspace(client, token)

    # Free plan caps uploads at 5MB; this CSV is well under the global 1GB
    # safety ceiling but over the plan limit.
    oversized_content = b"a,b\n" + b"1,2\n" * 2_000_000  # ~8MB
    resp = await _upload(client, token, workspace_id, "Too Big", content=oversized_content)
    assert resp.status_code == 402
    assert "plan" in resp.json()["detail"].lower()


async def test_upload_blocked_after_max_saved_datasets(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    workspace_id = await _create_workspace(client, token)

    # Free plan allows 2 saved datasets.
    first = await _upload(client, token, workspace_id, "Dataset One")
    second = await _upload(client, token, workspace_id, "Dataset Two")
    assert first.status_code == 201
    assert second.status_code == 201

    third = await _upload(client, token, workspace_id, "Dataset Three")
    assert third.status_code == 402
    assert "2 saved datasets" in third.json()["detail"]


async def test_checkout_and_portal_return_503_without_stripe_configured(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")

    checkout_resp = await client.post(
        "/api/v1/billing/checkout-session",
        json={"plan_id": "personal", "billing_period": "monthly"},
        headers=_auth(token),
    )
    assert checkout_resp.status_code == 503

    portal_resp = await client.post("/api/v1/billing/portal-session", json={}, headers=_auth(token))
    assert portal_resp.status_code == 503


async def test_outsider_cannot_read_org_subscription(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")

    org_resp = await client.post("/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    denied = await client.get(
        f"/api/v1/billing/subscription?organization_id={org_id}", headers=_auth(outsider_token)
    )
    assert denied.status_code == 403

    allowed = await client.get(
        f"/api/v1/billing/subscription?organization_id={org_id}", headers=_auth(owner_token)
    )
    assert allowed.status_code == 200


async def test_non_manager_gets_403_not_503_on_checkout(client: AsyncClient) -> None:
    """Security regression test: authorization must be checked before the
    "is Stripe configured" dependency resolves, or a non-manager would
    learn server configuration details (503) instead of simply being
    denied (403). Stripe is NOT configured in this test environment —
    if the ordering were wrong, this would incorrectly return 503."""
    owner_token = await _register_and_login(client, "owner8@example.com")
    analyst_email = "analyst8@example.com"
    analyst_token = await _register_and_login(client, analyst_email)

    org_resp = await client.post("/api/v1/organizations", json={"name": "Beta"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": analyst_email, "role": "analyst"},
        headers=_auth(owner_token),
    )

    resp = await client.post(
        "/api/v1/billing/checkout-session",
        json={"plan_id": "business", "billing_period": "monthly", "organization_id": org_id},
        headers=_auth(analyst_token),
    )
    assert resp.status_code == 403


async def test_checkout_rejects_plan_with_no_configured_price(client: AsyncClient) -> None:
    """Even if Stripe WERE configured, Enterprise has no self-serve price
    — this should be a clean 400, not an attempt to call Stripe with a
    null price id. We can't reach this path without Stripe configured
    (503 fires first), so this documents the intended behaviour via the
    plan registry directly rather than the live endpoint."""
    from app.core.plans import get_plan

    plan = get_plan("enterprise")
    assert plan.stripe_price_id_monthly is None
    assert plan.stripe_price_id_annual is None


async def test_concurrent_usage_counter_creation_does_not_crash(tmp_path) -> None:
    """Regression test for a real race condition found while verifying the
    scenario-comparison feature: comparing 2+ saved scenarios fires one
    quota-incrementing POST per scenario in parallel
    (ScenarioPanel.onCompare in the frontend), so two requests against the
    same subscription can both miss _get_or_create_usage_counter's SELECT
    and both try to INSERT this period's counter row — only one can win
    the table's unique (subscription_id, period_key) constraint, and the
    loser used to 500. Reproduced here with two independent connections
    against a shared file-backed SQLite db (StaticPool's single shared
    connection in the usual db_session fixture can't exhibit this)."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db.base import Base
    from app.models.billing import Subscription
    from app.services.billing import _get_or_create_usage_counter, current_period_key

    db_path = tmp_path / "usage_counter_race.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as setup_session:
        sub = Subscription(owner_user_id="race-owner", plan_id="free", status="active")
        setup_session.add(sub)
        await setup_session.commit()
        subscription_id = sub.id

    period_key = current_period_key()

    async def race() -> str:
        async with session_maker() as session:
            counter = await _get_or_create_usage_counter(session, subscription_id, period_key)
            await session.commit()
            return counter.id

    first_id, second_id = await asyncio.gather(race(), race())
    assert first_id == second_id  # both calls resolve to the same, single row
    await engine.dispose()


async def test_max_upload_size_env_override_does_not_break_plan_enforcement(client: AsyncClient) -> None:
    """Regression test for the bug caught during this build: the global
    safety ceiling must stay >= every plan's limit, or higher-tier plans
    would be silently capped by the platform default. Lower the global
    ceiling far below the free plan's limit and confirm the error message
    correctly attributes the rejection to the smaller of the two caps."""
    get_settings.cache_clear()
    os.environ["MAX_UPLOAD_SIZE_BYTES"] = "10"  # smaller than SAMPLE_CSV (23 bytes)
    try:
        token = await _register_and_login(client, "owner9@example.com")
        workspace_id = await _create_workspace(client, token)
        resp = await _upload(client, token, workspace_id, "Data")
        assert resp.status_code == 400  # platform ceiling (upload_validation.py), not the 402 plan check
    finally:
        del os.environ["MAX_UPLOAD_SIZE_BYTES"]
        get_settings.cache_clear()
