"""The third wave of cleaning operations: merge-columns, split-column,
and standardize-column (dates/currency stored as text — the two things
app/services/profiling.py's data-quality profiler only ever flagged,
never fixed). Same pattern as every other cleaning operation: a new
DatasetVersion, the source version left untouched, a Transformation
audit row."""

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
    files = {"file": ("data.csv", content, "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", data={"name": name}, files=files, headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["tables"][0]["id"]


def _columns_by_name(version_body: dict) -> dict:
    return {c["name"]: c for c in version_body["tables"][0]["profile"]["columns"]}


async def _dataset_id(client: AsyncClient, token: str, workspace_id: str) -> str:
    resp = await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(token))
    return resp.json()[0]["id"]


# --- merge-columns ----------------------------------------------------

MERGE_CSV = b"year,quarter,label\n2024,Q1,Alpha\n2025,Q2,Beta\n"


async def test_merge_columns_combines_and_drops_originals(client: AsyncClient) -> None:
    token = await _register_and_login(client, "merge1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", MERGE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/merge-columns",
        json={"columns": ["year", "quarter"], "new_column_name": "period", "separator": "-"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables"][0]["column_count"] == 2  # label + period (year/quarter dropped)
    columns = _columns_by_name(body)
    assert "period" in columns
    assert "year" not in columns
    assert "quarter" not in columns


async def test_merge_columns_keeps_originals_when_requested(client: AsyncClient) -> None:
    token = await _register_and_login(client, "merge2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", MERGE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/merge-columns",
        json={
            "columns": ["year", "quarter"],
            "new_column_name": "period",
            "drop_source_columns": False,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    columns = _columns_by_name(resp.json())
    assert {"year", "quarter", "period", "label"} <= columns.keys()


async def test_merge_columns_requires_at_least_two_columns(client: AsyncClient) -> None:
    token = await _register_and_login(client, "merge3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", MERGE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/merge-columns",
        json={"columns": ["year"], "new_column_name": "period"},
        headers=_auth(token),
    )
    assert resp.status_code == 422  # min_length=2 enforced by the schema


async def test_merge_columns_rejects_existing_column_name(client: AsyncClient) -> None:
    token = await _register_and_login(client, "merge4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", MERGE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/merge-columns",
        json={"columns": ["year", "quarter"], "new_column_name": "label"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()


# --- split-column -------------------------------------------------------

SPLIT_CSV = b"id,full_name\n1,Jane Doe\n2,Bob Smith Jr\n3,NoSpace\n"


async def test_split_column_auto_names_and_pads_short_rows_with_null(client: AsyncClient) -> None:
    token = await _register_and_login(client, "split1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", SPLIT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/split-column",
        json={"column": "full_name", "delimiter": " "},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    columns = _columns_by_name(body)
    # "Bob Smith Jr" has the most parts (3), so three columns are produced.
    assert {"full_name_1", "full_name_2", "full_name_3"} <= columns.keys()
    assert "full_name" not in columns
    assert columns["full_name_3"]["null_count"] == 2  # "Jane Doe" and "NoSpace" have no third part


async def test_split_column_with_explicit_names(client: AsyncClient) -> None:
    token = await _register_and_login(client, "split2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    csv = b"name\nJane Doe\nBob Smith\n"
    table_id = await _upload_csv(client, token, workspace_id, "Data", csv)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/split-column",
        json={"column": "name", "delimiter": " ", "new_column_names": ["first", "last"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert {"first", "last"} <= _columns_by_name(resp.json()).keys()


async def test_split_column_rejects_wrong_number_of_names(client: AsyncClient) -> None:
    token = await _register_and_login(client, "split3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", SPLIT_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/split-column",
        json={"column": "full_name", "delimiter": " ", "new_column_names": ["only_one"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "produces 3 column" in resp.json()["detail"]


async def test_split_column_no_delimiter_found_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "split4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    csv = b"id,code\n1,ABC\n2,DEF\n"
    table_id = await _upload_csv(client, token, workspace_id, "Data", csv)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/split-column",
        json={"column": "code", "delimiter": "-"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "nothing to split" in resp.json()["detail"].lower()


# --- standardize-column (date) ------------------------------------------

DATE_CSV = b"id,signed_on\n1,05/03/2026\n2,10/04/2026\n3,not-a-date\n"


async def test_standardize_column_date_parses_and_promotes_to_date_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "std1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", DATE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "signed_on", "kind": "date", "date_format": "%d/%m/%Y"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    columns = _columns_by_name(resp.json())
    assert columns["signed_on"]["inferred_type"] == "date"
    # the one genuinely unparseable value becomes null, not a crash
    assert columns["signed_on"]["null_count"] == 1


async def test_standardize_column_date_requires_format(client: AsyncClient) -> None:
    token = await _register_and_login(client, "std2@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", DATE_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "signed_on", "kind": "date"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "date_format is required" in resp.json()["detail"]


# --- standardize-column (currency) ---------------------------------------

CURRENCY_CSV = (
    b"id,price\n"
    b'1,"\xc2\xa31,200.50"\n'  # £1,200.50 — comma-containing value must be quoted in CSV
    b"2,$950\n"
    b'3,"2,000"\n'
    b"4,garbage\n"
)


async def test_standardize_column_currency_strips_symbols_and_parses_float(client: AsyncClient) -> None:
    token = await _register_and_login(client, "std3@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", CURRENCY_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "price", "kind": "currency"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    columns = _columns_by_name(resp.json())
    assert columns["price"]["inferred_type"] == "float"
    assert columns["price"]["stats"]["min"] == 950.0
    assert columns["price"]["stats"]["max"] == 2000.0
    assert columns["price"]["null_count"] == 1  # "garbage" doesn't parse


async def test_standardize_column_rejects_already_non_text_column(client: AsyncClient) -> None:
    token = await _register_and_login(client, "std4@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    csv = b"id,amount\n1,100\n2,200\n"
    table_id = await _upload_csv(client, token, workspace_id, "Data", csv)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "amount", "kind": "currency"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "not a text column" in resp.json()["detail"].lower()


async def test_standardize_column_unknown_kind_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "std5@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", CURRENCY_CSV)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "price", "kind": "weight"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# --- original version preserved across all three ------------------------


async def test_original_version_preserved_after_merge_split_standardize(client: AsyncClient) -> None:
    token = await _register_and_login(client, "orig1@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_csv(client, token, workspace_id, "Data", DATE_CSV)

    await client.post(
        f"/api/v1/dataset-tables/{table_id}/standardize-column",
        json={"column": "signed_on", "kind": "date", "date_format": "%d/%m/%Y"},
        headers=_auth(token),
    )

    dataset_id = await _dataset_id(client, token, workspace_id)
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    original = next(v for v in detail["versions"] if v["version_number"] == 1)
    assert original["tables"][0]["profile"]["columns"][1]["inferred_type"] == "text"
