"""Email verification and password reset, exercised with a recording
EmailSender override instead of the real SMTP backend (see
tests/test_email.py for the SMTP integration code's own coverage) — the
same "fake the external edge, exercise everything behind it for real"
approach test_webhooks.py and test_sso.py use."""

import re

import pytest
from httpx import AsyncClient

from app.api.deps import get_email_sender_dep, get_email_sender_optional_dep
from app.main import app
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


def _extract_token(text_body: str) -> str:
    match = re.search(r"token=([^\s]+)", text_body)
    assert match, f"no token found in email body: {text_body!r}"
    return match.group(1)


@pytest.fixture
def email_sender() -> _RecordingEmailSender:
    sender = _RecordingEmailSender()
    sender.override()
    yield sender
    sender.clear()


async def _register(client: AsyncClient, email: str, password: str = "correct-horse-battery") -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test User"}
    )
    assert resp.status_code == 201, resp.text


async def test_register_without_email_configured_sends_nothing(client: AsyncClient) -> None:
    # No email_sender fixture used here — SMTP stays unconfigured, same
    # as every other test file. Registration must still succeed.
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "nomail@example.com", "password": "correct-horse-battery", "full_name": "No Mail"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_verified"] is False


async def test_register_with_email_configured_sends_verification_email(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    await _register(client, "verify-me@example.com")
    assert len(email_sender.sent) == 1
    assert email_sender.sent[0].to == "verify-me@example.com"
    assert "verify" in email_sender.sent[0].subject.lower()


async def test_verify_email_marks_user_verified(client: AsyncClient, email_sender: _RecordingEmailSender) -> None:
    await _register(client, "verify-me@example.com")
    token = _extract_token(email_sender.sent[0].text_body)

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_verified"] is True

    # One-time use: the same token can't be replayed.
    resp2 = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp2.status_code == 400


async def test_verify_email_rejects_unknown_token(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400


async def test_resend_verification_requires_email_configured(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/resend-verification", json={"email": "anyone@example.com"})
    assert resp.status_code == 503


async def test_resend_verification_same_response_for_unknown_and_known_email(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    await _register(client, "verify-me@example.com")

    known_resp = await client.post("/api/v1/auth/resend-verification", json={"email": "verify-me@example.com"})
    unknown_resp = await client.post("/api/v1/auth/resend-verification", json={"email": "ghost@example.com"})

    assert known_resp.status_code == 202
    assert unknown_resp.status_code == 202
    assert known_resp.json() == unknown_resp.json()
    # Only the real account actually got an email — one from registration,
    # one from the resend; the unknown email never triggered a send.
    assert len(email_sender.sent) == 2


async def test_forgot_password_requires_email_configured(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "anyone@example.com"})
    assert resp.status_code == 503


async def test_forgot_password_reset_flow(client: AsyncClient, email_sender: _RecordingEmailSender) -> None:
    await _register(client, "reset-me@example.com")
    email_sender.sent.clear()  # discard the registration's verification email

    forgot_resp = await client.post("/api/v1/auth/forgot-password", json={"email": "reset-me@example.com"})
    assert forgot_resp.status_code == 202
    assert len(email_sender.sent) == 1
    token = _extract_token(email_sender.sent[0].text_body)

    reset_resp = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "brand-new-password-123"}
    )
    assert reset_resp.status_code == 200, reset_resp.text

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset-me@example.com", "password": "correct-horse-battery"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset-me@example.com", "password": "brand-new-password-123"}
    )
    assert new_login.status_code == 200

    # One-time use: the reset token can't be replayed.
    replay_resp = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "another-password-456"}
    )
    assert replay_resp.status_code == 400


async def test_forgot_password_unknown_email_gets_generic_response(
    client: AsyncClient, email_sender: _RecordingEmailSender
) -> None:
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert resp.status_code == 202
    assert len(email_sender.sent) == 0
