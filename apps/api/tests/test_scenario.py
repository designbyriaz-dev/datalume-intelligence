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


async def _setup_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Scenario Test", "industry": "commercial_property"},
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
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_scenario_percentage_rent_increase(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/scenario",
        json={"adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 10}]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    baseline = {k["kpi_id"]: k for k in body["baseline_kpis"]}
    scenario = {k["kpi_id"]: k for k in body["scenario_kpis"]}
    deltas = {d["kpi_id"]: d for d in body["kpi_deltas"]}

    assert baseline["total_rent_roll"]["value"] == 3000.0
    assert scenario["total_rent_roll"]["value"] == 3300.0
    assert deltas["total_rent_roll"]["delta"] == 300.0
    assert deltas["total_rent_roll"]["pct_change"] == 10.0

    # Occupancy rate is unaffected by a rent change — delta should be 0.
    assert deltas["occupancy_rate"]["delta"] == 0.0


async def test_scenario_rejects_invalid_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/scenario",
        json={"adjustments": [{"column": "not_a_column", "adjustment_type": "percentage", "value": 5}]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_scenario_requires_industry_pack(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "General", "industry": "general"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", COMMERCIAL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    table_id = version["tables"][0]["id"]

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/scenario",
        json={"adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_scenario_consumes_analysis_quota(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    table_id = await _setup_table(client, token)

    for i in range(3):
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/scenario",
            json={"adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 1}]},
            headers=_auth(token),
        )
        assert resp.status_code == 200, f"call {i}: {resp.text}"

    blocked = await client.post(
        f"/api/v1/dataset-tables/{table_id}/scenario",
        json={"adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 1}]},
        headers=_auth(token),
    )
    assert blocked.status_code == 402


async def test_outsider_cannot_run_scenario(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    outsider_token = await _register_and_login(client, "outsider5@example.com")
    table_id = await _setup_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/scenario",
        json={"adjustments": [{"column": "Rent (PCM)", "adjustment_type": "percentage", "value": 5}]},
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403
