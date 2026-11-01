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


async def _create_tenancy(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Portfolio", "industry": "residential_property"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Inventory Rd", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(token),
    )
    property_id = prop_resp.json()["id"]
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Jordan Lee", "rent_amount_gbp": 1000, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    return tenancy_resp.json()["id"]


async def _create_property_and_tenancy(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Portfolio", "industry": "residential_property"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Cascade Rd", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(token),
    )
    property_id = prop_resp.json()["id"]
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Casey Doe", "rent_amount_gbp": 1000, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    return property_id, tenancy_resp.json()["id"]


async def test_create_and_fetch_inventory_with_items(client: AsyncClient) -> None:
    token = await _register_and_login(client, "inventory@example.com")
    tenancy_id = await _create_tenancy(client, token)

    create_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={
            "inventory_type": "check_in",
            "inspection_date": "2026-01-01",
            "notes": "All good at move-in",
            "items": [
                {"room": "Kitchen", "item_name": "Oven", "condition": "good"},
                {"room": "Living room", "item_name": "Carpet", "condition": "excellent", "notes": "Newly fitted"},
            ],
        },
        headers=_auth(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["tenancy_id"] == tenancy_id
    assert body["inventory_type"] == "check_in"
    assert len(body["items"]) == 2
    inventory_id = body["id"]

    get_resp = await client.get(f"/api/v1/inventories/{inventory_id}", headers=_auth(token))
    assert get_resp.status_code == 200
    assert len(get_resp.json()["items"]) == 2

    list_resp = await client.get(f"/api/v1/tenancies/{tenancy_id}/inventories", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_compare_check_in_and_check_out_inventories(client: AsyncClient) -> None:
    token = await _register_and_login(client, "comparer@example.com")
    tenancy_id = await _create_tenancy(client, token)

    check_in = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={
            "inventory_type": "check_in",
            "inspection_date": "2026-01-01",
            "items": [
                {"room": "Kitchen", "item_name": "Oven", "condition": "good"},
                {"room": "Hallway", "item_name": "Rug", "condition": "fair"},
            ],
        },
        headers=_auth(token),
    )
    check_in_id = check_in.json()["id"]

    check_out = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={
            "inventory_type": "check_out",
            "inspection_date": "2026-12-31",
            "items": [
                {"room": "Kitchen", "item_name": "Oven", "condition": "damaged", "notes": "Door hinge broken"},
                {"room": "Garden", "item_name": "Shed", "condition": "good"},
            ],
        },
        headers=_auth(token),
    )
    check_out_id = check_out.json()["id"]

    compare_resp = await client.get(
        f"/api/v1/inventories/{check_in_id}/compare/{check_out_id}", headers=_auth(token)
    )
    assert compare_resp.status_code == 200
    body = compare_resp.json()
    assert body["changed_count"] == 1
    assert body["removed_count"] == 1
    assert body["added_count"] == 1

    statuses = {(d["room"], d["item_name"]): d["status"] for d in body["items"]}
    assert statuses[("Kitchen", "Oven")] == "changed"
    assert statuses[("Hallway", "Rug")] == "removed"
    assert statuses[("Garden", "Shed")] == "added"


async def test_comparing_inventories_from_different_tenancies_is_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "crosscompare@example.com")
    tenancy_a = await _create_tenancy(client, token)
    tenancy_b = await _create_tenancy(client, token)

    inv_a = await client.post(
        f"/api/v1/tenancies/{tenancy_a}/inventories",
        json={"inventory_type": "check_in", "inspection_date": "2026-01-01", "items": []},
        headers=_auth(token),
    )
    inv_b = await client.post(
        f"/api/v1/tenancies/{tenancy_b}/inventories",
        json={"inventory_type": "check_in", "inspection_date": "2026-01-01", "items": []},
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/inventories/{inv_a.json()['id']}/compare/{inv_b.json()['id']}", headers=_auth(token)
    )
    assert resp.status_code == 400


async def test_outsider_cannot_access_inventories(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "invowner@example.com")
    outsider_token = await _register_and_login(client, "invoutsider@example.com")
    tenancy_id = await _create_tenancy(client, owner_token)

    create_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={"inventory_type": "check_in", "inspection_date": "2026-01-01", "items": []},
        headers=_auth(owner_token),
    )
    inventory_id = create_resp.json()["id"]

    assert (
        await client.get(f"/api/v1/inventories/{inventory_id}", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/tenancies/{tenancy_id}/inventories", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/tenancies/{tenancy_id}/inventories",
            json={"inventory_type": "check_out", "inspection_date": "2026-06-01", "items": []},
            headers=_auth(outsider_token),
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/inventories/{inventory_id}", headers=_auth(outsider_token))
    ).status_code == 403


async def test_deleting_inventory_removes_its_items(client: AsyncClient) -> None:
    token = await _register_and_login(client, "invdelete@example.com")
    tenancy_id = await _create_tenancy(client, token)

    create_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={
            "inventory_type": "check_in",
            "inspection_date": "2026-01-01",
            "items": [{"room": "Kitchen", "item_name": "Oven", "condition": "good"}],
        },
        headers=_auth(token),
    )
    inventory_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/inventories/{inventory_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (await client.get(f"/api/v1/inventories/{inventory_id}", headers=_auth(token))).status_code == 404


async def test_deleting_property_cascades_through_tenancy_to_inventories(client: AsyncClient) -> None:
    token = await _register_and_login(client, "invcascade@example.com")
    property_id, tenancy_id = await _create_property_and_tenancy(client, token)

    create_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/inventories",
        json={
            "inventory_type": "check_in",
            "inspection_date": "2026-01-01",
            "items": [{"room": "Kitchen", "item_name": "Oven", "condition": "good"}],
        },
        headers=_auth(token),
    )
    inventory_id = create_resp.json()["id"]

    inv_list_before = await client.get(f"/api/v1/tenancies/{tenancy_id}/inventories", headers=_auth(token))
    assert len(inv_list_before.json()) == 1

    # Deleting the property cascades: property -> tenancy -> inventory ->
    # inventory_item, all via ON DELETE CASCADE at the DB level.
    delete_resp = await client.delete(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (
        await client.get(f"/api/v1/inventories/{inventory_id}", headers=_auth(token))
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/tenancies/{tenancy_id}/inventories", headers=_auth(token))
    ).status_code == 404
