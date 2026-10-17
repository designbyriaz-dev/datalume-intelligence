from httpx import AsyncClient

from app.api.deps import get_llm_client_dep
from app.core.industry_packs import COMMERCIAL_PROPERTY
from app.main import app
from app.services.ai.llm_client import LLMClient, LLMResponse
from app.services.industry_kpis import KPIResult
from app.services.reports import build_executive_summary_messages


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
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


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


COMMERCIAL_PROPERTY_CSV = (
    b"Unit,Tenant Name,Rent (PCM),Lease Expiry Date,Occupancy Status,Rent Arrears\n"
    b"A1,Acme Ltd,1200,2027-06-01,Occupied,0\n"
    b"A2,Beta Co,1800,2027-07-01,Occupied,0\n"
    b"A3,Gamma Inc,1500,2027-08-01,Occupied,100\n"
)


async def _setup_commercial_property_table(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Exec Report Test", "industry": "commercial_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", COMMERCIAL_PROPERTY_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Commercial Data"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


class _ScriptedLLMClient(LLMClient):
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def complete(self, *, system, messages, tools):
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        return LLMResponse(text=self._text, tool_uses=[], stop_reason="end_turn")


async def test_executive_intelligence_report_returns_503_when_llm_not_configured(
    client: AsyncClient,
) -> None:
    """Real, current behaviour — no LLM_API_KEY is set in this test
    environment, same assumption test_ai_analyst_api.py documents for
    /ask."""
    token = await _register_and_login(client, "owner4@example.com")
    table_id = await _setup_commercial_property_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/executive-intelligence", headers=_auth(token)
    )
    assert resp.status_code == 503


async def test_executive_intelligence_report_requires_an_industry_pack(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    table_id = await _setup_table(client, token)  # "general" industry — no pack, no KPIs possible

    fake_client = _ScriptedLLMClient("Should never be called.")
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/reports/executive-intelligence", headers=_auth(token)
        )
        assert resp.status_code == 400
        assert "industry" in resp.json()["detail"].lower()
        assert fake_client.calls == []  # never reached the LLM call
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


async def test_generate_executive_intelligence_report_full_flow(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    table_id = await _setup_commercial_property_table(client, token)

    fake_client = _ScriptedLLMClient(
        "Total rent roll across all three units stands at £4,500, averaging £1,500 per unit. "
        "Occupancy is strong at 100%, though Gamma Inc carries £100 in outstanding arrears."
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        gen_resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/reports/executive-intelligence", headers=_auth(token)
        )
        assert gen_resp.status_code == 201, gen_resp.text
        report = gen_resp.json()
        assert report["report_type"] == "executive_intelligence"
        assert report["file_size_bytes"] > 0

        # The LLM was given the real computed KPIs, not placeholder text.
        assert len(fake_client.calls) == 1
        prompt_text = fake_client.calls[0]["messages"][0]["content"]
        assert "Total Rent Roll" in prompt_text
        assert "4,500" in prompt_text or "4500" in prompt_text
        assert "Commercial Property Intelligence" in prompt_text

        download_resp = await client.get(
            f"/api/v1/reports/{report['id']}/download", headers=_auth(token)
        )
        assert download_resp.status_code == 200
        assert download_resp.content.startswith(b"%PDF-")
        assert len(download_resp.content) == report["file_size_bytes"]
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


async def test_outsider_cannot_generate_executive_intelligence_report(client: AsyncClient) -> None:
    """403 (tenant isolation) must win over 503 (LLM not configured) —
    an outsider shouldn't learn anything about server configuration. No
    LLM override needed: this must never reach the LLM dependency at
    all, same assumption test_ai_analyst_api.py's equivalent test makes
    for /ask."""
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")
    table_id = await _setup_commercial_property_table(client, owner_token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/reports/executive-intelligence", headers=_auth(outsider_token)
    )
    assert resp.status_code == 403


def test_executive_summary_prompt_includes_each_kpis_description() -> None:
    """build_executive_summary_messages's own docstring says it's "pure
    and synchronous on purpose... so the prompt construction itself can
    be unit-tested" — this is that test, previously missing. Proves a
    real gap is fixed: the model used to see only a KPI's name and a
    signed number, with no definition to disambiguate a metric whose
    sign isn't self-evident — the same gap found and fixed for the AI
    analyst's compute_industry_kpis tool (app/services/ai/planner.py)
    after a real model got one backwards; this is the executive
    summary's separate prompt-building path getting the same fix."""
    kpi_results = [
        KPIResult("total_rent_roll", "Total Rent Roll", "currency_gbp", 6750.0, "£6,750.00"),
        KPIResult("occupancy_rate", "Occupancy Rate", "percentage", 80.0, "80.0%"),
    ]

    messages = build_executive_summary_messages(kpi_results, COMMERCIAL_PROPERTY)

    content = messages[0]["content"]
    assert "Industry: Commercial Property Intelligence" in content
    assert "Total Rent Roll (Sum of rent across all units): £6,750.00" in content
    assert "Occupancy Rate (Share of units marked occupied): 80.0%" in content


def test_executive_summary_prompt_handles_a_kpi_with_no_matching_description() -> None:
    """Defensive: a kpi_id not found in the pack's own definitions (e.g.
    stale data from a renamed KPI) must not crash prompt building — it
    just omits the parenthetical rather than raising."""
    kpi_results = [KPIResult("not_a_real_kpi_id", "Mystery Metric", "number", 1.0, "1.00")]

    messages = build_executive_summary_messages(kpi_results, COMMERCIAL_PROPERTY)

    assert "Mystery Metric: 1.00" in messages[0]["content"]
