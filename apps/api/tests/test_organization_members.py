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


async def _create_org(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post("/api/v1/organizations", json={"name": name}, headers=_auth(token))
    return resp.json()["id"]


async def test_list_members_returns_owner_and_invited_member(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner@example.com", "Org Owner")
    org_id = await _create_org(client, owner_token, "Acme Co")

    # Owner alone first.
    owner_only = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))
    assert owner_only.status_code == 200, owner_only.text
    assert len(owner_only.json()) == 1
    assert owner_only.json()[0]["role"] == "owner"
    assert owner_only.json()[0]["user_email"] == "owner@example.com"
    assert owner_only.json()[0]["user_full_name"] == "Org Owner"

    # Invite an existing user directly (immediate Membership, no email needed).
    member_token = await _register_and_login(client, "member@example.com", "Org Member")
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "member@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201, invite_resp.text

    members_resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))
    assert members_resp.status_code == 200
    members = {m["user_email"]: m for m in members_resp.json()}
    assert set(members) == {"owner@example.com", "member@example.com"}
    assert members["member@example.com"]["role"] == "analyst"

    # Any member — not just the owner — can read the member list.
    as_member = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(member_token))
    assert as_member.status_code == 200
    assert len(as_member.json()) == 2


async def test_non_member_cannot_list_organization_members(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner2@example.com")
    outsider_token = await _register_and_login(client, "outsider2@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(outsider_token))
    assert resp.status_code == 403


async def test_list_members_requires_authentication(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    resp = await client.get(f"/api/v1/organizations/{org_id}/members")
    assert resp.status_code == 401
