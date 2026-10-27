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


async def _create_workspace(client: AsyncClient, token: str, name: str = "My Portfolio") -> str:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": name, "industry": "residential_property"},
        headers=_auth(token),
    )
    return resp.json()["id"]


async def test_create_and_fetch_property(client: AsyncClient) -> None:
    token = await _register_and_login(client, "landlord@example.com")
    workspace_id = await _create_workspace(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "12 Example Street", "city": "London", "postcode": "E1 6AN"},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["workspace_id"] == workspace_id
    assert body["country"] == "United Kingdom"
    property_id = body["id"]

    get_resp = await client.get(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["address_line1"] == "12 Example Street"

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/properties", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_outsider_cannot_access_another_workspaces_property(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    outsider_token = await _register_and_login(client, "outsider@example.com")
    workspace_id = await _create_workspace(client, owner_token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Secret Lane", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(owner_token),
    )
    property_id = create_resp.json()["id"]

    denied_get = await client.get(f"/api/v1/properties/{property_id}", headers=_auth(outsider_token))
    assert denied_get.status_code == 403

    denied_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/properties", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403


async def test_tenancy_and_ledger_entry_lifecycle_and_balance(client: AsyncClient) -> None:
    token = await _register_and_login(client, "agent@example.com")
    workspace_id = await _create_workspace(client, token)

    property_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "5 Flat Road", "city": "Bristol", "postcode": "BS1 1AA"},
        headers=_auth(token),
    )
    property_id = property_resp.json()["id"]

    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={
            "tenant_name": "Jordan Lee",
            "rent_amount_gbp": 1000,
            "rent_frequency": "monthly",
            "start_date": "2026-01-01",
        },
        headers=_auth(token),
    )
    assert tenancy_resp.status_code == 201
    tenancy_id = tenancy_resp.json()["id"]
    assert tenancy_resp.json()["status"] == "active"

    charge_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "charge", "amount_gbp": 1000, "entry_date": "2026-01-01"},
        headers=_auth(token),
    )
    assert charge_resp.status_code == 201

    payment_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "payment", "amount_gbp": 600, "entry_date": "2026-01-05"},
        headers=_auth(token),
    )
    assert payment_resp.status_code == 201

    balance_resp = await client.get(f"/api/v1/tenancies/{tenancy_id}/balance", headers=_auth(token))
    assert balance_resp.status_code == 200
    assert balance_resp.json()["balance_gbp"] == 400

    entries_resp = await client.get(f"/api/v1/tenancies/{tenancy_id}/ledger-entries", headers=_auth(token))
    assert len(entries_resp.json()) == 2

    end_resp = await client.patch(
        f"/api/v1/tenancies/{tenancy_id}",
        json={"status": "ended", "end_date": "2026-06-30"},
        headers=_auth(token),
    )
    assert end_resp.status_code == 200
    assert end_resp.json()["status"] == "ended"


async def test_ledger_entries_have_no_update_or_delete_endpoint(client: AsyncClient) -> None:
    token = await _register_and_login(client, "noeditor@example.com")
    workspace_id = await _create_workspace(client, token)
    property_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "9 Ledger Ave", "city": "York", "postcode": "YO1 1AA"},
        headers=_auth(token),
    )
    property_id = property_resp.json()["id"]
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Sam Rivers", "rent_amount_gbp": 500, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]
    entry_resp = await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "charge", "amount_gbp": 500, "entry_date": "2026-01-01"},
        headers=_auth(token),
    )
    entry_id = entry_resp.json()["id"]

    # No PATCH/DELETE route exists for a single ledger entry at all — the
    # ledger is append-only by design (see app/models/property.py's module
    # docstring), so FastAPI has nothing registered at this path/method
    # combination and correctly 404s rather than exposing an edit/delete.
    patch_resp = await client.patch(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries/{entry_id}",
        json={"amount_gbp": 999},
        headers=_auth(token),
    )
    assert patch_resp.status_code == 404

    delete_resp = await client.delete(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries/{entry_id}", headers=_auth(token)
    )
    assert delete_resp.status_code == 404


async def test_deleting_property_cascades_to_tenancies_and_ledger(client: AsyncClient) -> None:
    token = await _register_and_login(client, "cascade@example.com")
    workspace_id = await _create_workspace(client, token)
    property_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "3 Cascade Close", "city": "Hull", "postcode": "HU1 1AA"},
        headers=_auth(token),
    )
    property_id = property_resp.json()["id"]
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Casey Doe", "rent_amount_gbp": 500, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]
    await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "charge", "amount_gbp": 500, "entry_date": "2026-01-01"},
        headers=_auth(token),
    )

    delete_resp = await client.delete(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (await client.get(f"/api/v1/properties/{property_id}", headers=_auth(token))).status_code == 404
    assert (
        await client.get(f"/api/v1/tenancies/{tenancy_id}/balance", headers=_auth(token))
    ).status_code == 404


async def test_portfolio_kpis_endpoint(client: AsyncClient) -> None:
    token = await _register_and_login(client, "kpis@example.com")
    workspace_id = await _create_workspace(client, token)
    property_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 KPI Way", "city": "Bath", "postcode": "BA1 1AA"},
        headers=_auth(token),
    )
    property_id = property_resp.json()["id"]
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Taylor Reed", "rent_amount_gbp": 1200, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]
    await client.post(
        f"/api/v1/tenancies/{tenancy_id}/ledger-entries",
        json={"entry_type": "charge", "amount_gbp": 1200, "entry_date": "2026-01-01"},
        headers=_auth(token),
    )

    kpis_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/properties/kpis", headers=_auth(token))
    assert kpis_resp.status_code == 200
    body = kpis_resp.json()
    assert body["total_properties"] == 1
    assert body["active_tenancies"] == 1
    assert body["expected_monthly_rent_gbp"] == 1200
    assert body["outstanding_balance_gbp"] == 1200
    assert body["arrears_count"] == 1
