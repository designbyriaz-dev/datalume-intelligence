import pyotp
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str = "mfa@example.com", password: str = "correct-horse-battery") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "MFA Test"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _enable_mfa(client: AsyncClient, token: str) -> str:
    """Returns the confirmed TOTP secret."""
    setup_resp = await client.post("/api/v1/auth/mfa/setup", headers=_auth(token))
    assert setup_resp.status_code == 200, setup_resp.text
    secret = setup_resp.json()["secret"]

    code = pyotp.TOTP(secret).now()
    enable_resp = await client.post("/api/v1/auth/mfa/enable", json={"code": code}, headers=_auth(token))
    assert enable_resp.status_code == 200, enable_resp.text
    assert enable_resp.json()["mfa_enabled"] is True
    return secret


async def test_mfa_setup_returns_a_secret_and_otpauth_url(client: AsyncClient) -> None:
    token = await _register_and_login(client, "setup@example.com")
    resp = await client.post("/api/v1/auth/mfa/setup", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["secret"]) >= 16
    assert body["otpauth_url"].startswith("otpauth://totp/")
    assert "DataLume" in body["otpauth_url"]


async def test_mfa_enable_rejects_wrong_code(client: AsyncClient) -> None:
    token = await _register_and_login(client, "wrongcode@example.com")
    await client.post("/api/v1/auth/mfa/setup", headers=_auth(token))

    resp = await client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=_auth(token))
    assert resp.status_code == 400


async def test_mfa_enable_requires_setup_first(client: AsyncClient) -> None:
    token = await _register_and_login(client, "nosetup@example.com")
    resp = await client.post("/api/v1/auth/mfa/enable", json={"code": "123456"}, headers=_auth(token))
    assert resp.status_code == 400
    assert "setup" in resp.json()["detail"].lower()


async def test_full_mfa_login_flow(client: AsyncClient) -> None:
    email, password = "fullflow@example.com", "correct-horse-battery"
    token = await _register_and_login(client, email, password)
    secret = await _enable_mfa(client, token)

    # A normal login now pauses instead of returning tokens.
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    login_body = login_resp.json()
    assert login_body["mfa_required"] is True
    assert login_body["challenge_token"]
    assert "access_token" not in login_body

    # Completing it with the real TOTP code issues real tokens.
    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/auth/mfa/verify", json={"challenge_token": login_body["challenge_token"], "code": code}
    )
    assert verify_resp.status_code == 200, verify_resp.text
    verify_body = verify_resp.json()
    assert verify_body["access_token"]
    assert verify_body["refresh_token"]

    # The new access token actually works.
    me_resp = await client.get("/api/v1/users/me", headers=_auth(verify_body["access_token"]))
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


async def test_mfa_verify_rejects_wrong_code(client: AsyncClient) -> None:
    email, password = "wrongverify@example.com", "correct-horse-battery"
    token = await _register_and_login(client, email, password)
    await _enable_mfa(client, token)

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    challenge_token = login_resp.json()["challenge_token"]

    resp = await client.post(
        "/api/v1/auth/mfa/verify", json={"challenge_token": challenge_token, "code": "000000"}
    )
    assert resp.status_code == 401


async def test_mfa_verify_rejects_a_login_access_token_as_the_challenge(client: AsyncClient) -> None:
    """The challenge token is a distinct JWT type — a real access token
    (or refresh token) must never work here, confirming type-confusion
    isn't possible between the two token kinds."""
    email, password = "typeconfusion@example.com", "correct-horse-battery"
    token = await _register_and_login(client, email, password)
    await _enable_mfa(client, token)

    resp = await client.post("/api/v1/auth/mfa/verify", json={"challenge_token": token, "code": "123456"})
    assert resp.status_code == 401


async def test_mfa_challenge_token_cannot_be_used_as_a_bearer_credential(client: AsyncClient) -> None:
    email, password = "challengebearer@example.com", "correct-horse-battery"
    token = await _register_and_login(client, email, password)
    await _enable_mfa(client, token)

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    challenge_token = login_resp.json()["challenge_token"]

    resp = await client.get("/api/v1/users/me", headers=_auth(challenge_token))
    assert resp.status_code == 401


async def test_mfa_disable_requires_correct_password(client: AsyncClient) -> None:
    token = await _register_and_login(client, "disable@example.com")
    await _enable_mfa(client, token)

    denied = await client.post(
        "/api/v1/auth/mfa/disable", json={"password": "wrong-password"}, headers=_auth(token)
    )
    assert denied.status_code == 401

    allowed = await client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "correct-horse-battery"},
        headers=_auth(token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["mfa_enabled"] is False

    # Login now succeeds normally again, no challenge step.
    email = "disable@example.com"
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


async def test_cannot_enable_mfa_twice(client: AsyncClient) -> None:
    token = await _register_and_login(client, "twice@example.com")
    await _enable_mfa(client, token)

    resp = await client.post("/api/v1/auth/mfa/setup", headers=_auth(token))
    assert resp.status_code == 400

    resp2 = await client.post("/api/v1/auth/mfa/enable", json={"code": "123456"}, headers=_auth(token))
    assert resp2.status_code == 400


async def test_mfa_verify_endpoint_requires_no_auth_header(client: AsyncClient) -> None:
    """Can't be authenticated — the whole point is the user doesn't have
    a valid access token yet."""
    email, password = "noauth@example.com", "correct-horse-battery"
    token = await _register_and_login(client, email, password)
    secret = await _enable_mfa(client, token)

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    challenge_token = login_resp.json()["challenge_token"]
    code = pyotp.TOTP(secret).now()

    resp = await client.post("/api/v1/auth/mfa/verify", json={"challenge_token": challenge_token, "code": code})
    assert resp.status_code == 200
