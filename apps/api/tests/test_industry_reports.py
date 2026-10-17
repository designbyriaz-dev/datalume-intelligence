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
    b"Unit,Tenant Name,Rent (PCM),Lease Expiry Date,Occupancy Status,Rent Arrears,Use Class\n"
    b"A1,Acme Ltd,1200,2027-01-15,Occupied,0,Office\n"
    b"A2,Beta Co,950,2026-03-20,Occupied,100,Office\n"
    b"A3,Acme Ltd,2000,2026-11-10,Vacant,0,Retail\n"
    b"A4,Gamma Inc,2100,2030-01-01,Occupied,50,Industrial\n"
    b"A5,Delta PLC,500,2025-06-01,Occupied,0,Retail\n"
)


async def _setup_table(client: AsyncClient, token: str, industry: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Report Test", "industry": industry}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", COMMERCIAL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_generate_and_download_commercial_property_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    table_id = await _setup_table(client, token, "commercial_property")

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/commercial-property-portfolio", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "commercial_property_portfolio"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_report_rejected_for_wrong_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/commercial-property-portfolio", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "commercial_property" in resp.json()["detail"]


async def test_outsider_cannot_generate_commercial_property_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    outsider_token = await _register_and_login(client, "outsider3@example.com")
    table_id = await _setup_table(client, owner_token, "commercial_property")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/commercial-property-portfolio",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


RESIDENTIAL_CSV = (
    b"Property,Tenant Name,Rent PCM,Occupancy Status,Tenancy End Date,Rent Arrears,Maintenance Cost\n"
    b"Flat 1,Jane Doe,950,Occupied,2027-01-15,0,120\n"
    b"Flat 2,Bob Smith,850,Occupied,2026-03-20,150,0\n"
    b"Flat 3,,0,Vacant,,0,300\n"
    b"Flat 4,Alice Brown,1100,Occupied,2030-01-01,0,0\n"
)


async def _setup_residential_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Residential Report Test", "industry": "residential_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", RESIDENTIAL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_generate_and_download_residential_property_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "resowner@example.com")
    table_id = await _setup_residential_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-property-portfolio", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "residential_property_portfolio"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_residential_report_rejected_for_wrong_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "resowner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-property-portfolio", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "residential_property" in resp.json()["detail"]


async def test_residential_report_rejected_for_commercial_workspace(client: AsyncClient) -> None:
    """Cross-pack rejection, not just "any non-matching industry" —
    residential_property's report must not be generatable in a
    commercial_property workspace either."""
    token = await _register_and_login(client, "resowner3@example.com")
    table_id = await _setup_table(client, token, "commercial_property")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-property-portfolio", headers=_auth(token)
    )
    assert resp.status_code == 400


async def test_outsider_cannot_generate_residential_property_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "resowner4@example.com")
    outsider_token = await _register_and_login(client, "resoutsider4@example.com")
    table_id = await _setup_residential_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-property-portfolio",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


async def test_generate_and_download_residential_repairs_maintenance_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rmowner@example.com")
    table_id = await _setup_residential_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-repairs-maintenance", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "residential_repairs_maintenance"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_residential_repairs_maintenance_report_rejected_for_wrong_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rmowner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-repairs-maintenance", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "residential_property" in resp.json()["detail"]


async def test_outsider_cannot_generate_residential_repairs_maintenance_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "rmowner3@example.com")
    outsider_token = await _register_and_login(client, "rmoutsider3@example.com")
    table_id = await _setup_residential_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/residential-repairs-maintenance",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


SOCIAL_HOUSING_CSV = (
    b"Property,Stock Type,EPC Rating,Last Inspection Date,Repair Cost,Planned Investment,Void Status\n"
    b"Flat 1,House,C,2023-01-01,500,2000,Occupied\n"
    b"Flat 2,Flat,B,2026-09-01,100,0,Occupied\n"
    b"Flat 3,Bungalow,D,2022-06-15,800,5000,Void\n"
)


async def _setup_social_housing_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Social Housing Report Test", "industry": "social_housing"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", SOCIAL_HOUSING_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Stock List"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_generate_and_download_social_housing_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "showner@example.com")
    table_id = await _setup_social_housing_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-asset", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "social_housing_asset"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_social_housing_report_rejected_for_wrong_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "showner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-asset", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "social_housing" in resp.json()["detail"]


async def test_outsider_cannot_generate_social_housing_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "showner3@example.com")
    outsider_token = await _register_and_login(client, "shoutsider3@example.com")
    table_id = await _setup_social_housing_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-asset",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


async def test_generate_and_download_social_housing_compliance_exceptions_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "shceowner@example.com")
    table_id = await _setup_social_housing_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-compliance-exceptions", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "social_housing_compliance_exceptions"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_social_housing_compliance_exceptions_report_rejected_for_wrong_industry(
    client: AsyncClient,
) -> None:
    token = await _register_and_login(client, "shceowner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-compliance-exceptions", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "social_housing" in resp.json()["detail"]


async def test_outsider_cannot_generate_social_housing_compliance_exceptions_report(
    client: AsyncClient,
) -> None:
    owner_token = await _register_and_login(client, "shceowner3@example.com")
    outsider_token = await _register_and_login(client, "shceoutsider3@example.com")
    table_id = await _setup_social_housing_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/social-housing-compliance-exceptions",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


BUSINESS_FINANCE_CSV = (
    b"Date,Revenue,Expenses,Category,Customer\n"
    b"2026-01-15,10000,4000,Consulting,Acme Ltd\n"
    b"2026-01-20,5000,2000,Products,Beta Co\n"
    b"2026-02-10,12000,4500,Consulting,Acme Ltd\n"
    b"2026-02-15,3000,1000,Products,Gamma Inc\n"
)


async def _setup_business_finance_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Business Finance Report Test", "industry": "business_finance"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", BUSINESS_FINANCE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Transactions"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_generate_and_download_business_finance_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "bfowner@example.com")
    table_id = await _setup_business_finance_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/business-performance", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "business_performance"

    download_resp = await client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content.startswith(b"%PDF-")


async def test_business_finance_report_rejected_for_wrong_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "bfowner2@example.com")
    table_id = await _setup_table(client, token, "general")

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/business-performance", headers=_auth(token)
    )
    assert resp.status_code == 400
    assert "business_finance" in resp.json()["detail"]


async def test_outsider_cannot_generate_business_finance_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "bfowner3@example.com")
    outsider_token = await _register_and_login(client, "bfoutsider3@example.com")
    table_id = await _setup_business_finance_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/business-performance",
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403
