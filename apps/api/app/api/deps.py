from collections.abc import AsyncGenerator, Awaitable, Callable

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.ai.llm_client import LLMClient, LLMNotConfiguredError
from app.services.ai.llm_client import get_llm_client as _get_llm_client
from app.services.api_keys import looks_like_api_key, resolve_user_for_api_key
from app.services.email import EmailNotConfiguredError, EmailSender
from app.services.email import get_email_sender as _get_email_sender
from app.services.rate_limit import check_rate_limit
from app.services.storage import ObjectStorage, get_storage
from app.services.stripe_billing import BillingNotConfiguredError, StripeBillingClient
from app.services.stripe_billing import get_stripe_client as _get_stripe_client

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error

    if looks_like_api_key(token):
        user = await resolve_user_for_api_key(db, token)
        if user is None:
            raise credentials_error
        await db.commit()
        return user

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_error

    return user


async def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    """Gate for the admin dashboard (app/api/v1/routers/admin.py). There
    is no API path that sets is_platform_admin — see
    scripts/grant_admin.py — so reaching this check at all already
    required direct database access to grant, not just a role in some
    organization."""
    if not current_user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin access required")
    return current_user


def get_object_storage() -> ObjectStorage:
    return get_storage()


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """A fresh httpx.AsyncClient per request, used for outbound webhook
    delivery (app/services/webhooks.py). Tests override this with a
    client built on httpx.MockTransport so delivery is exercised for
    real, with no actual network call."""
    async with httpx.AsyncClient() as client:
        yield client


def get_llm_client_dep() -> LLMClient:
    """FastAPI dependency wrapping app.services.ai.llm_client.get_llm_client
    — converts the "not configured" case into a clean 503 instead of a
    raw 500, and gives tests a single override point for a fake client."""
    try:
        return _get_llm_client()
    except LLMNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def get_stripe_client_dep() -> StripeBillingClient:
    """Same pattern as get_llm_client_dep, for Stripe."""
    try:
        return _get_stripe_client()
    except BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def get_email_sender_dep() -> EmailSender:
    """Same pattern as get_llm_client_dep/get_stripe_client_dep — use this
    where the caller's whole job IS to send an email (resend-verification,
    forgot-password), so a 503 is the honest response when unconfigured."""
    try:
        return _get_email_sender()
    except EmailNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def get_email_sender_optional_dep() -> EmailSender | None:
    """For call sites where sending an email is a best-effort side
    effect, not the point of the request (registration; inviting an
    email with no account yet, which falls back to its pre-Phase-7
    behavior when unconfigured) — returns None instead of raising, so
    the primary action still succeeds without email configured."""
    try:
        return _get_email_sender()
    except EmailNotConfiguredError:
        return None


def rate_limit_dependency(
    bucket_prefix: str, max_requests: int, window_seconds: int
) -> Callable[[Request, AsyncSession], Awaitable[None]]:
    """FastAPI dependency factory: `Depends(rate_limit_dependency("login",
    10, 300))` limits a route to 10 requests per 300s per client IP.
    Keyed on `request.client.host` — this app isn't behind a
    reverse proxy that sets X-Forwarded-For in this environment, so
    there's no trusted header to prefer over the direct connection's
    address; add that translation here (and only here) if that changes,
    rather than at each call site.

    Raises 429 rather than letting the route run when the bucket is
    over its limit for the current fixed window (see
    app/services/rate_limit.py for why fixed-window, and why a database
    table rather than Redis)."""

    async def dependency(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        client_host = request.client.host if request.client else "unknown"
        bucket_key = f"{bucket_prefix}:{client_host}"
        allowed = await check_rate_limit(
            db, bucket_key=bucket_key, max_requests=max_requests, window_seconds=window_seconds
        )
        if not allowed:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please try again later.")

    return dependency
