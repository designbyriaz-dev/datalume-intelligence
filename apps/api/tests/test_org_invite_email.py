"""Organization invites to not-yet-registered users — the invite is
emailed instead of immediately creating a Membership (there's no
account to attach one to), and consumed at registration time via
RegisterRequest.invite_token. Uses the same recording EmailSender
override as tests/test_auth_email_flows.py."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_email_sender_dep, get_email_sender_optional_dep
from app.main import app
from app.models.email_token import EmailToken
from app.services.email import EmailMessage


class _RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def override(self) -> None:
        app.dependency_overrides[get_email_sender_dep] = lambda: self
        app.dependency_overrides[get_email_sender_optional_dep] = lambda: self

    def clear(self) -> None:
        app.dependency_overrides.pop(get_email_sender_dep, None)
        app.dependency_overrides.pop(get_email_sender_optional_dep, None)


@pytest.fixture
def email_sender() -> _RecordingEmailSender:
    sender = _RecordingEmailSender()
    sender.override()
    yield sender
    sender.clear()


def _extract_token(text_body: str) -> str:
    match = re.search(r"token=([^\s]+)", text_body)
    assert match, f"no token found in email body: {text_body!r}"
    return match.group(1)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery", "full_name": "Owner"}
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


async def _create_org(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post("/api/v1/organizations", json={"name": name}, headers=_auth(token))
    return resp.json()["id"]


async def test_invite_unknown_email_without_smtp_returns_404(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 404


async def test_invite_unknown_email_with_smtp_emails_a_pending_invite(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    email_sender.sent.clear()  # discard the owner's own registration verification email

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"status": "invite_emailed", "email": "newperson@example.com", "role": "analyst"}

    assert len(email_sender.sent) == 1
    assert email_sender.sent[0].to == "newperson@example.com"
    assert "Acme Co" in email_sender.sent[0].text_body


async def test_invite_preview_and_registration_grants_membership(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    email_sender.sent.clear()

    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    invite_token = _extract_token(email_sender.sent[0].text_body)

    preview = await client.get(f"/api/v1/organizations/invites/{invite_token}")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"organization_name": "Acme Co", "role": "analyst", "email": "newperson@example.com"}

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newperson@example.com",
            "password": "correct-horse-battery",
            "full_name": "New Person",
            "invite_token": invite_token,
        },
    )
    assert register_resp.status_code == 201, register_resp.text

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "newperson@example.com", "password": "correct-horse-battery"}
    )
    new_person_token = login_resp.json()["access_token"]

    orgs_resp = await client.get("/api/v1/organizations", headers=_auth(new_person_token))
    assert orgs_resp.status_code == 200
    assert any(org["id"] == org_id for org in orgs_resp.json())

    # One-time use: the invite token can't preview or register again.
    replay_preview = await client.get(f"/api/v1/organizations/invites/{invite_token}")
    assert replay_preview.status_code == 400


async def test_registering_with_invite_token_for_a_different_email_is_rejected(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    email_sender.sent.clear()

    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    invite_token = _extract_token(email_sender.sent[0].text_body)

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "someone-else@example.com",
            "password": "correct-horse-battery",
            "full_name": "Someone Else",
            "invite_token": invite_token,
        },
    )
    assert resp.status_code == 400


async def test_expired_invite_token_is_rejected(
    client: AsyncClient, email_sender: _RecordingEmailSender, db_session: AsyncSession
) -> None:
    owner_token = await _register_and_login(client, "owner@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    email_sender.sent.clear()

    await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    invite_token = _extract_token(email_sender.sent[0].text_body)

    result = await db_session.execute(select(EmailToken).where(EmailToken.target_email == "newperson@example.com"))
    entry = result.scalar_one()
    entry.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    preview = await client.get(f"/api/v1/organizations/invites/{invite_token}")
    assert preview.status_code == 400
