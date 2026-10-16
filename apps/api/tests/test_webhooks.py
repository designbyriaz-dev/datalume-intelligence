"""Tests outbound webhook delivery end-to-end, using httpx.MockTransport
so a real HTTP POST (with a real HMAC signature, verified against the
subscription's actual secret) happens through httpx's own request/
response machinery — no real network call, no extra test dependency.
"""

import hashlib
import hmac
import json

import httpx
from httpx import AsyncClient

from app.api.deps import get_http_client
from app.main import app


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _verify_signature(secret: str, signature_header: str, payload_bytes: bytes) -> bool:
    parts = dict(p.split("=", 1) for p in signature_header.split(","))
    signed_payload = f"{parts['t']}.{payload_bytes.decode()}".encode()
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])


class _RecordingTransport:
    """Wraps an httpx.MockTransport-backed client override: records every
    request the app sends out, and always responds 200."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"received": True})

    def override(self):
        async def _get_http_client():
            async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as client:
                yield client

        app.dependency_overrides[get_http_client] = _get_http_client

    def clear(self):
        app.dependency_overrides.pop(get_http_client, None)


async def _setup_workspace(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Webhook Test", "industry": "general"}, headers=_auth(token)
    )
    return resp.json()["id"]


async def test_create_webhook_returns_secret_once(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    workspace_id = await _setup_workspace(client, token)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["dataset.uploaded"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["secret"].startswith("whsub_")

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/webhooks", headers=_auth(token))
    assert "secret" not in list_resp.json()[0]


async def test_dataset_upload_triggers_signed_webhook_delivery(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id = await _setup_workspace(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["dataset.uploaded"]},
        headers=_auth(token),
    )
    secret = create_resp.json()["secret"]

    recorder = _RecordingTransport()
    recorder.override()
    try:
        files = {"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
        upload_resp = await client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            data={"name": "Data"},
            files=files,
            headers=_auth(token),
        )
        assert upload_resp.status_code == 201
    finally:
        recorder.clear()

    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert str(request.url) == "https://example.test/hook"
    body = json.loads(request.content)
    assert body["event_type"] == "dataset.uploaded"

    signature_header = request.headers["x-datalume-signature"]
    assert _verify_signature(secret, signature_header, request.content)


async def test_webhook_not_triggered_for_unsubscribed_event_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    workspace_id = await _setup_workspace(client, token)

    # Subscribed only to report.generated, not dataset.uploaded.
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["report.generated"]},
        headers=_auth(token),
    )

    recorder = _RecordingTransport()
    recorder.override()
    try:
        files = {"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            data={"name": "Data"},
            files=files,
            headers=_auth(token),
        )
    finally:
        recorder.clear()

    assert recorder.requests == []


async def test_report_generation_triggers_webhook(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    workspace_id = await _setup_workspace(client, token)

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["report.generated"]},
        headers=_auth(token),
    )

    files = {"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    table_id = upload_resp.json()["tables"][0]["id"]

    recorder = _RecordingTransport()
    recorder.override()
    try:
        gen_resp = await client.post(
            f"/api/v1/dataset-tables/{table_id}/reports/data-quality", headers=_auth(token)
        )
        assert gen_resp.status_code == 201
    finally:
        recorder.clear()

    assert len(recorder.requests) == 1
    body = json.loads(recorder.requests[0].content)
    assert body["event_type"] == "report.generated"


async def test_webhook_delivery_failure_is_recorded_not_raised(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    workspace_id = await _setup_workspace(client, token)

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["dataset.uploaded"]},
        headers=_auth(token),
    )

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    async def _get_failing_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as c:
            yield c

    app.dependency_overrides[get_http_client] = _get_failing_client
    try:
        files = {"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
        # The upload itself must still succeed — one failing webhook must
        # never break the action that triggered it.
        upload_resp = await client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            data={"name": "Data"},
            files=files,
            headers=_auth(token),
        )
        assert upload_resp.status_code == 201
    finally:
        app.dependency_overrides.pop(get_http_client, None)

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/webhooks", headers=_auth(token))
    webhook = list_resp.json()[0]
    assert webhook["last_delivery_status"] == 500
    assert webhook["last_delivery_error"] == "HTTP 500"


async def test_webhook_test_endpoint_sends_regardless_of_event_types(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    workspace_id = await _setup_workspace(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["report.generated"]},  # not dataset.uploaded
        headers=_auth(token),
    )
    webhook_id = create_resp.json()["id"]

    recorder = _RecordingTransport()
    recorder.override()
    try:
        resp = await client.post(f"/api/v1/webhooks/{webhook_id}/test", headers=_auth(token))
        assert resp.status_code == 200
    finally:
        recorder.clear()

    assert len(recorder.requests) == 1
    body = json.loads(recorder.requests[0].content)
    assert body["event_type"] == "test"


async def test_unknown_event_type_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner7@example.com")
    workspace_id = await _setup_workspace(client, token)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["not_a_real_event"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_outsider_cannot_manage_webhooks(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner8@example.com")
    outsider_token = await _register_and_login(client, "outsider8@example.com")
    workspace_id = await _setup_workspace(client, owner_token)

    denied_create = await client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={"url": "https://example.test/hook", "event_types": ["dataset.uploaded"]},
        headers=_auth(outsider_token),
    )
    assert denied_create.status_code == 403

    denied_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403
