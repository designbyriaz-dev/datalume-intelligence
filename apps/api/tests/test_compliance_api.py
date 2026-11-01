from httpx import AsyncClient

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
        "/api/v1/workspaces", json={"name": "Portfolio", "industry": "residential_property"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    prop_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/properties",
        json={"address_line1": "1 Compliance Rd", "city": "Leeds", "postcode": "LS1 1AA"},
        headers=_auth(token),
    )
    return workspace_id, prop_resp.json()["id"]


async def test_create_list_and_update_compliance_rule(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rules@example.com")
    workspace_id, _property_id = await _create_workspace_and_property(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "Gas Safety Certificate", "document_type": "gas_safety_certificate"},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["requires_non_expired"] is True
    assert body["warning_window_days"] == 30
    rule_id = body["id"]

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/compliance-rules", headers=_auth(token))
    assert len(list_resp.json()) == 1

    update_resp = await client.patch(
        f"/api/v1/compliance-rules/{rule_id}",
        json={
            "name": "Gas Safety Certificate",
            "document_type": "gas_safety_certificate",
            "requires_non_expired": True,
            "warning_window_days": 60,
            "is_active": False,
        },
        headers=_auth(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["warning_window_days"] == 60
    assert update_resp.json()["is_active"] is False


async def test_property_compliance_reflects_real_documents(client: AsyncClient) -> None:
    token = await _register_and_login(client, "propcompliance@example.com")
    workspace_id, property_id = await _create_workspace_and_property(client, token)

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "Gas Safety Certificate", "document_type": "gas_safety_certificate"},
        headers=_auth(token),
    )
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "EPC", "document_type": "epc"},
        headers=_auth(token),
    )

    # Missing info for both rules before any document exists.
    before = await client.get(f"/api/v1/properties/{property_id}/compliance", headers=_auth(token))
    assert before.status_code == 200
    statuses_before = {c["rule_name"]: c["status"] for c in before.json()["checks"]}
    assert statuses_before["Gas Safety Certificate"] == "missing_information"
    assert statuses_before["EPC"] == "missing_information"

    await client.post(
        f"/api/v1/properties/{property_id}/documents",
        data={
            "title": "Gas cert",
            "document_type": "gas_safety_certificate",
            "expiry_date": "2099-01-01",
        },
        files={"file": ("gas.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(token),
    )

    after = await client.get(f"/api/v1/properties/{property_id}/compliance", headers=_auth(token))
    statuses_after = {c["rule_name"]: c["status"] for c in after.json()["checks"]}
    assert statuses_after["Gas Safety Certificate"] == "passes"
    assert statuses_after["EPC"] == "missing_information"


async def test_inactive_rule_is_excluded_from_property_compliance(client: AsyncClient) -> None:
    token = await _register_and_login(client, "inactiverule@example.com")
    workspace_id, property_id = await _create_workspace_and_property(client, token)

    rule_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "EICR", "document_type": "eicr", "is_active": False},
        headers=_auth(token),
    )
    assert rule_resp.json()["is_active"] is False

    result = await client.get(f"/api/v1/properties/{property_id}/compliance", headers=_auth(token))
    assert result.json()["checks"] == []


async def test_outsider_cannot_access_compliance_rules(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "complianceowner@example.com")
    outsider_token = await _register_and_login(client, "complianceoutsider@example.com")
    workspace_id, property_id = await _create_workspace_and_property(client, owner_token)

    rule_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "EPC", "document_type": "epc"},
        headers=_auth(owner_token),
    )
    rule_id = rule_resp.json()["id"]

    assert (
        await client.get(f"/api/v1/workspaces/{workspace_id}/compliance-rules", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/properties/{property_id}/compliance", headers=_auth(outsider_token))
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/compliance-rules/{rule_id}",
            json={
                "name": "EPC",
                "document_type": "epc",
                "requires_non_expired": True,
                "warning_window_days": 30,
                "is_active": True,
            },
            headers=_auth(outsider_token),
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/compliance-rules/{rule_id}", headers=_auth(outsider_token))
    ).status_code == 403


async def test_deleting_compliance_rule(client: AsyncClient) -> None:
    token = await _register_and_login(client, "deleterule@example.com")
    workspace_id, _property_id = await _create_workspace_and_property(client, token)

    rule_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "EPC", "document_type": "epc"},
        headers=_auth(token),
    )
    rule_id = rule_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/compliance-rules/{rule_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/compliance-rules", headers=_auth(token))
    assert list_resp.json() == []


async def test_deleting_workspace_cascades_to_compliance_rules(client: AsyncClient) -> None:
    token = await _register_and_login(client, "cascaderule@example.com")
    workspace_id, _property_id = await _create_workspace_and_property(client, token)

    rule_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/compliance-rules",
        json={"name": "EPC", "document_type": "epc"},
        headers=_auth(token),
    )
    rule_id = rule_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    # No direct GET /compliance-rules/{id} endpoint exists — confirm via
    # an update attempt, which 404s once both the rule and its workspace
    # are gone rather than 403ing against a still-existing workspace.
    update_resp = await client.patch(
        f"/api/v1/compliance-rules/{rule_id}",
        json={
            "name": "EPC",
            "document_type": "epc",
            "requires_non_expired": True,
            "warning_window_days": 30,
            "is_active": True,
        },
        headers=_auth(token),
    )
    assert update_resp.status_code == 404
