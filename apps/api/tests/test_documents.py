from httpx import AsyncClient

from app.services.storage import LocalFilesystemStorage, ObjectStorage

PDF_BYTES = b"%PDF-1.4\n%mock pdf content for tests\n"


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace_and_property(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Portfolio", "industry": "residential_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Document St", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(token),
    )
    return workspace_id, prop_resp.json()["id"]


async def test_upload_and_fetch_document(client: AsyncClient) -> None:
    token = await _register_and_login(client, "docs@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    upload_resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Gas safety certificate 2026", "document_type": "gas_safety_certificate", "expiry_date": "2027-01-01"},
        files={"file": ("gas-cert.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    body = upload_resp.json()
    assert body["property_id"] == property_id
    assert body["document_type"] == "gas_safety_certificate"
    assert body["expiry_date"] == "2027-01-01"
    assert body["content_type"] == "application/pdf"
    document_id = body["id"]

    get_resp = await client.get(f"/api/v1/documents/{document_id}", headers=_auth(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Gas safety certificate 2026"

    list_resp = await client.get(f"/api/v1/properties/{property_id}/documents", headers=_auth(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_download_document_returns_original_bytes(client: AsyncClient) -> None:
    token = await _register_and_login(client, "downloader@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    upload_resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "EPC", "document_type": "epc"},
        files={"file": ("epc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    document_id = upload_resp.json()["id"]

    download_resp = await client.get(f"/api/v1/documents/{document_id}/download", headers=_auth(token))
    assert download_resp.status_code == 200
    assert download_resp.content == PDF_BYTES
    assert download_resp.headers["content-type"] == "application/pdf"
    assert "epc.pdf" in download_resp.headers["content-disposition"]


async def test_rejects_unsupported_file_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "badupload@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Suspicious", "document_type": "other"},
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_document_scoped_to_tenancy(client: AsyncClient) -> None:
    token = await _register_and_login(client, "tenancydocs@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)
    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id}/tenancies",
        json={"tenant_name": "Alex Doe", "rent_amount_gbp": 900, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Signed tenancy agreement", "document_type": "tenancy_agreement", "tenancy_id": tenancy_id},
        files={"file": ("agreement.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["tenancy_id"] == tenancy_id

    filtered = await client.get(
        f"/api/v1/properties/{property_id}/documents?tenancy_id={tenancy_id}", headers=_auth(token)
    )
    assert len(filtered.json()) == 1

    other_tenancy_filter = await client.get(
        f"/api/v1/properties/{property_id}/documents?tenancy_id=nonexistent", headers=_auth(token)
    )
    assert other_tenancy_filter.json() == []


async def test_tenancy_id_must_belong_to_the_same_property(client: AsyncClient) -> None:
    token = await _register_and_login(client, "crossprop@example.com")
    _workspace_id, property_id_a = await _create_workspace_and_property(client, token)
    workspace_id, property_id_b = await _create_workspace_and_property(client, token)

    tenancy_resp = await client.post(
        f"/api/v1/properties/{property_id_b}/tenancies",
        json={"tenant_name": "Sam Rivers", "rent_amount_gbp": 900, "start_date": "2026-01-01"},
        headers=_auth(token),
    )
    tenancy_id = tenancy_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/properties/{property_id_a}/documents",
        data={"title": "Mismatch", "document_type": "other", "tenancy_id": tenancy_id},
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_outsider_cannot_access_documents(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "docowner@example.com")
    outsider_token = await _register_and_login(client, "docoutsider@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, owner_token)

    upload_resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Private doc", "document_type": "other"},
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(owner_token),
    )
    document_id = upload_resp.json()["id"]

    assert (
        await client.get(f"/api/v1/documents/{document_id}", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/documents/{document_id}/download", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/properties/{property_id}/documents", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/properties/{property_id}/documents",
            data={"title": "Intrusion", "document_type": "other"},
            files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
            headers=_auth(outsider_token),
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/documents/{document_id}", headers=_auth(outsider_token))
    ).status_code == 403


async def test_delete_document_removes_it_from_storage_and_db(client: AsyncClient) -> None:
    token = await _register_and_login(client, "deleter@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    upload_resp = await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "To be deleted", "document_type": "other"},
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    document_id = upload_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/documents/{document_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    assert (await client.get(f"/api/v1/documents/{document_id}", headers=_auth(token))).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{document_id}/download", headers=_auth(token))
    ).status_code == 404


async def test_deleting_property_cascades_to_documents(client: AsyncClient) -> None:
    token = await _register_and_login(client, "cascadedocs@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Cascade test", "document_type": "other"},
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )

    delete_resp = await client.delete(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/properties/{property_id}/documents", headers=_auth(token))
    assert list_resp.status_code == 404


async def test_deleting_property_removes_document_storage_objects(
    client: AsyncClient, test_storage: ObjectStorage
) -> None:
    assert isinstance(test_storage, LocalFilesystemStorage)
    token = await _register_and_login(client, "cascadestorage@example.com")
    _workspace_id, property_id = await _create_workspace_and_property(client, token)

    await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={"title": "Orphan check", "document_type": "other"},
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )
    assert [p for p in test_storage.base_dir.rglob("*") if p.is_file()]

    delete_resp = await client.delete(f"/api/v1/properties/{property_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    remaining_files = [p for p in test_storage.base_dir.rglob("*") if p.is_file()]
    assert remaining_files == [], f"storage objects left behind: {remaining_files}"
