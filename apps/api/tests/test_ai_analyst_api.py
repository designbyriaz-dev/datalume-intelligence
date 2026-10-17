"""API-level tests for the /ask endpoint. The LLM_API_KEY-not-configured
test exercises REAL behaviour (that's the actual default in this
environment). The "full flow" tests override get_llm_client_dep with a
scripted fake — they verify conversation persistence, tenant isolation,
and the request/response contract, not real model behaviour.
"""

from httpx import AsyncClient

from app.api.deps import get_llm_client_dep
from app.main import app
from app.services.ai.llm_client import LLMClient, LLMResponse, ToolUseBlock


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


RENT_ROLL_CSV = (
    b"unit,category,rent\n"
    b"A1,office,1200\n"
    b"A2,office,950\n"
    b"A3,retail,2000\n"
)


async def _setup_dataset_and_table(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "AI Test", "industry": "general"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", RENT_ROLL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    table_id = version["tables"][0]["id"]
    return dataset_id, table_id


async def test_ask_returns_503_when_llm_not_configured(client: AsyncClient) -> None:
    """This is the REAL, current behaviour — no LLM_API_KEY is set in
    this environment. The endpoint must fail loudly, not pretend."""
    token = await _register_and_login(client, "owner@example.com")
    _dataset_id, table_id = await _setup_dataset_and_table(client, token)

    resp = await client.post(
        f"/api/v1/dataset-tables/{table_id}/ask",
        json={"question": "What's the average rent?"},
        headers=_auth(token),
    )
    assert resp.status_code == 503
    assert "llm_api_key" in resp.json()["detail"].lower()


class _ScriptedClient(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, *, system, messages, tools):
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        return self._responses.pop(0)


async def test_ask_full_flow_with_fake_llm_client(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    dataset_id, table_id = await _setup_dataset_and_table(client, token)

    fake_client = _ScriptedClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "rent"})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="The average rent is 1383.33.", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "What's the average rent?"},
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["answer"] == "The average rent is 1383.33."
        assert len(body["tool_calls"]) == 1
        assert body["tool_calls"][0]["name"] == "descriptive_stats"
        assert body["tool_calls"][0]["result"]["mean"] is not None
        conversation_id = body["conversation_id"]

        # Conversation + both messages were actually persisted.
        conv_resp = await client.get(f"/api/v1/ai-conversations/{conversation_id}", headers=_auth(token))
        assert conv_resp.status_code == 200
        messages = conv_resp.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["tool_calls"][0]["name"] == "descriptive_stats"

        list_resp = await client.get(f"/api/v1/datasets/{dataset_id}/conversations", headers=_auth(token))
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


COMMERCIAL_CSV = (
    b"Unit,Tenant Name,Rent (PCM),Occupancy Status\n"
    b"A1,Acme Ltd,1200,Occupied\n"
    b"A2,Beta Co,950,Occupied\n"
    b"A3,Gamma Inc,2000,Vacant\n"
)


async def _setup_commercial_property_dataset(client: AsyncClient, token: str) -> str:
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "AI Commercial Test", "industry": "commercial_property"},
        headers=_auth(token),
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", COMMERCIAL_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Rent Roll"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return version["tables"][0]["id"]


async def test_ask_uses_the_real_industry_kpi_engine_for_an_industry_workspace(client: AsyncClient) -> None:
    """End-to-end: a workspace with a real industry pack (commercial_
    property) offers the AI analyst compute_industry_kpis, and calling
    it returns this app's actual, precise KPI calculation — not an
    approximation — through the real /ask endpoint, not just the
    planner unit tests."""
    token = await _register_and_login(client, "owner3@example.com")
    table_id = await _setup_commercial_property_dataset(client, token)

    fake_client = _ScriptedClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="compute_industry_kpis", input={})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="Your total rent roll is £4,150.", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "What's our total rent roll?"},
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tool_calls"][0]["name"] == "compute_industry_kpis"
        assert body["tool_calls"][0]["error"] is None
        kpis_by_id = {k["kpi_id"]: k for k in body["tool_calls"][0]["result"]["kpis"]}
        assert kpis_by_id["total_rent_roll"]["value"] == 4150.0
        assert kpis_by_id["occupancy_rate"]["value"] == 66.67
        assert body["tool_calls"][0]["result"]["pack_name"] == "Commercial Property Intelligence"

        # Confirms the tool was actually offered to the model for this
        # workspace, not just handled if called speculatively.
        tool_names = {t["name"] for t in fake_client.calls[0]["tools"]}
        assert "compute_industry_kpis" in tool_names
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


async def test_ask_does_not_offer_the_industry_kpi_tool_for_a_general_workspace(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    _dataset_id, table_id = await _setup_dataset_and_table(client, token)  # industry="general"

    fake_client = _ScriptedClient([LLMResponse(text="No KPI engine here.", tool_uses=[], stop_reason="end_turn")])
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask", json={"question": "hi"}, headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text
        tool_names = {t["name"] for t in fake_client.calls[0]["tools"]}
        assert "compute_industry_kpis" not in tool_names
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


async def test_ask_continues_existing_conversation(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    _dataset_id, table_id = await _setup_dataset_and_table(client, token)

    fake_client = _ScriptedClient(
        [
            LLMResponse(text="Office rent averages 1075.", tool_uses=[], stop_reason="end_turn"),
            LLMResponse(text="Retail is higher, at 2000.", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        first = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "What's office rent?"},
            headers=_auth(token),
        )
        conversation_id = first.json()["conversation_id"]

        second = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "And retail?", "conversation_id": conversation_id},
            headers=_auth(token),
        )
        assert second.status_code == 200
        assert second.json()["conversation_id"] == conversation_id

        conv_resp = await client.get(f"/api/v1/ai-conversations/{conversation_id}", headers=_auth(token))
        assert len(conv_resp.json()["messages"]) == 4  # 2 user + 2 assistant across both turns
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)


async def test_second_turn_replays_first_turns_tool_call_with_full_fidelity(client: AsyncClient) -> None:
    """End-to-end proof (through real DB persistence, not just the
    in-memory planner test in test_ai_planner.py) that a second /ask
    call in the same conversation sees the first turn's actual
    tool_use/tool_result blocks — not a flattened text summary. This is
    the conversation-history replay fidelity fix: AIMessage.replay_messages
    is persisted by the first call and reconstructed by
    _history_to_anthropic_messages for the second."""
    token = await _register_and_login(client, "owner5@example.com")
    _dataset_id, table_id = await _setup_dataset_and_table(client, token)

    first_client = _ScriptedClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "rent"})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="The average rent is 1383.33.", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: first_client
    try:
        first = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "What's the average rent?"},
            headers=_auth(token),
        )
        conversation_id = first.json()["conversation_id"]
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)

    second_client = _ScriptedClient(
        [LLMResponse(text="Yes, 1383.33 as computed a moment ago.", tool_uses=[], stop_reason="end_turn")]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: second_client
    try:
        second = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "Can you double check that?", "conversation_id": conversation_id},
            headers=_auth(token),
        )
        assert second.status_code == 200, second.text
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)

    sent_history = second_client.calls[0]["messages"]
    tool_use_blocks = [
        block
        for m in sent_history
        if isinstance(m.get("content"), list)
        for block in m["content"]
        if block.get("type") == "tool_use"
    ]
    assert len(tool_use_blocks) == 1
    assert tool_use_blocks[0]["name"] == "descriptive_stats"
    assert tool_use_blocks[0]["input"] == {"column": "rent"}

    tool_result_blocks = [
        block
        for m in sent_history
        if isinstance(m.get("content"), list)
        for block in m["content"]
        if block.get("type") == "tool_result"
    ]
    assert len(tool_result_blocks) == 1
    assert tool_result_blocks[0]["tool_use_id"] == "tu_1"


async def test_outsider_cannot_ask_or_read_conversation(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner4@example.com")
    outsider_token = await _register_and_login(client, "outsider4@example.com")
    dataset_id, table_id = await _setup_dataset_and_table(client, owner_token)

    denied = await client.post(
        f"/api/v1/dataset-tables/{table_id}/ask",
        json={"question": "anything?"},
        headers=_auth(outsider_token),
    )
    # 403 (tenant isolation) must win over 503 (LLM not configured) —
    # an outsider shouldn't learn anything about server configuration.
    assert denied.status_code == 403

    denied_list = await client.get(
        f"/api/v1/datasets/{dataset_id}/conversations", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403


async def test_outsider_cannot_read_conversation_detail(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    outsider_token = await _register_and_login(client, "outsider5@example.com")
    _dataset_id, table_id = await _setup_dataset_and_table(client, owner_token)

    fake_client = _ScriptedClient(
        [LLMResponse(text="The average rent is 1383.33.", tool_uses=[], stop_reason="end_turn")]
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_client
    try:
        resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/ask",
            json={"question": "What's the average rent?"},
            headers=_auth(owner_token),
        )
        assert resp.status_code == 200, resp.text
        conversation_id = resp.json()["conversation_id"]
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)

    # The detail endpoint (unlike the list endpoint above) is keyed purely
    # by conversation_id with no dataset_id in the URL to pre-check — it
    # must still correctly reject an outsider rather than leaking the
    # conversation's contents.
    denied_detail = await client.get(
        f"/api/v1/ai-conversations/{conversation_id}", headers=_auth(outsider_token)
    )
    assert denied_detail.status_code == 403
