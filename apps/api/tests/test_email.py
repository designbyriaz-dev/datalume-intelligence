"""Verifies SMTPEmailSender's own integration code — the HELO/STARTTLS/
LOGIN/SENDMAIL call sequence and arguments — by mocking smtplib.SMTP at
the class level. This is the same "prove the real integration code runs
correctly without a live account" approach as Stripe's webhook-signing
tests and the SSO fake-IdP tests: it does NOT prove a message reaches a
real mailbox (see app/services/email.py's module docstring)."""

from unittest.mock import MagicMock, patch

from app.services.email import EmailAttachment, EmailMessage, SMTPEmailSender, get_email_sender
from app.services.email import EmailNotConfiguredError


def test_get_email_sender_raises_when_unconfigured() -> None:
    import app.services.email as email_module

    with patch.object(email_module, "get_settings") as mock_settings:
        mock_settings.return_value.smtp_host = None
        try:
            get_email_sender()
            assert False, "expected EmailNotConfiguredError"
        except EmailNotConfiguredError:
            pass


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
        import base64

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
