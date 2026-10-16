import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_http_client
from app.core.config import get_settings
from app.core.cookies import generate_csrf_token, set_auth_cookies
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.schemas.auth import TokenResponse
from app.schemas.sso import SSOCallbackRequest, SSOLoginResponse
from app.services.audit import record_audit_event
from app.services.sso import (
    OIDCNotConfiguredError,
    SSOError,
    build_authorization_url,
    consume_login_state,
    create_login_state,
    exchange_code_for_claims,
    fetch_discovery_document,
    get_oidc_config,
    resolve_or_create_user_from_oidc_claims,
)

router = APIRouter(prefix="/sso", tags=["sso"])


@router.get("/login", response_model=SSOLoginResponse)
async def sso_login(
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> SSOLoginResponse:
    try:
        config = get_oidc_config()
    except OIDCNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    try:
        discovery = await fetch_discovery_document(http_client, config.discovery_url)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not reach identity provider: {exc}") from exc

    state, code_verifier = await create_login_state(db)
    authorization_url = build_authorization_url(config, discovery, state=state, code_verifier=code_verifier)

    return SSOLoginResponse(authorization_url=authorization_url)


@router.post("/callback", response_model=TokenResponse)
async def sso_callback(
    payload: SSOCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> TokenResponse:
    try:
        config = get_oidc_config()
    except OIDCNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    try:
        code_verifier = await consume_login_state(db, payload.state)
    except SSOError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        discovery = await fetch_discovery_document(http_client, config.discovery_url)
        claims = await exchange_code_for_claims(
            http_client, config, discovery, code=payload.code, code_verifier=code_verifier
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Identity provider error: {exc}") from exc
    except SSOError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        user = await resolve_or_create_user_from_oidc_claims(db, claims)
    except SSOError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await record_audit_event(db, event_type="auth.login_succeeded", actor_user_id=user.id, metadata={"method": "oidc"})
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    set_auth_cookies(
        response, refresh_token=refresh_token, csrf_token=generate_csrf_token(), settings=get_settings()
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
