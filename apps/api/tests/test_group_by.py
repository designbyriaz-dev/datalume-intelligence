"""Persisted group-by — the version-producing counterpart to the
read-only `group_aggregate` analytics tool (Phase 3), which only ever
returns a single aggregation as a query result, never a new table. The
last cleaning operation named in the brief's "filter/group" pairing
(filter-rows was built earlier)."""

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


async def _create_personal_workspace(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Test Workspace", "industry": "general"}, headers=_auth(token)
    )
    return resp.json()["id"]


async def _upload_csv(client: AsyncClient, token: str, workspace_id: str, name: str, content: bytes) -> str:
    """Parsing/profiling now happen in a background task after the
    upload response is sent (see finish_ingest_upload in
    app/services/datasets.py) — that response's own tables list is
    always empty, so this re-fetches the dataset to find the table the
    background task already created by the time the upload response
    was received (confirmed: Starlette runs BackgroundTasks before
    client.post() returns, even under this test's in-process transport
    — no retry loop needed here)."""
    files = {"file": ("data.csv", content, "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", data={"name": name}, files=files, headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    dataset_id = resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


def _columns_by_name(version_body: dict) -> dict:
    return {c["name"]: c for c in version_body["tables"][0]["profile"]["columns"]}


async def _dataset_id(client: AsyncClient, token: str, workspace_id: str) -> str:
    resp = await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(token))
    return resp.json()[0]["id"]


GROUP_CSV = (
    b"category,amount,region\n"
    b"rent,1000,north\n"
    b"rent,1200,south\n"
    b"fees,50,north\n"
    b"fees,60,north\n"
    b"fees,70,south\n"
)


async def test_group_by_single_column_sum_and_count(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [
                {"column": "amount", "function": "sum", "output_name": "total_amount"},
                {"function": "count", "output_name": "row_count"},
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables"][0]["row_count"] == 2  # rent, fees
    columns = _columns_by_name(body)
    assert {"category", "total_amount", "row_count"} == columns.keys()


async def test_group_by_multiple_group_columns(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category", "region"],
            "aggregations": [{"column": "amount", "function": "sum", "output_name": "total_amount"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables"][0]["row_count"] == 4  # rent/north, rent/south, fees/north, fees/south
    assert {"category", "region", "total_amount"} == _columns_by_name(body).keys()


async def test_group_by_mean_aggregation(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"column": "amount", "function": "mean", "output_name": "avg_amount"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text


async def test_group_by_rejects_non_numeric_column_for_sum(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"column": "region", "function": "sum", "output_name": "x"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "not numeric" in resp.json()["detail"].lower()


async def test_group_by_rejects_unknown_group_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group5@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["not_a_column"],
            "aggregations": [{"function": "count", "output_name": "row_count"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "unknown column" in resp.json()["detail"].lower()


async def test_group_by_rejects_unknown_aggregation_function(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group6@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"column": "amount", "function": "nonsense", "output_name": "x"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_group_by_rejects_output_name_colliding_with_group_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group7@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"column": "amount", "function": "sum", "output_name": "category"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "colliding" in resp.json()["detail"].lower()


async def test_group_by_requires_column_for_non_count_function(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group8@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"function": "sum", "output_name": "x"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_group_by_preserves_original_version(client: AsyncClient) -> None:
    token = await _register_and_login(client, "group9@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", GROUP_CSV)

    await client.post(
        f"/api/v1/dataset-tables/{table_id}/group-by",
        json={
            "group_by_columns": ["category"],
            "aggregations": [{"function": "count", "output_name": "row_count"}],
        },
        headers=_auth(token),
    )

    dataset_id = await _dataset_id(client, token, workspace_id)
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    original = next(v for v in detail["versions"] if v["version_number"] == 1)
    assert original["tables"][0]["row_count"] == 5  # untouched
