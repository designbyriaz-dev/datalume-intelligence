from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str, full_name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": full_name},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_personal_workspace(client: AsyncClient) -> None:
    token = await _register_and_login(client, "landlord@example.com")

    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "My Rental Portfolio", "industry": "residential_property"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Rental Portfolio"
    assert body["industry"] == "residential_property"
    assert body["organization_id"] is None


async def test_list_workspaces_only_returns_own(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "a@example.com")
    token_b = await _register_and_login(client, "b@example.com")

    await client.post(
        "/api/v1/workspaces",
        json={"name": "A's workspace", "industry": "general"},
        headers=_auth(token_a),
    )

    resp_b = await client.get("/api/v1/workspaces", headers=_auth(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    resp_a = await client.get("/api/v1/workspaces", headers=_auth(token_a))
    assert len(resp_a.json()) == 1


async def test_create_organization_workspace_requires_membership(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    outsider_token = await _register_and_login(client, "outsider@example.com")

    org_resp = await client.post(
        "/api/v1/organizations", json={"name": "Acme Lettings"}, headers=_auth(owner_token)
    )
    org_id = org_resp.json()["id"]

    ok_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Acme Portfolio", "industry": "commercial_property", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    assert ok_resp.status_code == 201

    denied_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Sneaky", "industry": "general", "organization_id": org_id},
        headers=_auth(outsider_token),
    )
    assert denied_resp.status_code == 403
