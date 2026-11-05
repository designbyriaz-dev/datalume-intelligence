"""Verifies branded_cta_email_html renders the given content into valid-
looking HTML with no raw interpolation bugs (unescaped braces, missing
values) — not a rendering/visual test, since there's no HTML renderer
in this suite to check pixels against."""

from app.services.email_templates import branded_cta_email_html


def test_branded_cta_email_html_includes_all_given_content() -> None:
    html = branded_cta_email_html(
        heading="Verify your email",
        intro_html="Welcome, <strong>Jane</strong>.",
        button_label="Verify email",
        button_url="https://example.com/verify-email?token=abc123",
        footer_note="This link expires in 24 hours.",
    )

    assert "Verify your email" in html
    assert "Welcome, <strong>Jane</strong>." in html
    assert "Verify email" in html
    # The URL must appear three times: the button's href, the fallback
    # link's href, and the fallback link's visible display text.
    assert html.count("https://example.com/verify-email?token=abc123") == 3
    assert "This link expires in 24 hours." in html
    assert "DataLume" in html and "Intelligence" in html


def test_branded_cta_email_html_is_well_formed() -> None:
    html = branded_cta_email_html(
        heading="Reset your password",
        intro_html="We received a request to reset your password.",
        button_label="Reset password",
        button_url="https://example.com/reset-password?token=xyz",
        footer_note="This link expires in 1 hour.",
    )

    assert html.strip().startswith("<!DOCTYPE html>")
    assert html.count("<table") == html.count("</table>")
    assert html.count("<a ") == html.count("</a>")
