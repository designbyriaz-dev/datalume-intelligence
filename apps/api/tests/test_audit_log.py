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


async def test_registration_and_login_are_audited(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")

    resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
    assert resp.status_code == 200
    event_types = [e["event_type"] for e in resp.json()]
    assert "auth.user_registered" in event_types
    assert "auth.login_succeeded" in event_types


async def test_failed_login_is_audited_without_leaking_unknown_accounts(client: AsyncClient) -> None:
    # Register and log in once to have a way to inspect the trail.
    token = await _register_and_login(client, "owner2@example.com")

    # Wrong password against a real account.
    await client.post(
        "/api/v1/auth/login", json={"email": "owner2@example.com", "password": "totally-wrong-password"}
    )
    # Login attempt against an email that was never registered.
    await client.post(
        "/api/v1/auth/login", json={"email": "never-registered@example.com", "password": "whatever12345"}
    )

    resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
    failed_events = [e for e in resp.json() if e["event_type"] == "auth.login_failed"]
    assert len(failed_events) == 1  # only the real account's failed attempt is attributed to this user
    assert failed_events[0]["actor_user_id"] is not None


async def test_organization_events_are_audited_and_exportable(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    member_email = "member3@example.com"
    await _register_and_login(client, member_email)

    org_resp = await client.post("/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": member_email, "role": "analyst"},
        headers=_auth(owner_token),
    )

    json_resp = await client.get(f"/api/v1/organizations/{org_id}/audit-log", headers=_auth(owner_token))
    assert json_resp.status_code == 200
    event_types = [e["event_type"] for e in json_resp.json()]
    assert "organization.created" in event_types
    assert "organization.member_invited" in event_types

    csv_resp = await client.get(
        f"/api/v1/organizations/{org_id}/audit-log?format=csv", headers=_auth(owner_token)
    )
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "organization.created" in csv_resp.text
    assert "organization.member_invited" in csv_resp.text


async def test_api_key_lifecycle_is_audited(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    create_resp = await client.post("/api/v1/api-keys", json={"name": "CI"}, headers=_auth(token))
    key_id = create_resp.json()["id"]

    await client.delete(f"/api/v1/api-keys/{key_id}", headers=_auth(token))

    resp = await client.get("/api/v1/users/me/audit-log", headers=_auth(token))
    event_types = [e["event_type"] for e in resp.json()]
    assert "api_key.created" in event_types
    assert "api_key.revoked" in event_types


async def test_non_manager_cannot_export_audit_log(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    analyst_email = "analyst5@example.com"
    analyst_token = await _register_and_login(client, analyst_email)

    org_resp = await client.post("/api/v1/organizations", json={"name": "Beta"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": analyst_email, "role": "analyst"},
        headers=_auth(owner_token),
    )

    resp = await client.get(f"/api/v1/organizations/{org_id}/audit-log", headers=_auth(analyst_token))
    assert resp.status_code == 403


async def test_outsider_cannot_export_audit_log(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner6@example.com")
    outsider_token = await _register_and_login(client, "outsider6@example.com")

    org_resp = await client.post("/api/v1/organizations", json={"name": "Gamma"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    resp = await client.get(f"/api/v1/organizations/{org_id}/audit-log", headers=_auth(outsider_token))
    assert resp.status_code == 403
