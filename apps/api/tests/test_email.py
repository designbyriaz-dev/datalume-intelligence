"""Verifies SMTPEmailSender's own integration code — the HELO/STARTTLS/
LOGIN/SENDMAIL call sequence and arguments — by mocking smtplib.SMTP at
the class level, and ResendEmailSender's HTTP call the same way by
mocking httpx.post. This is the same "prove the real integration code
runs correctly without a live account" approach as Stripe's webhook-
signing tests and the SSO fake-IdP tests: it does NOT prove a message
reaches a real mailbox (see app/services/email.py's module docstring)."""

import base64
from unittest.mock import MagicMock, patch

from app.services.email import (
    EmailAttachment,
    EmailMessage,
    EmailNotConfiguredError,
    ResendEmailSender,
    SMTPEmailSender,
    get_email_sender,
)


def test_get_email_sender_raises_when_unconfigured() -> None:
    import app.services.email as email_module

    with patch.object(email_module, "get_settings") as mock_settings:
        mock_settings.return_value.resend_api_key = None
        mock_settings.return_value.smtp_host = None
        try:
            get_email_sender()
            assert False, "expected EmailNotConfiguredError"
        except EmailNotConfiguredError:
            pass


def test_get_email_sender_prefers_resend_over_smtp_when_both_set() -> None:
    import app.services.email as email_module

    with patch.object(email_module, "get_settings") as mock_settings:
        mock_settings.return_value.resend_api_key = "re_test_key"
        mock_settings.return_value.smtp_host = "smtp.example.test"
        mock_settings.return_value.smtp_from_email = "no-reply@datalume.example"

        sender = get_email_sender()

        assert isinstance(sender, ResendEmailSender)


def test_smtp_email_sender_sends_with_tls_and_auth() -> None:
    sender = SMTPEmailSender(
        host="smtp.example.test",
        port=587,
        username="apikey",
        password="secret",
        use_tls=True,
        from_email="no-reply@datalume.example",
    )
    message = EmailMessage(
        to="someone@example.com",
        subject="Hello",
        text_body="Plain text body",
        html_body="<p>HTML body</p>",
    )

    with patch("app.services.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        sender.send(message)

        mock_smtp_cls.assert_called_once_with("smtp.example.test", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("apikey", "secret")
        assert mock_server.sendmail.call_count == 1
        from_addr, to_addrs, raw_message = mock_server.sendmail.call_args[0]
        assert from_addr == "no-reply@datalume.example"
        assert to_addrs == ["someone@example.com"]
        assert "Plain text body" in raw_message
        assert "HTML body" in raw_message
        assert "Subject: Hello" in raw_message


def test_smtp_email_sender_attaches_a_file() -> None:
    """Used by scheduled report delivery (app/services/scheduled_reports.py)
    to attach the generated PDF directly, since this app has no
    unauthenticated download route to link to instead."""
    sender = SMTPEmailSender(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        use_tls=False,
        from_email="no-reply@datalume.example",
    )
    message = EmailMessage(
        to="someone@example.com",
        subject="Your scheduled report",
        text_body="Attached is your scheduled report.",
        attachments=[
            EmailAttachment(filename="report.pdf", content=b"%PDF-1.4 fake pdf bytes", content_type="application/pdf")
        ],
    )

    with patch("app.services.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        sender.send(message)

        raw_message = mock_server.sendmail.call_args[0][2]
        assert "Content-Type: application/pdf" in raw_message
        assert 'filename="report.pdf"' in raw_message
        assert "Attached is your scheduled report." in raw_message
        # The raw PDF bytes are base64-encoded by MIMEApplication, not
        # embedded verbatim — assert the encoded form is present rather
        # than the literal bytes, which wouldn't survive encoding.
        assert base64.b64encode(b"%PDF-1.4 fake pdf bytes").decode() in raw_message


def test_smtp_email_sender_skips_tls_and_auth_when_not_configured() -> None:
    sender = SMTPEmailSender(
        host="localhost",
        port=1025,
        username=None,
        password=None,
        use_tls=False,
        from_email="no-reply@datalume.example",
    )
    message = EmailMessage(to="someone@example.com", subject="Hi", text_body="Body")

    with patch("app.services.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        sender.send(message)

        mock_server.starttls.assert_not_called()
        mock_server.login.assert_not_called()
        mock_server.sendmail.assert_called_once()


def test_resend_email_sender_posts_to_resend_api() -> None:
    sender = ResendEmailSender(api_key="re_test_key", from_email="no-reply@datalume.example")
    message = EmailMessage(
        to="someone@example.com",
        subject="Hello",
        text_body="Plain text body",
        html_body="<p>HTML body</p>",
    )

    with patch("app.services.email.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

        sender.send(message)

        mock_post.assert_called_once()
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert url == "https://api.resend.com/emails"
        assert kwargs["headers"] == {"Authorization": "Bearer re_test_key"}
        payload = kwargs["json"]
        assert payload["from"] == "no-reply@datalume.example"
        assert payload["to"] == ["someone@example.com"]
        assert payload["subject"] == "Hello"
        assert payload["text"] == "Plain text body"
        assert payload["html"] == "<p>HTML body</p>"
        mock_post.return_value.raise_for_status.assert_called_once()


def test_resend_email_sender_omits_html_when_not_provided() -> None:
    sender = ResendEmailSender(api_key="re_test_key", from_email="no-reply@datalume.example")
    message = EmailMessage(to="someone@example.com", subject="Hi", text_body="Body")

    with patch("app.services.email.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

        sender.send(message)

        payload = mock_post.call_args[1]["json"]
        assert "html" not in payload


def test_resend_email_sender_base64_encodes_attachments() -> None:
    """Used by scheduled report delivery (app/services/scheduled_reports.py)
    the same way SMTPEmailSender's attachment support is — see
    test_smtp_email_sender_attaches_a_file above."""
    sender = ResendEmailSender(api_key="re_test_key", from_email="no-reply@datalume.example")
    message = EmailMessage(
        to="someone@example.com",
        subject="Your scheduled report",
        text_body="Attached is your scheduled report.",
        attachments=[
            EmailAttachment(filename="report.pdf", content=b"%PDF-1.4 fake pdf bytes", content_type="application/pdf")
        ],
    )

    with patch("app.services.email.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

        sender.send(message)

        payload = mock_post.call_args[1]["json"]
        assert payload["attachments"] == [
            {
                "filename": "report.pdf",
                "content": base64.b64encode(b"%PDF-1.4 fake pdf bytes").decode("ascii"),
            }
        ]


def test_resend_email_sender_raises_on_http_error() -> None:
    sender = ResendEmailSender(api_key="re_bad_key", from_email="no-reply@datalume.example")
    message = EmailMessage(to="someone@example.com", subject="Hi", text_body="Body")

    with patch("app.services.email.httpx.post") as mock_post:
        import httpx

        response = MagicMock(status_code=401)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=response
        )
        mock_post.return_value = response

        try:
            sender.send(message)
            assert False, "expected httpx.HTTPStatusError"
        except httpx.HTTPStatusError:
            pass
