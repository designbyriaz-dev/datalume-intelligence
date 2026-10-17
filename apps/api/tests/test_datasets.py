import io

import openpyxl
import pytest
from httpx import AsyncClient

from app.core.config import get_settings


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
        "/api/v1/workspaces",
        json={"name": "Test Workspace", "industry": "general"},
        headers=_auth(token),
    )
    return resp.json()["id"]


SAMPLE_CSV = (
    b"name,age,signup_date,salary\n"
    b"Jane,34,2024-01-15,50000\n"
    b"Jane,34,2024-01-15,50000\n"  # exact duplicate of row above
    b"Bob,,2024-02-20,62000.50\n"
    b"Alice,29,2024-03-10,\n"
)


async def _upload_and_get_ready_version(
    client: AsyncClient,
    token: str,
    workspace_id: str,
    filename: str,
    content: bytes,
    content_type: str = "text/csv",
    name: str = "Data",
) -> dict:
    """Uploads a file and returns the fully-processed DatasetVersion
    dict (status="ready", tables populated) — not the raw POST response,
    which now only reflects status="processing" with no tables yet,
    since parsing/profiling happens in a background task scheduled by
    the endpoint (see finish_ingest_upload in app/services/datasets.py).
    No retry loop needed here: confirmed empirically that Starlette
    runs BackgroundTasks before the ASGI call itself returns, so under
    this client's in-process ASGITransport the background task has
    already completed by the time client.post() returns — this is a
    single immediate re-fetch, not polling."""
    files = {"file": (filename, content, content_type)}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": name},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    assert upload_resp.json()["status"] == "processing"
    dataset_id = upload_resp.json()["dataset_id"]

    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version


def _build_sample_xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheets.items():
        ws = wb.create_sheet(sheet_name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_upload_csv_profiles_correctly(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    body = await _upload_and_get_ready_version(
        client, token, workspace_id, "rent_roll.csv", SAMPLE_CSV, name="Rent Roll"
    )
    assert body["version_number"] == 1
    assert len(body["tables"]) == 1

    table = body["tables"][0]
    assert table["row_count"] == 4
    assert table["column_count"] == 4
    profile = table["profile"]
    assert profile["duplicate_row_count"] == 1
    assert 0 < profile["quality_score"] <= 100

    columns_by_name = {c["name"]: c for c in profile["columns"]}
    assert columns_by_name["age"]["inferred_type"] == "integer"
    assert columns_by_name["age"]["null_count"] == 1
    assert columns_by_name["salary"]["inferred_type"] == "float"
    assert columns_by_name["salary"]["null_count"] == 1

    issue_types = {i["issue_type"] for i in profile["issues"]}
    assert "duplicate_rows" in issue_types
    assert "missing_values" in issue_types


async def test_upload_returns_processing_immediately_then_becomes_ready(client: AsyncClient) -> None:
    """The actual async behaviour, not just the end state: the raw POST
    response must reflect status="processing" with no tables yet — it's
    serialized before finish_ingest_upload (the background task) runs,
    only after the response is sent. Everything else in this file uses
    _upload_and_get_ready_version, which deliberately re-fetches instead
    of asserting on this raw response, exactly because of this."""
    token = await _register_and_login(client, "asyncupload@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    assert body["tables"] == []
    assert body["dataset_id"]

    detail = (await client.get(f"/api/v1/datasets/{body['dataset_id']}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["id"] == body["id"]
    assert version["status"] == "ready"
    assert len(version["tables"]) == 1


async def test_upload_with_unparseable_content_ends_up_failed(client: AsyncClient) -> None:
    """Structural validation (extension, magic bytes, size) still
    happens synchronously and still 400s outright — see
    test_upload_rejects_disguised_file/test_upload_rejects_oversized_file
    above, both unchanged. A file that LOOKS like a valid CSV but can't
    actually be parsed is a different failure mode: it passes
    validate_upload (nothing structurally wrong with it) and only fails
    once finish_ingest_upload actually tries to parse it — now that
    parsing is deferred, this can no longer be a 400; it has to surface
    as DatasetVersionStatus.FAILED on the version instead, since there's
    no HTTP response left to turn an exception into by the time it's
    discovered."""
    token = await _register_and_login(client, "failedupload@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    files = {"file": ("blank.csv", b"\n\n\n", "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Blank"},
        files=files,
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    dataset_id = resp.json()["dataset_id"]

    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "failed"
    assert version["error_message"]
    assert version["tables"] == []


def _build_invalid_values_csv() -> bytes:
    # Polars infers a CSV column's dtype from only the first 10,000 rows
    # (profiling.py's infer_schema_length); ignore_errors=True then nulls
    # any *later* row that doesn't fit that inferred type, rather than
    # widening the column to text. So reproducing that coercion-failure
    # path (as opposed to a column Polars decides is text from the start)
    # genuinely requires a file bigger than that sample window — this
    # mirrors a real large export with a row beyond that window that holds
    # a non-numeric value in an otherwise-numeric column.
    lines = ["name,score"]
    for i in range(10_049):
        lines.append(f"row{i},{i}")
    lines.append("garbage_row,garbage")  # non-blank, fails to parse as int -> invalid
    lines.append("blank_row,")  # genuinely blank -> missing, not invalid
    return ("\n".join(lines) + "\n").encode()


async def test_upload_distinguishes_invalid_values_from_missing(client: AsyncClient) -> None:
    token = await _register_and_login(client, "invalidvalues@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    version = await _upload_and_get_ready_version(
        client, token, workspace_id, "scores.csv", _build_invalid_values_csv(), name="Scores"
    )
    profile = version["tables"][0]["profile"]
    columns_by_name = {c["name"]: c for c in profile["columns"]}

    score = columns_by_name["score"]
    assert score["inferred_type"] == "integer"
    # Both the "garbage" row and the blank row become nulls, but only the
    # one that held a real, non-blank value should be reported as invalid.
    assert score["null_count"] == 2
    assert score["invalid_count"] == 1

    issue_types_for_score = {
        i["issue_type"] for i in profile["issues"] if i["column"] == "score"
    }
    assert "invalid_values" in issue_types_for_score
    assert "missing_values" in issue_types_for_score

    invalid_issue = next(i for i in profile["issues"] if i["issue_type"] == "invalid_values")
    assert invalid_issue["column"] == "score"
    assert invalid_issue["severity"] == "warning"

    # "name" has no missing or invalid values at all.
    name = columns_by_name["name"]
    assert name["null_count"] == 0
    assert name["invalid_count"] == 0


async def test_upload_rejects_disguised_file(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    files = {"file": ("evil.csv", b"MZ\x90\x00" + b"x" * 50, "text/csv")}
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Evil"},
        files=files,
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "executable" in resp.json()["detail"].lower()


async def test_upload_rejects_oversized_file(client: AsyncClient) -> None:
    get_settings.cache_clear()
    import os

    os.environ["MAX_UPLOAD_SIZE_BYTES"] = "20"
    try:
        token = await _register_and_login(client, "owner3@example.com")
        workspace_id = await _create_personal_workspace(client, token)

        files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
        resp = await client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            data={"name": "Too Big"},
            files=files,
            headers=_auth(token),
        )
        assert resp.status_code == 400
        assert "exceeds" in resp.json()["detail"].lower()
    finally:
        del os.environ["MAX_UPLOAD_SIZE_BYTES"]
        get_settings.cache_clear()


async def test_upload_multisheet_xlsx_creates_one_table_per_sheet(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    content = _build_sample_xlsx(
        {
            "Tenants": [["unit", "rent"], ["A1", 1200], ["A2", 950]],
            "Arrears": [["unit", "owed"], ["A1", 0], ["A2", 450]],
        }
    )
    version = await _upload_and_get_ready_version(
        client,
        token,
        workspace_id,
        "portfolio.xlsx",
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        name="Portfolio",
    )
    sheet_names = {t["sheet_name"] for t in version["tables"]}
    assert sheet_names == {"Tenants", "Arrears"}


async def test_confirm_schema_updates_confirmed_types(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    version = await _upload_and_get_ready_version(client, token, workspace_id, "data.csv", SAMPLE_CSV)
    table_id = version["tables"][0]["id"]

    ok_resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/schema",
        json={"column_types": {"signup_date": "date"}},
        headers=_auth(token),
    )
    assert ok_resp.status_code == 200
    table = ok_resp.json()["tables"][0]
    assert table["confirmed_schema"] == {"signup_date": "date"}

    bad_column_resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/schema",
        json={"column_types": {"not_a_real_column": "date"}},
        headers=_auth(token),
    )
    assert bad_column_resp.status_code == 400

    bad_type_resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/schema",
        json={"column_types": {"signup_date": "not_a_real_type"}},
        headers=_auth(token),
    )
    assert bad_type_resp.status_code == 400


async def test_deduplicate_creates_new_version_and_preserves_original(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    version = await _upload_and_get_ready_version(client, token, workspace_id, "data.csv", SAMPLE_CSV)
    table_id = version["tables"][0]["id"]
    dataset_id = version["dataset_id"]

    dedupe_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/deduplicate", headers=_auth(token)
    )
    assert dedupe_resp.status_code == 200, dedupe_resp.text
    new_version = dedupe_resp.json()
    assert new_version["version_number"] == 2
    assert new_version["derived_from_version_id"] is not None
    assert new_version["tables"][0]["row_count"] == 3  # 4 rows minus 1 exact duplicate

    detail_resp = await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))
    detail = detail_resp.json()
    assert len(detail["versions"]) == 2
    original_version = next(v for v in detail["versions"] if v["version_number"] == 1)
    assert original_version["tables"][0]["row_count"] == 4  # original untouched


async def test_outsider_cannot_upload_or_view_datasets(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")
    workspace_id = await _create_personal_workspace(client, owner_token)

    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    denied_upload = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(outsider_token),
    )
    assert denied_upload.status_code == 403

    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(owner_token),
    )
    dataset_id = (
        await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(owner_token))
    ).json()[0]["id"]
    assert upload_resp.status_code == 201

    denied_read = await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(outsider_token))
    assert denied_read.status_code == 403

    denied_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403


async def test_get_dataset_table_returns_profile(client: AsyncClient) -> None:
    token = await _register_and_login(client, "ownertable@example.com")
    workspace_id = await _create_personal_workspace(client, token)

    version = await _upload_and_get_ready_version(
        client, token, workspace_id, "rent_roll.csv", SAMPLE_CSV, name="Rent Roll"
    )
    table_id = version["tables"][0]["id"]

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == table_id
    assert body["row_count"] == 4
    column_names = {c["name"] for c in body["profile"]["columns"]}
    assert column_names == {"name", "age", "signup_date", "salary"}


async def test_get_dataset_table_404_for_unknown_id(client: AsyncClient) -> None:
    token = await _register_and_login(client, "ownertable2@example.com")
    resp = await client.get("/api/v1/dataset-tables/not-a-real-id", headers=_auth(token))
    assert resp.status_code == 404


async def test_outsider_cannot_get_dataset_table(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "ownertable3@example.com")
    outsider_token = await _register_and_login(client, "outsidertable3@example.com")
    workspace_id = await _create_personal_workspace(client, owner_token)

    version = await _upload_and_get_ready_version(client, owner_token, workspace_id, "data.csv", SAMPLE_CSV)
    table_id = version["tables"][0]["id"]

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}", headers=_auth(outsider_token))
    assert resp.status_code == 403


async def test_org_viewer_cannot_upload_but_can_read(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner8@example.com")
    viewer_email = "viewer8@example.com"
    viewer_token = await _register_and_login(client, viewer_email)

    org_resp = await client.post(
        "/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token)
    )
    org_id = org_resp.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": viewer_email, "role": "viewer"},
        headers=_auth(owner_token),
    )

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared", "industry": "general", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    denied_upload = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(viewer_token),
    )
    assert denied_upload.status_code == 403

    owner_upload = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(owner_token),
    )
    assert owner_upload.status_code == 201

    viewer_read = await client.get(
        f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(viewer_token)
    )
    assert viewer_read.status_code == 200
    assert len(viewer_read.json()) == 1
