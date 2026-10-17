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
    b"A1,Acme Ltd,1200,2027-01-15,Occupied,0\n"
    b"A2,Beta Co,950,2026-03-20,Occupied,100\n"
    b"A3,Acme Ltd,2000,2026-11-10,Vacant,0\n"
    b"A4,Gamma Inc,2100,2030-01-01,Occupied,50\n"
    b"A5,Delta PLC,500,2025-06-01,Occupied,0\n"
)


async def _setup_table(client: AsyncClient, token: str, industry: str, content: bytes) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Industry Test", "industry": industry}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", content, "text/csv")}
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


async def test_list_industry_packs(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    resp = await client.get("/api/v1/industry-packs", headers=_auth(token))
    assert resp.status_code == 200
    ids = {p["industry_id"] for p in resp.json()}
    assert ids == {
        "commercial_property",
        "residential_property",
        "social_housing",
        "business_finance",
        "public_sector",
    }

    commercial = next(p for p in resp.json() if p["industry_id"] == "commercial_property")
    assert len(commercial["kpis"]) == 8
    assert len(commercial["suggested_questions"]) > 0
    assert "Rent Roll" in commercial["terminology"]


async def test_unknown_industry_pack_404s(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    resp = await client.get("/api/v1/industry-packs/not_a_real_industry", headers=_auth(token))
    assert resp.status_code == 404


async def test_compute_commercial_property_kpis_end_to_end(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["industry_id"] == "commercial_property"
    assert body["missing_required_fields"] == []
    assert body["field_mapping"]["rent_amount"] == "Rent (PCM)"

    kpis = {k["kpi_id"]: k for k in body["kpis"]}
    assert kpis["total_rent_roll"]["value"] == 6750.0
    assert kpis["occupancy_rate"]["value"] == 80.0
    assert all(k["error"] is None for k in kpis.values())

    # It was saved as an AnalysisRun and shows up in the existing list endpoint.
    analyses_resp = await client.get(f"/api/v1/dataset-tables/{table_id}/analyses", headers=_auth(token))
    operations = {a["operation_type"] for a in analyses_resp.json()}
    assert "industry_kpis:commercial_property" in operations


async def test_general_workspace_has_no_industry_pack(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    table_id = await _setup_table(client, token, "general", COMMERCIAL_CSV)

    resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert resp.status_code == 400
    assert "no industry pack" in resp.json()["detail"].lower()


async def test_social_housing_response_includes_compliance_caveat(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    csv = (
        b"Property ID,Last Inspection,EPC,Repair Cost,Planned Investment,Void Status\n"
        b"P1,2025-01-01,C,500,2000,Occupied\n"
        b"P2,2026-09-01,B,200,0,Void\n"
    )
    table_id = await _setup_table(client, token, "social_housing", csv)

    resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert resp.status_code == 200
    assert "do not constitute legal compliance" in resp.json()["compliance_caveat"].lower()


async def test_industry_kpis_consume_analysis_quota(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    # Free plan allows 3 analyses/month.
    for i in range(3):
        resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
        assert resp.status_code == 200, f"call {i}: {resp.text}"

    blocked = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert blocked.status_code == 402


async def test_missing_required_fields_reported_but_available_kpis_still_computed(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner7@example.com")
    csv = b"Unit,Rent\nA1,1000\nA2,2000\n"
    table_id = await _setup_table(client, token, "commercial_property", csv)

    resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["missing_required_fields"]) >= {"tenant", "lease_end_date", "status"}

    kpis = {k["kpi_id"]: k for k in body["kpis"]}
    assert kpis["total_rent_roll"]["value"] == 3000.0
    assert kpis["occupancy_rate"]["error"] is not None


async def test_outsider_cannot_compute_industry_kpis(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner8@example.com")
    outsider_token = await _register_and_login(client, "outsider8@example.com")
    table_id = await _setup_table(client, owner_token, "commercial_property", COMMERCIAL_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(outsider_token)
    )
    assert resp.status_code == 403
