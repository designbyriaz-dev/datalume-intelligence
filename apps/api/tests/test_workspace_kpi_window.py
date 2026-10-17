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


async def _create_workspace(client: AsyncClient, token: str, industry: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "KPI Window Test", "industry": industry}, headers=_auth(token)
    )
    return resp.json()["id"]


async def _upload(client: AsyncClient, token: str, workspace_id: str, content: bytes) -> str:
    files = {"file": ("data.csv", content, "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", data={"name": "Data"}, files=files, headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    dataset_id = resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


# Lease ends at +1 day and +3 months from "today" (whatever day the suite
# runs). A 1-month window only catches the first; the 12-month default
# catches both.
COMMERCIAL_CSV = (
    b"Unit,Tenant Name,Rent (PCM),Lease Expiry Date,Occupancy Status,Rent Arrears\n"
    b"A1,Acme Ltd,1200,{soon},Occupied,0\n"
    b"A2,Beta Co,950,{later},Occupied,0\n"
)

# Last inspection at -2 weeks and -2 months from "today". A 1-month window
# makes both overdue; the 12-month default makes neither.
SOCIAL_HOUSING_CSV = (
    b"Property ID,Last Inspection,EPC,Repair Cost,Planned Investment,Void Status\n"
    b"P1,{recent},C,500,2000,Occupied\n"
    b"P2,{less_recent},B,200,0,Occupied\n"
)


def _build_commercial_csv() -> bytes:
    import datetime as dt

    today = dt.date.today()
    soon = today + dt.timedelta(days=20)  # within 1 month
    later = today + dt.timedelta(days=90)  # outside 1 month, inside 12
    return COMMERCIAL_CSV.replace(b"{soon}", soon.isoformat().encode()).replace(
        b"{later}", later.isoformat().encode()
    )


def _build_social_housing_csv() -> bytes:
    import datetime as dt

    today = dt.date.today()
    recent = today - dt.timedelta(days=14)  # not overdue even at a 1-month window
    less_recent = today - dt.timedelta(days=40)  # overdue at a 1-month window, not at 12
    return SOCIAL_HOUSING_CSV.replace(b"{recent}", recent.isoformat().encode()).replace(
        b"{less_recent}", less_recent.isoformat().encode()
    )


async def test_workspace_out_includes_kpi_window_months(client: AsyncClient) -> None:
    token = await _register_and_login(client, "window-get@example.com")
    workspace_id = await _create_workspace(client, token, "commercial_property")

    resp = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["kpi_window_months"] is None


async def test_patch_settings_changes_leases_expiring_kpi(client: AsyncClient) -> None:
    token = await _register_and_login(client, "window-leases@example.com")
    workspace_id = await _create_workspace(client, token, "commercial_property")
    table_id = await _upload(client, token, workspace_id, _build_commercial_csv())

    default_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert default_resp.status_code == 200, default_resp.text
    default_body = default_resp.json()
    assert default_body["window_months_used"] == 12
    default_kpis = {k["kpi_id"]: k for k in default_body["kpis"]}
    assert default_kpis["leases_expiring_12_months"]["value"] == 2

    patch_resp = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings",
        json={"kpi_window_months": 1},
        headers=_auth(token),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["kpi_window_months"] == 1

    narrow_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert narrow_resp.status_code == 200
    narrow_body = narrow_resp.json()
    assert narrow_body["window_months_used"] == 1
    narrow_kpis = {k["kpi_id"]: k for k in narrow_body["kpis"]}
    assert narrow_kpis["leases_expiring_12_months"]["value"] == 1

    reset_resp = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings",
        json={"kpi_window_months": None},
        headers=_auth(token),
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["kpi_window_months"] is None

    reset_kpi_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    reset_kpis = {k["kpi_id"]: k for k in reset_kpi_resp.json()["kpis"]}
    assert reset_kpis["leases_expiring_12_months"]["value"] == 2


async def test_patch_settings_changes_overdue_inspection_kpi(client: AsyncClient) -> None:
    token = await _register_and_login(client, "window-inspection@example.com")
    workspace_id = await _create_workspace(client, token, "social_housing")
    table_id = await _upload(client, token, workspace_id, _build_social_housing_csv())

    default_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    default_kpis = {k["kpi_id"]: k for k in default_resp.json()["kpis"]}
    assert default_kpis["properties_overdue_inspection"]["value"] == 0

    await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings",
        json={"kpi_window_months": 1},
        headers=_auth(token),
    )
    narrow_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    narrow_kpis = {k["kpi_id"]: k for k in narrow_resp.json()["kpis"]}
    assert narrow_kpis["properties_overdue_inspection"]["value"] == 1


async def test_patch_settings_rejects_out_of_range_values(client: AsyncClient) -> None:
    token = await _register_and_login(client, "window-range@example.com")
    workspace_id = await _create_workspace(client, token, "commercial_property")

    too_low = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings", json={"kpi_window_months": 0}, headers=_auth(token)
    )
    assert too_low.status_code == 422

    too_high = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings", json={"kpi_window_months": 61}, headers=_auth(token)
    )
    assert too_high.status_code == 422


async def test_patch_settings_requires_workspace_write_access(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "window-owner@example.com")
    outsider_token = await _register_and_login(client, "window-outsider@example.com")
    workspace_id = await _create_workspace(client, owner_token, "commercial_property")

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings",
        json={"kpi_window_months": 6},
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403
