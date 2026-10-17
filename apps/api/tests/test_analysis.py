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


RENT_ROLL_CSV = (
    b"unit,category,rent,lease_start\n"
    b"A1,office,1200,2023-01-15\n"
    b"A2,office,950,2023-02-20\n"
    b"A3,retail,2000,2023-03-10\n"
    b"A4,retail,2100,2023-04-05\n"
    b"A5,industrial,500,2023-05-12\n"
    b"A6,office,1300,2023-06-18\n"
    b"A7,retail,2200,2023-07-22\n"
    b"A8,industrial,480,2023-08-30\n"
)


async def _setup_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Analytics Test", "industry": "commercial_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]

    files = {"file": ("rent_roll.csv", RENT_ROLL_CSV, "text/csv")}
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


async def test_list_tools_returns_registry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    resp = await client.get("/api/v1/tools", headers=_auth(token))
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert {
        "descriptive_stats",
        "frequency_table",
        "correlation",
        "detect_outliers",
        "group_aggregate",
        "time_trend",
        "simple_forecast",
    } <= names


async def test_descriptive_stats_analysis(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "rent"}},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["operation_type"] == "descriptive_stats"
    assert body["result"]["count"] == 8
    assert body["result"]["sum"] == 1200 + 950 + 2000 + 2100 + 500 + 1300 + 2200 + 480


async def test_group_aggregate_analysis(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={
            "operation": "group_aggregate",
            "parameters": {"group_by": "category", "agg": "sum", "value_column": "rent"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    groups = {g["label"]: g["value"] for g in resp.json()["result"]["groups"]}
    assert groups["office"] == 1200 + 950 + 1300
    assert groups["retail"] == 2000 + 2100 + 2200
    assert groups["industrial"] == 500 + 480


async def test_unknown_operation_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "not_a_real_tool", "parameters": {}},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_invalid_parameters_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    table_id = await _setup_table(client, token)

    # non-numeric column for a numeric-only tool
    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "unit"}},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "not numeric" in resp.json()["detail"].lower()

    # missing required parameter
    resp2 = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "correlation", "parameters": {"column_a": "rent"}},
        headers=_auth(token),
    )
    assert resp2.status_code == 400


async def test_analyses_are_saved_and_listable(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    table_id = await _setup_table(client, token)

    await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "rent"}},
        headers=_auth(token),
    )
    await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "frequency_table", "parameters": {"column": "category"}},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}/analyses", headers=_auth(token))
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2
    operations = {r["operation_type"] for r in runs}
    assert operations == {"descriptive_stats", "frequency_table"}


async def test_outsider_cannot_analyze_or_list(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")
    table_id = await _setup_table(client, owner_token)

    denied_analyze = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "rent"}},
        headers=_auth(outsider_token),
    )
    assert denied_analyze.status_code == 403

    denied_list = await client.get(
        f"/api/v1/dataset-tables/{table_id}/analyses", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403


async def test_time_trend_and_forecast_analysis(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner8@example.com")
    table_id = await _setup_table(client, token)

    trend_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={
            "operation": "time_trend",
            "parameters": {"date_column": "lease_start", "value_column": "rent", "period": "month"},
        },
        headers=_auth(token),
    )
    assert trend_resp.status_code == 201, trend_resp.text
    assert len(trend_resp.json()["result"]["points"]) == 8

    forecast_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={
            "operation": "simple_forecast",
            "parameters": {"date_column": "lease_start", "value_column": "rent", "periods_ahead": 2},
        },
        headers=_auth(token),
    )
    assert forecast_resp.status_code == 201, forecast_resp.text
    result = forecast_resp.json()["result"]
    assert len(result["forecast_points"]) == 2
    assert "caveat" in result
