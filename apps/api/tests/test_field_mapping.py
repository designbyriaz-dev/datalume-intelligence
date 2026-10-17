"""Reviewing and confirming the automatic industry-pack field mapping —
same "review before trusting" pattern as Phase 2's schema confirmation
for column types (app/services/industry_matching.py's docstring).
Proves the confirmed mapping actually changes what /industry-kpis
computes, not just what GET .../field-mapping reports back."""

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


# "Amount Due Monthly" deliberately doesn't match any rent_amount alias
# (rent/rent pcm/monthly rent/...) by exact or token-subset match — the
# automatic matcher leaves rent_amount unmapped for this CSV.
AMBIGUOUS_CSV = (
    b"Unit,Tenant Name,Amount Due Monthly,Lease Expiry Date,Occupancy Status\n"
    b"A1,Acme Ltd,1200,2027-01-15,Occupied\n"
    b"A2,Beta Co,950,2026-03-20,Occupied\n"
)


async def _setup_workspace_and_table(client: AsyncClient, token: str, content: bytes = AMBIGUOUS_CSV) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Mapping Test", "industry": "commercial_property"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", content, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", data={"name": "Data"}, files=files, headers=_auth(token)
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return workspace_id, version["tables"][0]["id"]


async def test_get_field_mapping_reports_automatic_match_and_unconfirmed(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner1@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}/field-mapping", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["industry_id"] == "commercial_property"
    assert body["is_confirmed"] is False
    assert "Amount Due Monthly" in body["available_columns"]

    fields_by_name = {f["canonical_field"]: f for f in body["fields"]}
    assert fields_by_name["tenant"]["matched_column"] == "Tenant Name"  # auto-matched fine
    assert fields_by_name["rent_amount"]["matched_column"] is None  # the ambiguous one
    assert "rent_amount" in body["missing_required_fields"]


async def test_industry_kpis_fail_to_map_rent_before_confirmation(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    kpis_by_id = {k["kpi_id"]: k for k in resp.json()["kpis"]}
    assert kpis_by_id["total_rent_roll"]["error"] is not None
    assert "rent_amount" in kpis_by_id["total_rent_roll"]["error"].lower()


async def test_confirming_mapping_fixes_industry_kpis(client: AsyncClient) -> None:
    """The real end-to-end proof: confirming rent_amount -> 'Amount Due
    Monthly' changes what /industry-kpis actually computes, not just
    what the field-mapping endpoint reports."""
    token = await _register_and_login(client, "owner3@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    confirm_resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/field-mapping",
        json={"mapping": {"rent_amount": "Amount Due Monthly"}},
        headers=_auth(token),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    body = confirm_resp.json()
    assert body["is_confirmed"] is True
    fields_by_name = {f["canonical_field"]: f for f in body["fields"]}
    assert fields_by_name["rent_amount"]["matched_column"] == "Amount Due Monthly"
    # Confirming is a full replacement, not a merge: fields the caller
    # didn't mention explicitly go back to null, not whatever the
    # automatic matcher would have guessed.
    assert fields_by_name["tenant"]["matched_column"] is None

    kpi_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/industry-kpis", headers=_auth(token))
    kpis_by_id = {k["kpi_id"]: k for k in kpi_resp.json()["kpis"]}
    assert kpis_by_id["total_rent_roll"]["error"] is None
    assert kpis_by_id["total_rent_roll"]["value"] == 2150.0  # 1200 + 950


async def test_confirm_rejects_unknown_canonical_field(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/field-mapping",
        json={"mapping": {"not_a_real_field": "Amount Due Monthly"}},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "unknown field" in resp.json()["detail"].lower()


async def test_confirm_rejects_unknown_column_name(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/field-mapping",
        json={"mapping": {"rent_amount": "Not A Real Column"}},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "unknown column" in resp.json()["detail"].lower()


async def test_confirmed_mapping_survives_a_cleaning_operation(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, token)

    await client.patch(
        f"/api/v1/dataset-tables/{table_id}/field-mapping",
        json={"mapping": {"rent_amount": "Amount Due Monthly"}},
        headers=_auth(token),
    )

    dedupe_resp = await client.post(f"/api/v1/dataset-tables/{table_id}/deduplicate", headers=_auth(token))
    assert dedupe_resp.status_code == 200, dedupe_resp.text
    new_table_id = dedupe_resp.json()["tables"][0]["id"]

    mapping_resp = await client.get(f"/api/v1/dataset-tables/{new_table_id}/field-mapping", headers=_auth(token))
    body = mapping_resp.json()
    assert body["is_confirmed"] is True
    fields_by_name = {f["canonical_field"]: f for f in body["fields"]}
    assert fields_by_name["rent_amount"]["matched_column"] == "Amount Due Monthly"


async def test_outsider_cannot_read_or_confirm_field_mapping(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")
    _workspace_id, table_id = await _setup_workspace_and_table(client, owner_token)

    get_resp = await client.get(f"/api/v1/dataset-tables/{table_id}/field-mapping", headers=_auth(outsider_token))
    assert get_resp.status_code == 403

    patch_resp = await client.patch(
        f"/api/v1/dataset-tables/{table_id}/field-mapping",
        json={"mapping": {"rent_amount": "Amount Due Monthly"}},
        headers=_auth(outsider_token),
    )
    assert patch_resp.status_code == 403


async def test_field_mapping_rejected_for_workspace_without_industry_pack(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner8@example.com")
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "General", "industry": "general"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", AMBIGUOUS_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", data={"name": "Data"}, files=files, headers=_auth(token)
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    table_id = version["tables"][0]["id"]

    resp = await client.get(f"/api/v1/dataset-tables/{table_id}/field-mapping", headers=_auth(token))
    assert resp.status_code == 400
