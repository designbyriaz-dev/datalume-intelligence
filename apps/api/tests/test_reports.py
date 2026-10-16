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


SAMPLE_CSV = (
    b"unit,tenant,rent\n"
    b"A1,Acme Ltd,1200\n"
    b"A2,Beta Co,950\n"
    b"A3,,\n"
)


async def _setup_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Reports Test", "industry": "general"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Test Data"},
        files=files,
        headers=_auth(token),
    )
    return upload_resp.json()["tables"][0]["id"]


async def test_generate_and_download_data_quality_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    table_id = await _setup_table(client, token)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text
    report = gen_resp.json()
    assert report["report_type"] == "data_quality"
    assert report["file_size_bytes"] > 0

    download_resp = await client.get(
        f"/api/v1/reports/{report['id']}/download", headers=_auth(token)
    )
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content.startswith(b"%PDF-")
    assert len(download_resp.content) == report["file_size_bytes"]


async def test_list_reports(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    table_id = await _setup_table(client, token)

    await client.post(f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(token))
    await client.post(f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(token))

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}/reports", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_outsider_cannot_generate_or_download_report(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    outsider_token = await _register_and_login(client, "outsider3@example.com")
    table_id = await _setup_table(client, owner_token)

    denied_gen = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(outsider_token)
    )
    assert denied_gen.status_code == 403

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(owner_token)
    )
    report_id = gen_resp.json()["id"]

    denied_download = await client.get(
        f"/api/v1/reports/{report_id}/download", headers=_auth(outsider_token)
    )
    assert denied_download.status_code == 403
