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


async def test_create_api_key_returns_raw_key_once(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    resp = await client.post("/api/v1/api-keys", json={"name": "CI key"}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["raw_key"].startswith("dlk_")
    assert body["key_prefix"] == body["raw_key"][:12]
    assert len(body["raw_key"]) > 20


async def test_api_key_authenticates_real_requests(client: AsyncClient) -> None:
    """The actual end-to-end check: a generated key must work as a
    Bearer token on a real, unrelated endpoint — not just exist in the
    database."""
    token = await _register_and_login(client, "owner2@example.com")
    create_resp = await client.post("/api/v1/api-keys", json={"name": "CI key"}, headers=_auth(token))
    raw_key = create_resp.json()["raw_key"]

    me_resp = await client.get("/api/v1/users/me", headers=_auth(raw_key))
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "owner2@example.com"

    # The key can drive the full authz-checked API too, not just /me.
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Via API Key", "industry": "general"},
        headers=_auth(raw_key),
    )
    assert ws_resp.status_code == 201


async def test_api_key_tracks_last_used_at(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    create_resp = await client.post("/api/v1/api-keys", json={"name": "CI key"}, headers=_auth(token))
    raw_key = create_resp.json()["raw_key"]
    key_id = create_resp.json()["id"]

    list_before = await client.get("/api/v1/api-keys", headers=_auth(token))
    assert list_before.json()[0]["last_used_at"] is None

    await client.get("/api/v1/users/me", headers=_auth(raw_key))

    list_after = await client.get("/api/v1/api-keys", headers=_auth(token))
    matching = next(k for k in list_after.json() if k["id"] == key_id)
    assert matching["last_used_at"] is not None


async def test_revoked_api_key_no_longer_authenticates(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner4@example.com")
    create_resp = await client.post("/api/v1/api-keys", json={"name": "CI key"}, headers=_auth(token))
    raw_key = create_resp.json()["raw_key"]
    key_id = create_resp.json()["id"]

    working = await client.get("/api/v1/users/me", headers=_auth(raw_key))
    assert working.status_code == 200

    revoke_resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=_auth(token))
    assert revoke_resp.status_code == 204

    blocked = await client.get("/api/v1/users/me", headers=_auth(raw_key))
    assert blocked.status_code == 401


async def test_garbage_api_key_is_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me", headers=_auth("dlk_not_a_real_key_at_all"))
    assert resp.status_code == 401


async def test_list_only_shows_own_keys(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "ownerA@example.com")
    token_b = await _register_and_login(client, "ownerB@example.com")

    await client.post("/api/v1/api-keys", json={"name": "A's key"}, headers=_auth(token_a))
    await client.post("/api/v1/api-keys", json={"name": "B's key 1"}, headers=_auth(token_b))
    await client.post("/api/v1/api-keys", json={"name": "B's key 2"}, headers=_auth(token_b))

    list_a = await client.get("/api/v1/api-keys", headers=_auth(token_a))
    list_b = await client.get("/api/v1/api-keys", headers=_auth(token_b))
    assert len(list_a.json()) == 1
    assert len(list_b.json()) == 2


async def test_cannot_revoke_someone_elses_key(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "ownerC@example.com")
    token_b = await _register_and_login(client, "ownerD@example.com")

    create_resp = await client.post("/api/v1/api-keys", json={"name": "A's key"}, headers=_auth(token_a))
    key_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=_auth(token_b))
    assert resp.status_code == 404  # not 403 — existence isn't confirmed to a non-owner either


async def test_api_key_response_never_includes_hash_or_full_key_on_list(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    await client.post("/api/v1/api-keys", json={"name": "CI key"}, headers=_auth(token))

    list_resp = await client.get("/api/v1/api-keys", headers=_auth(token))
    body = list_resp.json()[0]
    assert "raw_key" not in body
    assert "key_hash" not in body
