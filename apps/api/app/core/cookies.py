"""HttpOnly cookie helpers backing the browser refresh flow (see
/login, /refresh, /logout in app/api/v1/routers/auth.py). This is the
only part of this app's auth that changed: the access token the
frontend uses for every other request is still sent as an
`Authorization: Bearer` header exactly as before — kept in memory on
the frontend now, not localStorage, but the backend side of that path
(app/api/deps.py's get_current_user) is completely unchanged. Only the
longer-lived, more dangerous refresh token moved off of
browser-script-readable storage entirely, into an httpOnly cookie.
"""

import secrets

from fastapi import Response

from app.core.config import Settings

REFRESH_TOKEN_COOKIE = "refresh_token"
CSRF_TOKEN_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, *, refresh_token: str, csrf_token: str, settings: Settings) -> None:
    # Secure (HTTPS-only) is gated on environment, mirroring
    # app/services/storage.py's existing "environment == production"
    # pattern — this app runs over plain http://localhost in dev, where
    # a Secure cookie would simply never be sent by the browser at all.
    secure = settings.environment == "production"
    max_age = settings.refresh_token_expire_minutes * 60

    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Deliberately NOT httponly — the double-submit CSRF pattern needs
    # frontend JS to read this value and echo it back as a header on
    # state-changing cookie-authenticated requests. Its secrecy from
    # the browser's own page was never the point; what matters is that
    # an attacker's cross-site page can't read it (same-origin policy),
    # so it can't forge a matching header.
    response.set_cookie(
        CSRF_TOKEN_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/")
    response.delete_cookie(CSRF_TOKEN_COOKIE, path="/")
