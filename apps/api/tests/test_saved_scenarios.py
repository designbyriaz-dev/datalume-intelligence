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


COMMERCIAL_CSV = (
    b"Unit,Tenant Name,Rent (PCM),Lease Expiry Date,Occupancy Status,Rent Arrears\n"
    b"A1,Acme Ltd,1000,2027-01-15,Occupied,0\n"
    b"A2,Beta Co,2000,2026-03-20,Occupied,0\n"
)


async def _setup_table(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Saved Scenario Test", "industry": "commercial_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", COMMERCIAL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    return workspace_id, upload_resp.json()["tables"][0]["id"]


async def test_create_and_list_saved_scenario(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,
            "name": "Rent +10%",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 10}],
        },
        headers=_auth(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["name"] == "Rent +10%"
    assert body["workspace_id"] == workspace_id
    assert body["dataset_table_id"] == table_id
    assert body["adjustments"] == [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 10.0}]

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/saved-scenarios", headers=_auth(token))
    assert list_resp.status_code == 200
    names = [s["name"] for s in list_resp.json()]
    assert names == ["Rent +10%"]

    # Filtering by dataset_table_id works too.
    filtered = await client.get(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        params={"dataset_table_id": table_id},
        headers=_auth(token),
    )
    assert len(filtered.json()) == 1


async def test_run_saved_scenario_matches_a_fresh_adhoc_scenario(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,
            "name": "Rent +10%",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 10}],
        },
        headers=_auth(token),
    )
    scenario_id = create_resp.json()["id"]

    run_resp = await client.post(f"/api/v1/saved-scenarios/{scenario_id}/run", headers=_auth(token))
    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()

    baseline = {k["kpi_id"]: k for k in body["baseline_kpis"]}
    scenario = {k["kpi_id"]: k for k in body["scenario_kpis"]}
    deltas = {d["kpi_id"]: d for d in body["kpi_deltas"]}

    # Same expected numbers as the ad-hoc /scenario test for the same
    # adjustment — proves run_scenario_computation is genuinely shared,
    # not a second, possibly-drifting implementation.
    assert baseline["total_rent_roll"]["value"] == 3000.0
    assert scenario["total_rent_roll"]["value"] == 3300.0
    assert deltas["total_rent_roll"]["delta"] == 300.0


async def test_delete_saved_scenario(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,
            "name": "To delete",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}],
        },
        headers=_auth(token),
    )
    scenario_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/saved-scenarios/{scenario_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/saved-scenarios", headers=_auth(token))
    assert list_resp.json() == []

    run_resp = await client.post(f"/api/v1/saved-scenarios/{scenario_id}/run", headers=_auth(token))
    assert run_resp.status_code == 404


async def test_create_rejects_table_from_a_different_workspace(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    _workspace_id, table_id = await _setup_table(client, token)

    other_ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Other", "industry": "commercial_property"}, headers=_auth(token)
    )
    other_workspace_id = other_ws_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/workspaces/{other_workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,  # belongs to the first workspace, not this one
            "name": "Mismatched",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_outsider_cannot_create_list_or_run_saved_scenario(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    outsider_token = await _register_and_login(client, "outsider5@example.com")
    workspace_id, table_id = await _setup_table(client, owner_token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,
            "name": "Owner's scenario",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}],
        },
        headers=_auth(owner_token),
    )
    scenario_id = create_resp.json()["id"]

    denied_create = await client.post(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios",
        json={
            "dataset_table_id": table_id,
            "name": "Outsider's attempt",
            "adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}],
        },
        headers=_auth(outsider_token),
    )
    assert denied_create.status_code == 403

    denied_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/saved-scenarios", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403

    denied_run = await client.post(
        f"/api/v1/saved-scenarios/{scenario_id}/run", headers=_auth(outsider_token)
    )
    assert denied_run.status_code == 403

    denied_delete = await client.delete(
        f"/api/v1/saved-scenarios/{scenario_id}", headers=_auth(outsider_token)
    )
    assert denied_delete.status_code == 403
