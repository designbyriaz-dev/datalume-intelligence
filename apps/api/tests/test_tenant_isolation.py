from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_outsider_cannot_read_other_orgs_workspace(client: AsyncClient) -> None:
    """Journey 7: an unauthorised user must not be able to access another
    organisation's workspace or data."""
    owner_token = await _register_and_login(client, "owner@acme.com")
    outsider_token = await _register_and_login(client, "outsider@rival.com")

    org_resp = await client.post("/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Acme Confidential", "industry": "business_finance", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    denied = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(outsider_token))
    assert denied.status_code == 403

    allowed = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(owner_token))
    assert allowed.status_code == 200


async def test_outsider_cannot_read_other_users_personal_workspace(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner2@example.com")
    outsider_token = await _register_and_login(client, "outsider2@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Personal Data", "industry": "general"},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    denied = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(outsider_token))
    assert denied.status_code == 403


async def test_non_manager_cannot_invite_members(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    analyst_email = "analyst@example.com"
    analyst_token = await _register_and_login(client, analyst_email)
    rando_token = await _register_and_login(client, "rando@example.com")

    org_resp = await client.post("/api/v1/organizations", json={"name": "Beta Corp"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": analyst_email, "role": "analyst"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201

    denied = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "someone-else@example.com", "role": "viewer"},
        headers=_auth(analyst_token),
    )
    assert denied.status_code == 403

    outsider_denied = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "someone-else@example.com", "role": "viewer"},
        headers=_auth(rando_token),
    )
    assert outsider_denied.status_code == 403
