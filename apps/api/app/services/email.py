"""Transactional email. Four otherwise-finished features depend on this
one integration: email verification (app/api/v1/routers/auth.py),
password reset (same file), organization invites to not-yet-registered
users (app/api/v1/routers/organizations.py), and scheduled report
delivery (app/services/scheduled_reports.py), which attaches the
generated PDF directly rather than linking to it — this app has no
unauthenticated download route to link to, and an authenticated one
would need a magic token scheme of its own just for this.

IMPORTANT — read before trusting this "works": SMTPEmailSender is
written correctly against smtplib's documented API (HELO, STARTTLS,
LOGIN, SENDMAIL) and tests/test_email.py verifies that exact call
sequence and its arguments by mocking smtplib.SMTP at the class level —
the same "verify the real integration code path without a live
account/server" approach used for Stripe's webhook signing and the SSO
fake-IdP tests elsewhere in this codebase. What that does NOT prove: no
message has been sent to, or received by, a real mailbox in this
session. Set SMTP_HOST (+ SMTP_USERNAME/SMTP_PASSWORD if your provider
requires auth) to actually exercise this for the first time — any
standard SMTP provider works: Postmark, SendGrid's SMTP endpoint, AWS
SES SMTP, Gmail, or a self-hosted server.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

from app.core.config import get_settings


class EmailNotConfiguredError(Exception):
    """Raised when email-backed functionality is invoked but no
    SMTP_HOST is set. Routers turn this into either a clean 503 (when
    the caller needs the email to actually go out) or a silent no-op
    (when sending is best-effort, e.g. registration)."""


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    attachments: list[EmailAttachment] = field(default_factory=list)


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SMTPEmailSender:
    """A thin, direct wrapper over smtplib — deliberately not a third-
    party SDK, since every SMTP provider speaks the same protocol and
    this app doesn't need provider-specific features (templates,
    analytics) that would justify one."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        from_email: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_email = from_email

    def send(self, message: EmailMessage) -> None:
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(message.text_body, "plain"))
        if message.html_body:
            body.attach(MIMEText(message.html_body, "html"))

        if message.attachments:
            # A real attachment needs an outer "mixed" envelope around the
            # text/html alternative body — attaching straight onto an
            # "alternative" MIME part would make the attachment itself one
            # of the "alternative" renderings of the message, which most
            # mail clients render as a broken or missing body.
            mime = MIMEMultipart("mixed")
            mime.attach(body)
            for attachment in message.attachments:
                part = MIMEApplication(attachment.content, _subtype=attachment.content_type.split("/")[-1])
                part.add_header("Content-Disposition", "attachment", filename=attachment.filename)
                mime.attach(part)
        else:
            mime = body

        mime["Subject"] = message.subject
        mime["From"] = self._from_email
        mime["To"] = message.to

        with smtplib.SMTP(self._host, self._port, timeout=10) as server:
            if self._use_tls:
                server.starttls()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.sendmail(self._from_email, [message.to], mime.as_string())


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if not settings.smtp_host:
        raise EmailNotConfiguredError(
            "Transactional email is scaffolded (verification/reset/invite logic is "
            "tested) but no SMTP provider is connected — set SMTP_HOST (and "
            "SMTP_USERNAME/SMTP_PASSWORD if your provider requires auth). "
            "See docs/CHECKLIST.md."
        )
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        from_email=settings.smtp_from_email,
    )
