"""Branded HTML for the handful of transactional emails that exist only
to get a user to click one link (email verification, password reset,
org invite). Before this, every one of those sent plain text with a
bare pasted URL — a shape that's genuinely a common spam-filter and
"does this look like phishing" visual signal, which is exactly what
surfaced the request to fix this (a real verification email landing in
Junk during live testing against a freshly-verified sending domain).

This narrows, but does not eliminate, that risk: a styled HTML email
with a clear button is not itself proof of sender reputation, and a
domain verified minutes ago has none yet — that only builds up over
real send volume and recipient engagement over time. Don't read
"branded now" as "will never land in spam."

Deliberately plain, table-based HTML (not flexbox/grid) — this is
standard practice for email specifically because many email clients
(Outlook chief among them) render with old, partial CSS support, not
a real browser engine.
"""

from __future__ import annotations

_BRAND_BLUE = "#3b6dfb"
_BRAND_NAVY = "#111f52"
_BODY_TEXT = "#1e293b"
_MUTED_TEXT = "#64748b"
_BORDER = "#e2e8f0"


def branded_cta_email_html(*, heading: str, intro_html: str, button_label: str, button_url: str, footer_note: str) -> str:
    """intro_html may contain simple inline HTML (e.g. <strong>); callers
    are responsible for escaping any user-supplied values they interpolate
    into it, the same way f-string text_body construction already assumes
    today."""
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background-color:#ffffff;border:1px solid {_BORDER};border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:28px 32px 0 32px;">
                <span style="font-size:18px;font-weight:700;color:{_BRAND_NAVY};">DataLume</span>
                <span style="font-size:18px;font-weight:700;color:{_BRAND_BLUE};"> Intelligence</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 0 32px;">
                <h1 style="margin:0 0 16px 0;font-size:20px;line-height:28px;color:{_BRAND_NAVY};">{heading}</h1>
                <div style="font-size:15px;line-height:24px;color:{_BODY_TEXT};">{intro_html}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px 0 32px;" align="center">
                <a href="{button_url}" style="display:inline-block;background-color:{_BRAND_BLUE};color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:12px 28px;border-radius:8px;">{button_label}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 0 32px;">
                <p style="margin:0;font-size:13px;line-height:20px;color:{_MUTED_TEXT};">
                  If the button doesn't work, copy and paste this link into your browser:<br />
                  <a href="{button_url}" style="color:{_BRAND_BLUE};word-break:break-all;">{button_url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 28px 32px;border-top:1px solid {_BORDER};margin-top:24px;">
                <p style="margin:20px 0 0 0;font-size:13px;line-height:20px;color:{_MUTED_TEXT};">{footer_note}</p>
              </td>
            </tr>
          </table>
          <p style="max-width:480px;margin:16px 0 0 0;font-size:12px;color:{_MUTED_TEXT};">DataLume Intelligence</p>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
