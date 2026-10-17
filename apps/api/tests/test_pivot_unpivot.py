"""Pivot and unpivot — the last two of the brief's originally-listed
cleaning operations. Unlike every other cleaning operation, pivot
replaces the table's column set entirely rather than adding to or
filtering it (the row grouping itself changes) — that's inherent to
what "pivot" means, documented in apply_pivot's own docstring, not a
limitation of this implementation."""

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
    """Parsing/profiling happen in a background task after the upload
    response is sent (see finish_ingest_upload in
    app/services/datasets.py) — re-fetch to find the table it created."""
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


# --- pivot ---------------------------------------------------------------

PIVOT_CSV = (
    b"date,category,amount\n"
    b"2026-01,rent,1000\n"
    b"2026-01,fees,50\n"
    b"2026-02,rent,1100\n"
    b"2026-02,fees,60\n"
    b"2026-01,rent,200\n"  # duplicate (2026-01, rent) combo — exercises aggregation
)


async def test_pivot_creates_wide_table_with_aggregation(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", PIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={"index_columns": ["date"], "pivot_column": "category", "value_column": "amount"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables"][0]["row_count"] == 2  # 2026-01, 2026-02
    columns = _columns_by_name(body)
    assert {"date", "rent", "fees"} == columns.keys()


async def test_pivot_with_mean_aggregate_function(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", PIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={
            "index_columns": ["date"],
            "pivot_column": "category",
            "value_column": "amount",
            "aggregate_function": "mean",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text


async def test_pivot_rejects_invalid_aggregate_function(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", PIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={
            "index_columns": ["date"],
            "pivot_column": "category",
            "value_column": "amount",
            "aggregate_function": "nonsense",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_pivot_rejects_too_many_distinct_values(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    rows = [f"row{i},cat{i},1" for i in range(51)]
    csv = ("date,category,amount\n" + "\n".join(rows) + "\n").encode()
    table_id = await _upload_csv(client, token, workspace_id, "Data", csv)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={"index_columns": ["date"], "pivot_column": "category", "value_column": "amount"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "distinct values" in resp.json()["detail"].lower()


async def test_pivot_column_name_collision_rejected(client: AsyncClient) -> None:
    """A pivoted category value that happens to equal an index column
    name (e.g. a category literally called "date") is a genuine
    collision polars itself rejects — surfaced as a clean 400, not a
    500."""
    token = await _register_and_login(client, "pivot5@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    csv = b"date,category,amount\n2026-01,date,1\n2026-01,fees,2\n"
    table_id = await _upload_csv(client, token, workspace_id, "Data", csv)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={"index_columns": ["date"], "pivot_column": "category", "value_column": "amount"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_pivot_rejects_unknown_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot6@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", PIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={"index_columns": ["not_a_column"], "pivot_column": "category", "value_column": "amount"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "unknown column" in resp.json()["detail"].lower()


async def test_pivot_preserves_original_version(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pivot7@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", PIVOT_CSV)

    await client.post(
        f"/api/v1/dataset-tables/{table_id}/pivot",
        json={"index_columns": ["date"], "pivot_column": "category", "value_column": "amount"},
        headers=_auth(token),
    )

    dataset_id = await _dataset_id(client, token, workspace_id)
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    original = next(v for v in detail["versions"] if v["version_number"] == 1)
    assert original["tables"][0]["column_count"] == 3  # date, category, amount — untouched


# --- unpivot ---------------------------------------------------------------

UNPIVOT_CSV = b"id,jan,feb\n1,100,110\n2,200,210\n"


async def test_unpivot_creates_long_table(client: AsyncClient) -> None:
    token = await _register_and_login(client, "unpivot1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", UNPIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/unpivot",
        json={"id_columns": ["id"], "value_columns": ["jan", "feb"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables"][0]["row_count"] == 4  # 2 ids * 2 months
    columns = _columns_by_name(body)
    assert {"id", "variable", "value"} == columns.keys()


async def test_unpivot_with_custom_names(client: AsyncClient) -> None:
    token = await _register_and_login(client, "unpivot2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", UNPIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/unpivot",
        json={
            "id_columns": ["id"],
            "value_columns": ["jan", "feb"],
            "variable_name": "month",
            "value_name": "amount",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    columns = _columns_by_name(resp.json())
    assert {"id", "month", "amount"} == columns.keys()


async def test_unpivot_rejects_overlapping_id_and_value_columns(client: AsyncClient) -> None:
    token = await _register_and_login(client, "unpivot3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", UNPIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/unpivot",
        json={"id_columns": ["id", "jan"], "value_columns": ["jan", "feb"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "both id_columns and value_columns" in resp.json()["detail"]


async def test_unpivot_rejects_variable_name_collision_with_id_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "unpivot4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", UNPIVOT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/unpivot",
        json={"id_columns": ["id"], "value_columns": ["jan", "feb"], "variable_name": "id"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "collides with an id column" in resp.json()["detail"]


async def test_unpivot_preserves_original_version(client: AsyncClient) -> None:
    token = await _register_and_login(client, "unpivot5@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", UNPIVOT_CSV)

    await client.post(
        f"/api/v1/dataset-tables/{table_id}/unpivot",
        json={"id_columns": ["id"], "value_columns": ["jan", "feb"]},
        headers=_auth(token),
    )

    dataset_id = await _dataset_id(client, token, workspace_id)
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    original = next(v for v in detail["versions"] if v["version_number"] == 1)
    assert original["tables"][0]["row_count"] == 2  # untouched
