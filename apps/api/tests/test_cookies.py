"""Verifies app/core/cookies.py's Secure/SameSite logic directly — the
real bug this guards against (sessions dying on every cross-subdomain
request once deployed) only shows up in production, which
tests/test_auth.py's client never runs under, so it needs its own
test rather than relying on the dev-environment assertions there."""

from fastapi import Response

from app.core.config import Settings
from app.core.cookies import CSRF_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE, clear_auth_cookies, set_auth_cookies


def _settings(environment: str) -> Settings:
    return Settings(environment=environment)


def test_dev_cookies_are_lax_and_not_secure() -> None:
    response = Response()
    set_auth_cookies(response, refresh_token="rt", csrf_token="ct", settings=_settings("development"))

    cookies = response.headers.getlist("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith(f"{REFRESH_TOKEN_COOKIE}="))
    csrf_cookie = next(c for c in cookies if c.startswith(f"{CSRF_TOKEN_COOKIE}="))

    assert "SameSite=lax" in refresh_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Secure" not in refresh_cookie
    assert "Secure" not in csrf_cookie


def test_production_cookies_are_samesite_none_and_secure() -> None:
    """The actual fix: on a real deployment where the frontend and API
    are cross-site to each other (different Railway subdomains), a Lax
    cookie is never sent on the cross-origin fetch the browser flow
    depends on — None is required, and browsers silently drop a None
    cookie unless Secure is also set, which production already is."""
    response = Response()
    set_auth_cookies(response, refresh_token="rt", csrf_token="ct", settings=_settings("production"))

    cookies = response.headers.getlist("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith(f"{REFRESH_TOKEN_COOKIE}="))
    csrf_cookie = next(c for c in cookies if c.startswith(f"{CSRF_TOKEN_COOKIE}="))

    assert "SameSite=none" in refresh_cookie
    assert "SameSite=none" in csrf_cookie
    assert "Secure" in refresh_cookie
    assert "Secure" in csrf_cookie


def test_clear_auth_cookies_matches_the_attributes_it_was_set_with() -> None:
    """A delete_cookie call with mismatched Secure/SameSite sets a
    different cookie rather than clearing the real one (these
    attributes are part of a cookie's identity in the browser's jar) —
    so logout silently not working in production was the real risk
    this covers, not just a cosmetic mismatch."""
    response = Response()
    clear_auth_cookies(response, _settings("production"))

    cookies = response.headers.getlist("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith(f"{REFRESH_TOKEN_COOKIE}="))
    csrf_cookie = next(c for c in cookies if c.startswith(f"{CSRF_TOKEN_COOKIE}="))

    assert "SameSite=none" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "SameSite=none" in csrf_cookie
    assert "Secure" in csrf_cookie
