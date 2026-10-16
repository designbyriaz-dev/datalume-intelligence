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


SAMPLE_CSV = b"unit,rent\nA1,1000\nA2,2000\n"


async def _setup_dashboard_in_org(client: AsyncClient, owner_token: str, member_email: str, role: str) -> tuple[str, str]:
    org_resp = await client.post("/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": member_email, "role": role},
        headers=_auth(owner_token),
    )

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared", "industry": "general", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(owner_token),
    )
    table_id = upload_resp.json()["tables"][0]["id"]

    dashboard_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(owner_token),
    )
    return dashboard_resp.json()["id"], workspace_id


async def test_viewer_can_comment_despite_being_read_only(client: AsyncClient) -> None:
    """The key collaboration test: a Viewer role can't upload data or run
    transformations (enforced since Phase 2/4), but commenting on a
    shared dashboard is a read-level activity they ARE allowed to do."""
    owner_token = await _register_and_login(client, "owner@example.com")
    viewer_email = "viewer@example.com"
    viewer_token = await _register_and_login(client, viewer_email)

    dashboard_id, _workspace_id = await _setup_dashboard_in_org(client, owner_token, viewer_email, "viewer")

    resp = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments",
        json={"content": "Why is unit A2 so much higher than A1?"},
        headers=_auth(viewer_token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["content"] == "Why is unit A2 so much higher than A1?"


async def test_comments_are_listed_in_order(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner2@example.com")
    analyst_email = "analyst2@example.com"
    analyst_token = await _register_and_login(client, analyst_email)
    dashboard_id, _workspace_id = await _setup_dashboard_in_org(client, owner_token, analyst_email, "analyst")

    await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments", json={"content": "First"}, headers=_auth(owner_token)
    )
    await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments", json={"content": "Second"}, headers=_auth(analyst_token)
    )

    resp = await client.get(f"/api/v1/dashboards/{dashboard_id}/comments", headers=_auth(owner_token))
    assert resp.status_code == 200
    contents = [c["content"] for c in resp.json()]
    assert contents == ["First", "Second"]


async def test_can_only_delete_own_comment(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    analyst_email = "analyst3@example.com"
    analyst_token = await _register_and_login(client, analyst_email)
    dashboard_id, _workspace_id = await _setup_dashboard_in_org(client, owner_token, analyst_email, "analyst")

    comment_resp = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments", json={"content": "Owner's comment"}, headers=_auth(owner_token)
    )
    comment_id = comment_resp.json()["id"]

    denied = await client.delete(
        f"/api/v1/dashboards/{dashboard_id}/comments/{comment_id}", headers=_auth(analyst_token)
    )
    assert denied.status_code == 403

    allowed = await client.delete(
        f"/api/v1/dashboards/{dashboard_id}/comments/{comment_id}", headers=_auth(owner_token)
    )
    assert allowed.status_code == 204


async def test_outsider_cannot_comment_or_read_comments(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner4@example.com")
    outsider_token = await _register_and_login(client, "outsider4@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Personal", "industry": "general"}, headers=_auth(owner_token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(owner_token),
    )
    table_id = upload_resp.json()["tables"][0]["id"]
    dashboard_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "D", "dataset_table_id": table_id},
        headers=_auth(owner_token),
    )
    dashboard_id = dashboard_resp.json()["id"]

    denied_post = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments", json={"content": "x"}, headers=_auth(outsider_token)
    )
    assert denied_post.status_code == 403

    denied_list = await client.get(
        f"/api/v1/dashboards/{dashboard_id}/comments", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403
