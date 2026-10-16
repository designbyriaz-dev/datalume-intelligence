from httpx import AsyncClient


async def _register(client: AsyncClient, email: str = "jane@example.com", password: str = "correct-horse-battery") -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Jane Doe"},
    )
    assert resp.status_code == 201, resp.text


async def test_register_creates_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "jane@example.com", "password": "correct-horse-battery", "full_name": "Jane Doe"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "jane@example.com"
    assert body["is_verified"] is False
    assert "hashed_password" not in body


async def test_register_duplicate_email_rejected(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "jane@example.com", "password": "another-password", "full_name": "Jane Two"},
    )
    assert resp.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "short", "full_name": "Short Pw"},
    )
    assert resp.status_code == 422


async def test_login_succeeds_with_correct_credentials(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_fails_with_wrong_password(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_me_returns_current_user_with_valid_token(client: AsyncClient) -> None:
    await _register(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "jane@example.com"


async def test_refresh_token_issues_new_access_token(client: AsyncClient) -> None:
    await _register(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def _set_cookie_headers(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


async def test_login_sets_httponly_refresh_cookie_and_readable_csrf_cookie(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    cookies = _set_cookie_headers(resp)
    refresh_cookie = next(c for c in cookies if c.startswith("refresh_token="))
    csrf_cookie = next(c for c in cookies if c.startswith("csrf_token="))

    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie  # frontend JS must be able to read this one
    assert "SameSite=lax" in refresh_cookie
    assert resp.cookies.get("refresh_token")
    assert resp.cookies.get("csrf_token")


async def test_refresh_via_cookie_without_csrf_header_is_rejected(client: AsyncClient) -> None:
    await _register(client)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    # The client's cookie jar now holds refresh_token + csrf_token from
    # login. Posting with no body and no CSRF header relies purely on
    # the ambient refresh_token cookie — exactly the pattern CSRF
    # protection exists to block.
    resp = await client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 403


async def test_refresh_via_cookie_with_wrong_csrf_header_is_rejected(client: AsyncClient) -> None:
    await _register(client)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    resp = await client.post("/api/v1/auth/refresh", json={}, headers={"X-CSRF-Token": "not-the-real-token"})
    assert resp.status_code == 403


async def test_refresh_via_cookie_with_correct_csrf_header_succeeds_and_rotates_cookies(
    client: AsyncClient,
) -> None:
    await _register(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    csrf_token = login_resp.cookies.get("csrf_token")
    assert csrf_token

    resp = await client.post("/api/v1/auth/refresh", json={}, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    # Cookies are rotated on every successful refresh, not reused.
    new_csrf_cookie = next(c for c in _set_cookie_headers(resp) if c.startswith("csrf_token="))
    assert csrf_token not in new_csrf_cookie


async def test_refresh_via_explicit_body_token_does_not_need_a_csrf_header(client: AsyncClient) -> None:
    """The non-browser path (a script, this test suite elsewhere) isn't
    an ambient-credential flow an attacker's page could trigger, so no
    CSRF header is required — covers the same ground as
    test_refresh_token_issues_new_access_token above but makes the
    "no CSRF needed here" property explicit."""
    await _register(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200


async def test_refresh_with_no_cookie_and_no_body_token_is_unauthorized(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 401


async def test_logout_clears_cookies(client: AsyncClient) -> None:
    await _register(client)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-battery"},
    )
    assert client.cookies.get("refresh_token")

    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 204

    cleared = _set_cookie_headers(resp)
    refresh_cleared = next(c for c in cleared if c.startswith("refresh_token="))
    assert "Max-Age=0" in refresh_cleared or "01 Jan 1970" in refresh_cleared

    # A subsequent refresh attempt relying on the (now-cleared) cookie
    # must fail — proving the clear actually took effect, not just that
    # the response looked right.
    csrf_before_logout = client.cookies.get("csrf_token")
    after = await client.post(
        "/api/v1/auth/refresh",
        json={},
        headers={"X-CSRF-Token": csrf_before_logout} if csrf_before_logout else {},
    )
    assert after.status_code in (401, 403)
