"""Self-serve workspace and account deletion. The most important case
here is test_deleting_an_analysts_account_preserves_shared_org_content
— it's a regression test for a real bug this round found and fixed: 9
"creator" foreign keys (Dataset.created_by_user_id,
AnalysisRun.created_by_user_id, Report.generated_by_user_id, ...) had
no ON DELETE action at all, which SQLite's default FK-enforcement-off
behaviour hides completely but real Postgres does not — deleting a
user who had ever contributed to someone else's shared workspace would
raise a real ForeignKeyViolation there. See
alembic/versions/1e8b0cec90e4_nullable_creator_fields_for_account_.py
and app/services/account_deletion.py's module docstring."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.dashboard import DashboardComment
from app.models.dataset import Dataset
from app.services.storage import LocalFilesystemStorage, ObjectStorage

SAMPLE_CSV = b"name,value\nA,1\nB,2\n"


async def _register_and_login(client: AsyncClient, email: str, full_name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": full_name},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_personal_workspace(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Delete Me", "industry": "general"}, headers=_auth(token)
    )
    return resp.json()["id"]


async def _upload_and_get_table_id(client: AsyncClient, token: str, workspace_id: str) -> str:
    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_delete_workspace_removes_data_and_storage_objects(
    client: AsyncClient, test_storage: ObjectStorage
) -> None:
    assert isinstance(test_storage, LocalFilesystemStorage)
    token = await _register_and_login(client, "wsowner@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    table_id = await _upload_and_get_table_id(client, token, workspace_id)

    gen_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(token)
    )
    assert gen_resp.status_code == 201, gen_resp.text

    # Confirm the storage objects genuinely exist on disk before deleting.
    stored_files = list(test_storage.base_dir.rglob("*"))
    data_files = [p for p in stored_files if p.is_file()]
    assert len(data_files) >= 2, "expected at least the uploaded source file and the generated report"

    delete_resp = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=_auth(token))
    assert delete_resp.status_code == 204, delete_resp.text

    get_resp = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(token))
    assert get_resp.status_code == 404

    remaining_files = [p for p in test_storage.base_dir.rglob("*") if p.is_file()]
    assert remaining_files == [], f"storage objects left behind: {remaining_files}"


async def test_outsider_cannot_delete_a_personal_workspace(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "wsowner2@example.com")
    outsider_token = await _register_and_login(client, "wsoutsider2@example.com")
    workspace_id = await _create_personal_workspace(client, owner_token)

    resp = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=_auth(outsider_token))
    assert resp.status_code == 403

    # Still there.
    get_resp = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(owner_token))
    assert get_resp.status_code == 200


async def test_analyst_role_cannot_delete_an_org_workspace_but_admin_can(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "orgowner@example.com", "Org Owner")
    org_resp = await client.post("/api/v1/organizations", json={"name": "Acme"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    analyst_token = await _register_and_login(client, "orgdeleter_analyst@example.com", "Analyst")
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "orgdeleter_analyst@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    admin_token = await _register_and_login(client, "orgdeleter_admin@example.com", "Admin")
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "orgdeleter_admin@example.com", "role": "administrator"},
        headers=_auth(owner_token),
    )

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared", "industry": "general", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    analyst_resp = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=_auth(analyst_token))
    assert analyst_resp.status_code == 403

    admin_resp = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=_auth(admin_token))
    assert admin_resp.status_code == 204, admin_resp.text


async def test_delete_my_account_requires_correct_password(client: AsyncClient) -> None:
    token = await _register_and_login(client, "wrongpw@example.com")
    resp = await client.request(
        "DELETE", "/api/v1/users/me", json={"password": "not-the-right-password"}, headers=_auth(token)
    )
    assert resp.status_code == 401

    # The account must still work normally afterward.
    me_resp = await client.get("/api/v1/users/me", headers=_auth(token))
    assert me_resp.status_code == 200


async def test_delete_my_account_removes_personal_data_and_logs_out(client: AsyncClient) -> None:
    token = await _register_and_login(client, "selfdelete@example.com")
    workspace_id = await _create_personal_workspace(client, token)
    await _upload_and_get_table_id(client, token, workspace_id)

    resp = await client.request(
        "DELETE", "/api/v1/users/me", json={"password": "correct-horse-battery"}, headers=_auth(token)
    )
    assert resp.status_code == 204, resp.text

    # The old access token is dead — the user row it points to is gone.
    me_resp = await client.get("/api/v1/users/me", headers=_auth(token))
    assert me_resp.status_code == 401

    # Re-registering the same email works — nothing of the old account lingers.
    reregister = await client.post(
        "/api/v1/auth/register",
        json={"email": "selfdelete@example.com", "password": "a-different-password", "full_name": "New"},
    )
    assert reregister.status_code == 201, reregister.text


async def test_deleting_an_analysts_account_preserves_shared_org_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The real regression test — see this module's own docstring.
    Before the fix, this exact sequence raised a real
    ForeignKeyViolation against Postgres (reproduced and confirmed
    fixed against a real local Postgres instance, not just SQLite,
    which doesn't enforce foreign keys by default and would never have
    caught this)."""
    owner_token = await _register_and_login(client, "shareowner@example.com", "Owner")
    org_resp = await client.post("/api/v1/organizations", json={"name": "Shared Co"}, headers=_auth(owner_token))
    org_id = org_resp.json()["id"]

    analyst_email = "contributor@example.com"
    analyst_token = await _register_and_login(client, analyst_email, "Contributor")
    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": analyst_email, "role": "analyst"},
        headers=_auth(owner_token),
    )

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared Workspace", "industry": "general", "organization_id": org_id},
        headers=_auth(owner_token),
    )
    workspace_id = ws_resp.json()["id"]

    # The analyst — not the owner — uploads the data and runs an analysis.
    table_id = await _upload_and_get_table_id(client, analyst_token, workspace_id)
    analyze_resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/analyze",
        json={"operation": "descriptive_stats", "parameters": {"column": "value"}},
        headers=_auth(analyst_token),
    )
    assert analyze_resp.status_code == 201, analyze_resp.text

    # The analyst also leaves a dashboard comment, as another independent
    # author_user_id FK that must survive the same way.
    dash_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/dashboards",
        json={"name": "Dash", "dataset_table_id": table_id},
        headers=_auth(analyst_token),
    )
    assert dash_resp.status_code == 201, dash_resp.text
    dashboard_id = dash_resp.json()["id"]
    comment_resp = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/comments",
        json={"content": "Looks good"},
        headers=_auth(analyst_token),
    )
    assert comment_resp.status_code == 201, comment_resp.text

    dataset_id = (
        await db_session.execute(select(Dataset.id).where(Dataset.workspace_id == workspace_id))
    ).scalar_one()

    # The analyst deletes their own account.
    delete_resp = await client.request(
        "DELETE", "/api/v1/users/me", json={"password": "correct-horse-battery"}, headers=_auth(analyst_token)
    )
    assert delete_resp.status_code == 204, delete_resp.text

    # The shared workspace and everything in it survives, still fully
    # readable by the owner.
    ws_get = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth(owner_token))
    assert ws_get.status_code == 200
    table_get = await client.get(f"/api/v1/dataset-tables/{table_id}", headers=_auth(owner_token))
    assert table_get.status_code == 200
    dash_get = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=_auth(owner_token))
    assert dash_get.status_code == 200

    # The creator-tracking columns are null, not still pointing at a
    # user row that no longer exists.
    await db_session.commit()  # release this session's view of any cached state
    dataset = await db_session.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.created_by_user_id is None

    comment = (
        await db_session.execute(select(DashboardComment).where(DashboardComment.dashboard_id == dashboard_id))
    ).scalar_one()
    assert comment.author_user_id is None
    assert comment.content == "Looks good"  # the comment itself is untouched

    # The account-deletion audit event survives too, actor anonymised,
    # email kept as a readable snapshot in its metadata.
    deletion_event = (
        await db_session.execute(select(AuditLog).where(AuditLog.event_type == "auth.account_deleted"))
    ).scalar_one()
    assert deletion_event.actor_user_id is None
    assert deletion_event.event_metadata["email"] == analyst_email
