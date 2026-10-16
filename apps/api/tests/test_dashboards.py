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
)

GENERAL_CSV = b"product,region,units_sold,revenue\nWidget,North,10,1000\nWidget,South,5,500\nGadget,North,8,1600\n"


async def _setup_table(client: AsyncClient, token: str, industry: str, content: bytes) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Dashboard Test", "industry": industry}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", content, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    table_id = upload_resp.json()["tables"][0]["id"]
    return workspace_id, table_id


async def test_auto_generate_commercial_property_dashboard(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    workspace_id, table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards/auto-generate",
        json={"name": "Portfolio Overview", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Portfolio Overview"
    assert len(body["widgets"]) == 8  # one per commercial property KPI

    rent_roll = next(w for w in body["widgets"] if w["config"].get("kpi_id") == "total_rent_roll")
    assert rent_roll["value"]["value"] == 4150.0
    assert rent_roll["value"]["formatted"] == "£4,150.00"


async def test_auto_generate_general_dashboard_uses_profile_heuristics(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id, table_id = await _setup_table(client, token, "general", GENERAL_CSV)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards/auto-generate",
        json={"name": "Sales Overview", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["widgets"]) > 0
    assert all(w["widget_type"] == "chart" for w in body["widgets"])
    assert all(w["value"]["error"] is None for w in body["widgets"])


async def test_manual_dashboard_crud_lifecycle(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    workspace_id, table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "My Dashboard", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    dashboard_id = create_resp.json()["id"]
    assert create_resp.json()["widgets"] == []

    add_resp = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        json={"widget_type": "kpi", "title": "Rent Roll", "config": {"kpi_id": "total_rent_roll"}},
        headers=_auth(token),
    )
    assert add_resp.status_code == 201
    widgets = add_resp.json()["widgets"]
    assert len(widgets) == 1
    assert widgets[0]["value"]["value"] == 4150.0

    add_resp2 = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        json={
            "widget_type": "chart",
            "title": "Rent by unit",
            "config": {"operation": "group_aggregate", "parameters": {"group_by": "Unit", "agg": "sum", "value_column": "Rent (PCM)"}},
        },
        headers=_auth(token),
    )
    assert add_resp2.status_code == 201
    widget_id_to_remove = add_resp2.json()["widgets"][0]["id"]

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/dashboards", headers=_auth(token))
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["widget_count"] == 2

    delete_widget_resp = await client.delete(
        f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id_to_remove}", headers=_auth(token)
    )
    assert delete_widget_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert len(get_resp.json()["widgets"]) == 1

    delete_dashboard_resp = await client.delete(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert delete_dashboard_resp.status_code == 204

    final_get = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert final_get.status_code == 404


async def test_invalid_kpi_widget_reports_error_without_failing_whole_dashboard(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    workspace_id, table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    dashboard_id = create_resp.json()["id"]

    await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        json={"widget_type": "kpi", "title": "Bad", "config": {"kpi_id": "not_a_real_kpi"}},
        headers=_auth(token),
    )
    await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        json={"widget_type": "kpi", "title": "Good", "config": {"kpi_id": "total_rent_roll"}},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert resp.status_code == 200
    widgets = {w["title"]: w for w in resp.json()["widgets"]}
    assert "error" in widgets["Bad"]["value"]
    assert widgets["Good"]["value"]["value"] == 4150.0


async def test_outsider_cannot_access_dashboards(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    outsider_token = await _register_and_login(client, "outsider5@example.com")
    workspace_id, table_id = await _setup_table(client, owner_token, "commercial_property", COMMERCIAL_CSV)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(owner_token),
    )
    dashboard_id = create_resp.json()["id"]

    assert (await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(outsider_token))).status_code == 403
    assert (
        await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "kpi", "title": "X", "config": {"kpi_id": "total_rent_roll"}},
            headers=_auth(outsider_token),
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/dashboards/{dashboard_id}/widgets/reorder",
            json={"widget_ids": []},
            headers=_auth(outsider_token),
        )
    ).status_code in (403, 422)  # 422 if the empty list fails validation before auth would even matter


async def test_reorder_widgets_persists_new_order(client: AsyncClient) -> None:
    token = await _register_and_login(client, "reorderowner@example.com")
    workspace_id, table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    dashboard_id = create_resp.json()["id"]

    widget_ids = []
    for kpi_id in ("total_rent_roll", "average_rent", "occupancy_rate"):
        resp = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "kpi", "title": kpi_id, "config": {"kpi_id": kpi_id}},
            headers=_auth(token),
        )
        widget_ids.append(resp.json()["widgets"][-1]["id"])

    # Original order is creation order: [rent_roll, average_rent, occupancy].
    get_resp = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert [w["id"] for w in get_resp.json()["widgets"]] == widget_ids

    reversed_order = list(reversed(widget_ids))
    reorder_resp = await client.patch(
        f"/api/v1/dashboards/{dashboard_id}/widgets/reorder",
        json={"widget_ids": reversed_order},
        headers=_auth(token),
    )
    assert reorder_resp.status_code == 200, reorder_resp.text
    assert [w["id"] for w in reorder_resp.json()["widgets"]] == reversed_order

    # Persisted, not just reflected in the response — a fresh GET agrees.
    get_resp2 = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert [w["id"] for w in get_resp2.json()["widgets"]] == reversed_order


async def test_reorder_rejects_a_widget_set_that_does_not_match(client: AsyncClient) -> None:
    token = await _register_and_login(client, "reorderowner2@example.com")
    workspace_id, table_id = await _setup_table(client, token, "commercial_property", COMMERCIAL_CSV)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(token),
    )
    dashboard_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        json={"widget_type": "kpi", "title": "A", "config": {"kpi_id": "total_rent_roll"}},
        headers=_auth(token),
    )
    widget_id = add_resp.json()["widgets"][0]["id"]

    # Missing the one real widget entirely.
    missing_resp = await client.patch(
        f"/api/v1/dashboards/{dashboard_id}/widgets/reorder",
        json={"widget_ids": []},
        headers=_auth(token),
    )
    assert missing_resp.status_code in (400, 422)

    # Includes an id that doesn't belong to this dashboard.
    bogus_resp = await client.patch(
        f"/api/v1/dashboards/{dashboard_id}/widgets/reorder",
        json={"widget_ids": [widget_id, "not-a-real-widget-id"]},
        headers=_auth(token),
    )
    assert bogus_resp.status_code == 400

    # Duplicates the one real widget instead of listing it once.
    dup_resp = await client.patch(
        f"/api/v1/dashboards/{dashboard_id}/widgets/reorder",
        json={"widget_ids": [widget_id, widget_id]},
        headers=_auth(token),
    )
    assert dup_resp.status_code == 400

    # None of the above should have changed anything.
    get_resp = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(token))
    assert len(get_resp.json()["widgets"]) == 1
