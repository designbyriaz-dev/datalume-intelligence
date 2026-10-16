"""Enterprise SSO via OIDC (the brief accepts SAML or OIDC; OIDC is the
modern standard and sufficient to satisfy that requirement — SAML's
XML-based flow is legacy and significantly more complex for no benefit
to a new integration).

IMPORTANT — read before trusting this "works":
This module is written correctly against authlib's documented API —
authlib (not hand-rolled code) owns every security-critical piece: PKCE
challenge generation, fetching the provider's JWKS, and validating the
ID token's signature and claims (iss/aud/exp). Delegating that to a
vetted library, rather than writing JWT signature verification by hand,
is a deliberate risk-reduction choice.

tests/test_sso.py goes further than most "unverified" integrations in
this codebase: it stands up a fake-but-spec-shaped OIDC provider (a real
generated RSA keypair, a real signed ID token, served over
httpx.MockTransport) and drives the full /sso/login -> /sso/callback
flow through it, including authlib's real JWKS-fetch and
signature/claims validation code — then separately proves that a token
signed with the WRONG key is actually rejected (not just "would be" —
that test caught a real bug: authlib's BadSignatureError wasn't being
caught, see the try/except below). That's real verification of the
cryptographic validation path.

Since also verified against a real identity provider: a real Google
Cloud OAuth client, a real consent screen, a real login driven all the
way through to a real User row (see docs/CHECKLIST.md's "SSO via OIDC"
section for the full account). That pass also caught a real bug this
module had: /sso/callback built valid tokens but never set the same
httpOnly session cookie /auth/login does, so a real SSO session would
have silently logged itself out on the next page reload — fixed in
app/api/v1/routers/sso.py.

What is still NOT verified: only Google has been tried — Okta and Azure
AD haven't, and either can have its own quirks (different claim names,
different error response shapes, token endpoint auth methods beyond
client_secret_post). The Google app itself is also still in
"Testing" publishing status with one whitelisted test user, not
verified/published. Do not report SSO as fully production-ready until a
second real IdP has been tried and the Google app has moved past
Testing status.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey, jwt as jose_jwt
from authlib.jose.errors import JoseError
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.sso_state import SSOLoginState
from app.models.user import User

STATE_EXPIRY = timedelta(minutes=10)


class OIDCNotConfiguredError(Exception):
    pass


class SSOError(Exception):
    """Client-facing error during the SSO flow (bad/expired state,
    unverified email, provider error)."""


@dataclass
class OIDCProviderConfig:
    client_id: str
    client_secret: str
    discovery_url: str
    redirect_uri: str


def get_oidc_config() -> OIDCProviderConfig:
    settings = get_settings()
    if not (settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_discovery_url):
        raise OIDCNotConfiguredError(
            "SSO is scaffolded (account-linking logic is tested) but not connected to a real "
            "identity provider — set OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_DISCOVERY_URL "
            "(and optionally OIDC_REDIRECT_URI). See docs/CHECKLIST.md."
        )
    return OIDCProviderConfig(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        discovery_url=settings.oidc_discovery_url,
        redirect_uri=settings.oidc_redirect_uri or f"{settings.frontend_base_url}/sso/callback",
    )


async def resolve_or_create_user_from_oidc_claims(db: AsyncSession, claims: dict[str, Any]) -> User:
    """The one fully-tested piece of this module. Takes already-validated
    OIDC claims (as authlib's jwt.decode().validate() would produce) and
    finds-or-creates the corresponding local User, linked by email.

    Refuses to link/create an account from an unverified email — an IdP
    that hands back email_verified=False is explicitly not trusted to
    assert account ownership."""
    email = claims.get("email")
    if not email:
        raise SSOError("The identity provider did not return an email claim.")
    if not claims.get("email_verified", False):
        raise SSOError("The identity provider's email is not verified — refusing to link an account.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    # A brand new account via SSO has no usable password of its own —
    # a random, never-communicated hash, same approach as disabling
    # password login for an SSO-only account without a separate flag.
    user = User(
        email=email,
        full_name=claims.get("name") or email.split("@")[0],
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        is_verified=True,  # the IdP already verified the email
    )
    db.add(user)
    await db.flush()
    return user


async def create_login_state(db: AsyncSession) -> tuple[str, str]:
    """Creates and persists one-time CSRF state + PKCE code_verifier for
    an authorization-code flow. Returns (state, code_verifier)."""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    db.add(
        SSOLoginState(
            state=state,
            code_verifier=code_verifier,
            expires_at=datetime.now(timezone.utc) + STATE_EXPIRY,
        )
    )
    await db.commit()
    return state, code_verifier


async def consume_login_state(db: AsyncSession, state: str) -> str:
    """Looks up and deletes (one-time use) the code_verifier for a state
    value. Raises SSOError if the state is unknown or expired."""
    result = await db.execute(select(SSOLoginState).where(SSOLoginState.state == state))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise SSOError("Unknown or already-used login state.")

    code_verifier = entry.code_verifier
    # entry.expires_at may come back naive (SQLite drops tzinfo on
    # DateTime(timezone=True) round-trip — same quirk documented in
    # Phase 6's scheduled-reports work) or aware (Postgres). Matching
    # tzinfo to whichever it is keeps the comparison valid either way —
    # the underlying stored instant is UTC regardless of the label.
    now = datetime.now(timezone.utc).replace(tzinfo=entry.expires_at.tzinfo)
    expired = entry.expires_at < now
    await db.delete(entry)
    await db.commit()

    if expired:
        raise SSOError("Login state expired — please try signing in again.")
    return code_verifier


async def fetch_discovery_document(http_client: httpx.AsyncClient, discovery_url: str) -> dict[str, Any]:
    response = await http_client.get(discovery_url, timeout=10.0)
    response.raise_for_status()
    return response.json()


def build_authorization_url(
    config: OIDCProviderConfig, discovery: dict[str, Any], *, state: str, code_verifier: str
) -> str:
    client = AsyncOAuth2Client(
        config.client_id, config.client_secret, redirect_uri=config.redirect_uri, scope="openid email profile"
    )
    code_challenge = create_s256_code_challenge(code_verifier)
    uri, _state = client.create_authorization_url(
        discovery["authorization_endpoint"],
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return uri


async def exchange_code_for_claims(
    http_client: httpx.AsyncClient,
    config: OIDCProviderConfig,
    discovery: dict[str, Any],
    *,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchanges the authorization code for tokens, then validates the ID
    token's signature (against the provider's published JWKS) and
    standard claims (issuer, audience, expiry) before returning them.
    UNVERIFIED against a real provider — see module docstring.

    Deliberately does NOT use authlib's AsyncOAuth2Client.fetch_token()
    for this step: that class is itself an httpx.AsyncClient subclass (no
    way to hand it an existing client/transport to reuse), so using it
    here would silently make a second, unmocked, real HTTP client —
    exactly the kind of thing that would make tests pass while hiding a
    real bug. A token exchange is a plain form-encoded POST with no
    cryptography in it, so there's no real benefit to authlib's wrapper
    for this specific call; the security-critical part (ID token
    signature/claims validation, below) still goes through authlib's
    `jose` module, not hand-rolled code."""
    token_response = await http_client.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        },
        timeout=10.0,
    )
    token_response.raise_for_status()
    token = token_response.json()

    id_token = token.get("id_token")
    if not id_token:
        raise SSOError("The identity provider did not return an id_token.")

    jwks_response = await http_client.get(discovery["jwks_uri"], timeout=10.0)
    jwks_response.raise_for_status()
    key_set = JsonWebKey.import_key_set(jwks_response.json())

    # authlib raises its own JoseError subclasses (BadSignatureError,
    # ExpiredTokenError, InvalidClaimError, ...) for anything wrong with
    # the token — a bad signature, expired token, wrong issuer/audience,
    # etc. All of those mean exactly one thing to a caller: reject this
    # login. Caught here and turned into SSOError so the router returns
    # a clean 400, not a raw 500 — this exact gap (uncaught
    # BadSignatureError leaking as a 500) was caught by
    # test_oidc_callback_rejects_tampered_id_token.
    try:
        claims = jose_jwt.decode(
            id_token,
            key_set,
            claims_options={
                "iss": {"essential": True, "values": [discovery["issuer"]]},
                "aud": {"essential": True, "values": [config.client_id]},
            },
        )
        claims.validate()
    except JoseError as exc:
        raise SSOError(f"ID token validation failed: {exc}") from exc

    return dict(claims)
