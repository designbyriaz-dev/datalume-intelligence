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


def _cookie_security(settings: Settings) -> tuple[bool, str]:
    # Secure (HTTPS-only) is gated on environment, mirroring
    # app/services/storage.py's existing "environment == production"
    # pattern — this app runs over plain http://localhost in dev, where
    # a Secure cookie would simply never be sent by the browser at all.
    #
    # SameSite follows from that same flag rather than being hardcoded,
    # because the two environments have genuinely different "site"
    # relationships between frontend and API: in local dev both run on
    # localhost (different ports only), which browsers treat as
    # same-site, so Lax works and is the safer default. In production
    # this app's frontend and API are deployed on different Railway
    # subdomains (e.g. *.up.railway.app) — if that suffix is itself a
    # registered public suffix (common for multi-tenant PaaS, done
    # specifically to stop cross-tenant cookie leakage), those
    # subdomains are cross-site to each other even though they share a
    # literal domain ending. Lax cookies aren't sent on cross-site
    # fetch/XHR at all (only top-level navigation), which is exactly
    # the bug this was: the browser silently never sent the refresh
    # cookie back to the API, so every session died on the very first
    # cross-origin request. None is the correct SameSite value for a
    # legitimately cross-origin frontend/API split, and the double-
    # submit CSRF check below (required on this cookie's one consuming
    # endpoint, /refresh) already covers the forgery risk Lax/Strict
    # would otherwise add as defense-in-depth. None requires Secure —
    # browsers silently drop a None cookie without it — which is why
    # this only applies when secure is True (production); dev keeps Lax.
    secure = settings.environment == "production"
    samesite = "none" if secure else "lax"
    return secure, samesite


def set_auth_cookies(response: Response, *, refresh_token: str, csrf_token: str, settings: Settings) -> None:
    secure, samesite = _cookie_security(settings)
    max_age = settings.refresh_token_expire_minutes * 60

    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
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
        samesite=samesite,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    # Must pass the same secure/samesite the cookie was set with — these
    # are part of a cookie's identity in the browser's jar, so a
    # delete_cookie call with mismatched attributes (Starlette defaults
    # to secure=False, samesite="lax") sets a *different* cookie rather
    # than clearing the real one, leaving the user still logged in.
    secure, samesite = _cookie_security(settings)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/", secure=secure, samesite=samesite)
    response.delete_cookie(CSRF_TOKEN_COOKIE, path="/", secure=secure, samesite=samesite)
