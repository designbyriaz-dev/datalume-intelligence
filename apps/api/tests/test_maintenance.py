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


async def _create_workspace_and_property(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Portfolio", "industry": "residential_property"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Maintenance Rd", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(token),
    )
    return workspace_id, prop_resp.json()["id"]


async def test_create_and_fetch_maintenance_request(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maint@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Boiler not working", "priority": "high", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["property_id"] == property_id
    assert body["status"] == "reported"
    assert body["priority"] == "high"
    request_id = body["id"]

    get_resp = await client.get(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Boiler not working"

    list_resp = await client.get(f"/api/v1/properties/{property_id}/maintenance-requests", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_update_status_and_resolved_date(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maintupdate@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Leaking tap", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    request_id = create_resp.json()["id"]
    assert create_resp.json()["priority"] == "medium"  # default

    update_resp = await client.patch(
        f"/api/v1/maintenance-requests/{request_id}",
        json={"status": "completed", "priority": "medium", "resolved_date": "2026-11-05"},
        headers=_auth(token),
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["status"] == "completed"
    assert body["resolved_date"] == "2026-11-05"


async def test_filter_by_status(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maintfilter@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    open_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Open issue", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    closed_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "To be closed", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    await client.patch(
        f"/api/v1/maintenance-requests/{closed_resp.json()['id']}",
        json={"status": "completed", "priority": "medium", "resolved_date": "2026-11-02"},
        headers=_auth(token),
    )

    reported_only = await client.get(
        f"/api/v1/properties/{property_id}/maintenance-requests?status=reported", headers=_auth(token)
    )
    assert [r["id"] for r in reported_only.json()] == [open_resp.json()["id"]]

    completed_only = await client.get(
        f"/api/v1/properties/{property_id}/maintenance-requests?status=completed", headers=_auth(token)
    )
    assert [r["id"] for r in completed_only.json()] == [closed_resp.json()["id"]]


async def test_tenancy_id_must_belong_to_the_same_property(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maintcross@example.com")
    _workspace_id, property_a = await _create_workspace_and_property(client, token)
    _workspace_id2, property_b = await _create_workspace_and_property(client, token)

    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_b}/tenancies",
        json={"tenant_name": "Sam Rivers", "rent_amount_gbp": 900, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/properties/{property_a}/maintenance-requests",
        json={"title": "Mismatch", "reported_date": "2026-11-01", "tenancy_id": tenancy_id},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_outsider_cannot_access_maintenance_requests(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "maintowner@example.com")
    outsider_token = await _register_and_login(client, "maintoutsider@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, owner_token)

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Private issue", "reported_date": "2026-11-01"},
        headers=_auth(owner_token),
    )
    request_id = create_resp.json()["id"]

    assert (
        await client.get(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/properties/{property_id}/maintenance-requests", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/maintenance-requests/{request_id}",
            json={"status": "completed", "priority": "medium"},
            headers=_auth(outsider_token),
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(outsider_token))
    ).status_code == 403


async def test_delete_maintenance_request(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maintdelete@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Temp issue", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    request_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (
        await client.get(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(token))
    ).status_code == 404


async def test_deleting_property_cascades_to_maintenance_requests(client: AsyncClient) -> None:
    token = await _register_and_login(client, "maintcascade@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Cascade check", "reported_date": "2026-11-01"},
        headers=_auth(token),
    )
    request_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (
        await client.get(f"/api/v1/maintenance-requests/{request_id}", headers=_auth(token))
    ).status_code == 404


async def test_tenancy_reference_survives_as_set_null_semantics(client: AsyncClient) -> None:
    """A maintenance request tagged with a reporting tenancy is still
    readable even once that tenancy would no longer exist — exercised
    indirectly here via the model-level FK (no endpoint deletes a
    Tenancy independently of its Property today, so this mainly
    documents the intent captured in app/models/maintenance.py)."""
    token = await _register_and_login(client, "mainttenancy@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Reporter Tenant", "rent_amount_gbp": 900, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]

    create_resp = await client.post(
        f"/api/v1/properties/{property_id}/maintenance-requests",
        json={"title": "Reported by tenant", "reported_date": "2026-11-01", "tenancy_id": tenancy_id},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["tenancy_id"] == tenancy_id
