from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_admin(db_session: AsyncSession, email: str) -> None:
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.is_platform_admin = True
    await db_session.commit()


async def test_non_admin_cannot_access_admin_endpoints(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")

    stats_resp = await client.get("/api/v1/admin/stats", headers=_auth(token))
    assert stats_resp.status_code == 403

    users_resp = await client.get("/api/v1/admin/users", headers=_auth(token))
    assert users_resp.status_code == 403


async def test_admin_stats_reflect_real_data(client: AsyncClient, db_session: AsyncSession) -> None:
    admin_token = await _register_and_login(client, "admin@example.com")
    await _register_and_login(client, "user1@example.com")
    await _register_and_login(client, "user2@example.com")
    await _make_admin(db_session, "admin@example.com")

    # Create a workspace and upload a dataset for one of the users to
    # exercise the dataset/version counters too.
    user1_token = await _register_and_login(client, "user1@example.com")
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Test WS", "industry": "general"}, headers=_auth(user1_token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", b"a,b\n1,2\n3,4\n", "text/csv")}
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(user1_token),
    )

    resp = await client.get("/api/v1/admin/stats", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()

    # 3 registered users: admin, user1, user2.
    assert body["total_users"] == 3
    assert body["active_users"] == 3
    assert body["total_workspaces"] == 1
    assert body["total_datasets"] == 1
    assert body["total_dataset_versions"] == 1
    # Subscriptions are created lazily on first access (Phase 4), not
    # eagerly at registration — only user1 did anything that triggered
    # one (the dataset upload's quota check), so only 1 exists here.
    assert body["subscriptions_by_plan"].get("free") == 1
    assert body["estimated_mrr_gbp"] == 0.0  # nobody is on a paid plan in this test


async def test_admin_users_endpoint_is_itself_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    admin_token = await _register_and_login(client, "admin2@example.com")
    await _register_and_login(client, "user3@example.com")
    await _make_admin(db_session, "admin2@example.com")

    resp = await client.get("/api/v1/admin/users", headers=_auth(admin_token))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "admin2@example.com" in emails
    assert "user3@example.com" in emails

    audit_resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(admin_token))
    event_types = [e["event_type"] for e in audit_resp.json()]
    assert "admin.user_data_accessed" in event_types
