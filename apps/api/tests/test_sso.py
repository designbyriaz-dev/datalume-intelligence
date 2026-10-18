"""SSO tests. Two kinds, deliberately distinguished:

1. Direct unit tests of resolve_or_create_user_from_oidc_claims and the
   login-state store — fully real, no mocking needed.
2. A full end-to-end flow (test_full_oidc_login_flow_with_fake_provider)
   against a FAKE identity provider: we generate our own RSA keypair,
   sign a real ID token with it, and serve a discovery document + token
   endpoint + JWKS endpoint via httpx.MockTransport. This exercises
   authlib's real JOSE/JWKS validation code for real, but a fake
   provider can only prove the code handles the token *shapes* its
   author anticipated — not the shapes a real IdP actually sends. Google
   was verified live in an earlier round; Microsoft Entra ID/Azure AD
   was verified live in a later one (see docs/CHECKLIST.md), which
   caught test_accepts_email_when_idp_omits_the_verified_claim_entirely
   below — a real interop gap no fake-provider test would ever have
   caught, since the fake provider only ever sent the claim shapes this
   file's own author assumed. Okta remains unverified.
"""

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_http_client
from app.core.config import get_settings
from app.main import app
from app.models.sso_state import SSOLoginState
from app.models.user import User
from app.services.sso import (
    SSOError,
    consume_login_state,
    create_login_state,
    resolve_or_create_user_from_oidc_claims,
)


async def test_create_user_from_new_oidc_claims(db_session: AsyncSession) -> None:
    claims = {"email": "new-sso-user@example.com", "email_verified": True, "name": "New User", "sub": "idp-123"}
    user = await resolve_or_create_user_from_oidc_claims(db_session, claims)
    assert user.email == "new-sso-user@example.com"
    assert user.full_name == "New User"
    assert user.is_verified is True


async def test_links_to_existing_user_by_email(db_session: AsyncSession) -> None:
    existing = User(email="existing@example.com", full_name="Existing", hashed_password="x", is_verified=False)
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    claims = {"email": "existing@example.com", "email_verified": True, "sub": "idp-456"}
    resolved = await resolve_or_create_user_from_oidc_claims(db_session, claims)
    assert resolved.id == existing.id


async def test_rejects_unverified_email(db_session: AsyncSession) -> None:
    with pytest.raises(SSOError, match="not verified"):
        await resolve_or_create_user_from_oidc_claims(
            db_session, {"email": "unverified@example.com", "email_verified": False}
        )


async def test_accepts_email_when_idp_omits_the_verified_claim_entirely(db_session: AsyncSession) -> None:
    """Regression test for a real bug found verifying SSO live against a
    real Microsoft Entra ID app registration (see docs/CHECKLIST.md):
    Microsoft's standard v2.0 ID token has no email_verified claim at
    all under the default `openid email profile` scopes — confirmed by
    logging the actual raw claims from a real token, not assumed. The
    original check treated "claim absent" the same as "claim false"
    (claims.get("email_verified", False)), which Google's tokens never
    exposed as a problem since Google always sends email_verified
    explicitly — so no Entra ID/Azure AD login could ever have
    succeeded until this was caught and fixed. Only an *explicit* false
    is a red flag (see test_rejects_unverified_email above); an IdP
    that simply doesn't report the claim is accepted."""
    claims = {"email": "entra-user@example.com", "name": "Entra User", "sub": "entra-oid-123"}
    assert "email_verified" not in claims
    user = await resolve_or_create_user_from_oidc_claims(db_session, claims)
    assert user.email == "entra-user@example.com"


async def test_rejects_missing_email(db_session: AsyncSession) -> None:
    with pytest.raises(SSOError, match="email claim"):
        await resolve_or_create_user_from_oidc_claims(db_session, {"email_verified": True})


async def test_login_state_is_one_time_use(db_session: AsyncSession) -> None:
    state, code_verifier = await create_login_state(db_session)
    assert state and code_verifier

    recovered = await consume_login_state(db_session, state)
    assert recovered == code_verifier

    with pytest.raises(SSOError, match="Unknown"):
        await consume_login_state(db_session, state)


async def test_login_state_rejects_unknown_state(db_session: AsyncSession) -> None:
    with pytest.raises(SSOError, match="Unknown"):
        await consume_login_state(db_session, "not-a-real-state")


async def test_expired_login_state_is_rejected(db_session: AsyncSession) -> None:
    import datetime as dt

    state, code_verifier = await create_login_state(db_session)
    entry_result = await db_session.execute(
        __import__("sqlalchemy").select(SSOLoginState).where(SSOLoginState.state == state)
    )
    entry = entry_result.scalar_one()
    entry.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(SSOError, match="expired"):
        await consume_login_state(db_session, state)


async def test_sso_login_returns_503_when_not_configured(client: AsyncClient) -> None:
    # This environment now has real OIDC_CLIENT_ID/SECRET/DISCOVERY_URL
    # in apps/api/.env (verified against a real Google identity provider
    # — see docs/CHECKLIST.md). Explicitly clear them so this test keeps
    # exercising the "not configured" path regardless of local .env
    # contents, the same way test_billing.py/test_billing_webhook.py
    # isolate Stripe config.
    _clear_oidc_config()
    try:
        resp = await client.get("/api/v1/sso/login")
        assert resp.status_code == 503
        assert "oidc_client_id" in resp.json()["detail"].lower()
    finally:
        get_settings.cache_clear()


async def test_sso_callback_returns_503_when_not_configured(client: AsyncClient) -> None:
    _clear_oidc_config()
    try:
        resp = await client.post("/api/v1/sso/callback", json={"code": "x", "state": "y"})
        assert resp.status_code == 503
    finally:
        get_settings.cache_clear()


class _FakeProvider:
    """A minimal but spec-shaped OIDC provider: real RSA keys, a real
    signed ID token, served via httpx.MockTransport."""

    ISSUER = "https://fake-idp.test"
    CLIENT_ID = "test-client-id"

    def __init__(self, claims_override: dict | None = None):
        self.key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
        self.public_jwk = self.key.as_dict(is_private=False)
        self.public_jwk["kid"] = "test-key-1"
        self.public_jwk["alg"] = "RS256"
        self.claims_override = claims_override or {}

    def _sign_id_token(self) -> str:
        now = int(time.time())
        claims = {
            "iss": self.ISSUER,
            "aud": self.CLIENT_ID,
            "sub": "idp-user-1",
            "email": "sso-user@example.com",
            "email_verified": True,
            "name": "SSO User",
            "iat": now,
            "exp": now + 300,
            **self.claims_override,
        }
        token = jose_jwt.encode({"alg": "RS256", "kid": "test-key-1"}, claims, self.key)
        return token.decode() if isinstance(token, bytes) else token

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": self.ISSUER,
                    "authorization_endpoint": f"{self.ISSUER}/authorize",
                    "token_endpoint": f"{self.ISSUER}/token",
                    "jwks_uri": f"{self.ISSUER}/jwks",
                },
            )
        if path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "fake-access-token",
                    "token_type": "Bearer",
                    "id_token": self._sign_id_token(),
                },
            )
        if path.endswith("/jwks"):
            return httpx.Response(200, json={"keys": [self.public_jwk]})
        return httpx.Response(404)


def _configure_oidc():
    import os

    os.environ["OIDC_CLIENT_ID"] = _FakeProvider.CLIENT_ID
    os.environ["OIDC_CLIENT_SECRET"] = "test-client-secret"
    os.environ["OIDC_DISCOVERY_URL"] = f"{_FakeProvider.ISSUER}/.well-known/openid-configuration"
    get_settings.cache_clear()


def _clear_oidc_config():
    import os

    for key in ("OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_DISCOVERY_URL"):
        os.environ.pop(key, None)
    get_settings.cache_clear()


async def test_full_oidc_login_flow_with_fake_provider(client: AsyncClient, db_session: AsyncSession) -> None:
    _configure_oidc()
    provider = _FakeProvider()

    async def _get_mock_http_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as c:
            yield c

    app.dependency_overrides[get_http_client] = _get_mock_http_client
    try:
        login_resp = await client.get("/api/v1/sso/login")
        assert login_resp.status_code == 200, login_resp.text
        authorization_url = login_resp.json()["authorization_url"]

        parsed = urlparse(authorization_url)
        assert parsed.netloc == "fake-idp.test"
        query = parse_qs(parsed.query)
        assert query["client_id"] == [_FakeProvider.CLIENT_ID]
        assert query["code_challenge_method"] == ["S256"]
        state = query["state"][0]

        callback_resp = await client.post("/api/v1/sso/callback", json={"code": "fake-auth-code", "state": state})
        assert callback_resp.status_code == 200, callback_resp.text
        tokens = callback_resp.json()
        assert tokens["access_token"]
        assert tokens["refresh_token"]
    finally:
        app.dependency_overrides.pop(get_http_client, None)
        _clear_oidc_config()

    # The user was really created from the validated ID token's claims.
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "sso-user@example.com"))
    user = result.scalar_one()
    assert user.full_name == "SSO User"
    assert user.is_verified is True


async def test_oidc_callback_rejects_tampered_id_token(client: AsyncClient, db_session: AsyncSession) -> None:
    """A token signed with the WRONG key (not the one published at
    jwks_uri) must be rejected — proves signature validation is actually
    being enforced, not just present in the code."""
    _configure_oidc()
    legit_provider = _FakeProvider()
    attacker_key = JsonWebKey.generate_key("RSA", 2048, is_private=True)

    def tampering_handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": legit_provider.ISSUER,
                    "authorization_endpoint": f"{legit_provider.ISSUER}/authorize",
                    "token_endpoint": f"{legit_provider.ISSUER}/token",
                    "jwks_uri": f"{legit_provider.ISSUER}/jwks",
                },
            )
        if path.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": legit_provider.ISSUER,
                "aud": legit_provider.CLIENT_ID,
                "sub": "attacker",
                "email": "attacker@example.com",
                "email_verified": True,
                "iat": now,
                "exp": now + 300,
            }
            # Signed with a key that does NOT match what jwks_uri publishes.
            bad_token = jose_jwt.encode({"alg": "RS256", "kid": "test-key-1"}, claims, attacker_key)
            return httpx.Response(
                200,
                json={"access_token": "x", "token_type": "Bearer", "id_token": bad_token.decode()},
            )
        if path.endswith("/jwks"):
            return httpx.Response(200, json={"keys": [legit_provider.public_jwk]})
        return httpx.Response(404)

    async def _get_mock_http_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tampering_handler)) as c:
            yield c

    app.dependency_overrides[get_http_client] = _get_mock_http_client
    try:
        login_resp = await client.get("/api/v1/sso/login")
        state = parse_qs(urlparse(login_resp.json()["authorization_url"]).query)["state"][0]

        callback_resp = await client.post("/api/v1/sso/callback", json={"code": "fake-code", "state": state})
        assert callback_resp.status_code in (400, 502)
    finally:
        app.dependency_overrides.pop(get_http_client, None)
        _clear_oidc_config()

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "attacker@example.com"))
    assert result.scalar_one_or_none() is None  # no account was created from the forged token
