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


MONTH_1_CSV = b"unit,rent,status\nA1,1000,Occupied\nA2,1200,Occupied\nA3,900,Vacant\n"
MONTH_2_CSV = b"unit,rent,status\nA1,1050,Occupied\nA2,1200,Occupied\nA3,950,Occupied\nA4,800,Occupied\n"


async def test_compare_versions_detects_changes(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Compare Test", "industry": "general"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]

    files1 = {"file": ("month1.csv", MONTH_1_CSV, "text/csv")}
    upload1 = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files1,
        headers=_auth(token),
    )
    dataset_id = (
        await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(token))
    ).json()[0]["id"]

    files2 = {"file": ("month2.csv", MONTH_2_CSV, "text/csv")}
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"dataset_id": dataset_id},
        files=files2,
        headers=_auth(token),
    )

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/compare-versions",
        json={"version_a": 1, "version_b": 2},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count_before"] == 3
    assert body["row_count_after"] == 4
    assert body["row_count_delta"] == 1

    rent_comparison = next(c for c in body["column_comparisons"] if c["column"] == "rent")
    assert rent_comparison["sum_before"] == 3100.0
    assert rent_comparison["sum_after"] == 4000.0
    assert rent_comparison["sum_delta"] == 900.0


async def test_compare_versions_rejects_unknown_version(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Compare Test 2", "industry": "general"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", MONTH_1_CSV, "text/csv")}
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(token),
    )
    dataset_id = (
        await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(token))
    ).json()[0]["id"]

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/compare-versions",
        json={"version_a": 1, "version_b": 99},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "99" in resp.json()["detail"]


async def test_outsider_cannot_compare_versions(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    outsider_token = await _register_and_login(client, "outsider3@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Compare Test 3", "industry": "general"}, headers=_auth(owner_token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", MONTH_1_CSV, "text/csv")}
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(owner_token),
    )
    dataset_id = (
        await client.get(f"/api/v1/workspaces/{workspace_id}/datasets", headers=_auth(owner_token))
    ).json()[0]["id"]

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/compare-versions",
        json={"version_a": 1, "version_b": 1},
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403
