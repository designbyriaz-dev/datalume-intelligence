import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_email_sender_dep, get_email_sender_optional_dep, rate_limit_dependency
from app.core.config import get_settings
from app.core.cookies import (
    CSRF_HEADER,
    CSRF_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    generate_csrf_token,
    set_auth_cookies,
)
from app.core.security import (
    create_access_token,
    create_mfa_challenge_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.email_token import EmailTokenPurpose
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaRequiredOut,
    MfaSetupOut,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.user import UserOut
from app.services.audit import record_audit_event
from app.services.email import EmailMessage, EmailSender
from app.services.email_tokens import (
    EmailTokenError,
    consume_token,
    create_email_verification_token,
    create_password_reset_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_MFA_ISSUER = "DataLume Intelligence"

# Per-IP request limits on every auth endpoint that doesn't already
# require a valid credential to reach (refresh excluded — it needs a
# real refresh token, which is already the gate). Generous enough for
# real multi-attempt usage (a user mistyping a password a few times,
# retrying a flaky network request) while still bounding brute-force
# login guessing, registration spam, and email-bombing via
# forgot-password/resend-verification. See app/services/rate_limit.py.
_register_rate_limit = rate_limit_dependency("auth_register", max_requests=10, window_seconds=3600)
_login_rate_limit = rate_limit_dependency("auth_login", max_requests=10, window_seconds=300)
_verify_email_rate_limit = rate_limit_dependency("auth_verify_email", max_requests=10, window_seconds=3600)
_resend_verification_rate_limit = rate_limit_dependency("auth_resend_verification", max_requests=5, window_seconds=3600)
_forgot_password_rate_limit = rate_limit_dependency("auth_forgot_password", max_requests=5, window_seconds=3600)
_reset_password_rate_limit = rate_limit_dependency("auth_reset_password", max_requests=10, window_seconds=3600)
# A 6-digit TOTP code is brute-forceable (1 in 1,000,000 per guess) —
# this is the one unauthenticated MFA endpoint, same threat model as
# /login, so it gets the same tight per-IP limit.
_mfa_verify_rate_limit = rate_limit_dependency("auth_mfa_verify", max_requests=10, window_seconds=300)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender | None = Depends(get_email_sender_optional_dep),
) -> User:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    invite_entry = None
    if payload.invite_token:
        try:
            invite_entry = await consume_token(db, payload.invite_token, purpose=EmailTokenPurpose.ORG_INVITE)
        except EmailTokenError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        if invite_entry.target_email is None or invite_entry.target_email.lower() != payload.email.lower():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "This invite was sent to a different email address."
            )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_verified=False,
    )
    db.add(user)
    await db.flush()
    await record_audit_event(db, event_type="auth.user_registered", actor_user_id=user.id)

    if invite_entry is not None:
        membership = Membership(
            user_id=user.id,
            organization_id=invite_entry.organization_id,
            role=MembershipRole(invite_entry.role),
        )
        db.add(membership)
        await record_audit_event(
            db,
            event_type="organization.invite_accepted",
            actor_user_id=user.id,
            organization_id=invite_entry.organization_id,
        )

    # Best-effort: registration succeeds either way. Without SMTP
    # configured, the account is simply usable-but-unverified, same as
    # before this feature existed. Also catches a real-but-transient SMTP
    # failure (provider hiccup, network blip) once SMTP *is* configured —
    # without this, the send call above would raise straight out of the
    # request and turn a working registration into a 500. The user can
    # still get a verification email later via resend-verification
    # (which does use the non-optional get_email_sender_dep and
    # correctly 503s if sending is broken at the time).
    if email_sender is not None:
        raw_token = await create_email_verification_token(db, user.id)
        verify_url = f"{get_settings().frontend_base_url}/verify-email?token={raw_token}"
        try:
            email_sender.send(
                EmailMessage(
                    to=user.email,
                    subject="Verify your DataLume Intelligence account",
                    text_body=(
                        f"Welcome to DataLume Intelligence, {user.full_name}.\n\n"
                        f"Verify your email address:\n{verify_url}\n\n"
                        "This link expires in 24 hours."
                    ),
                )
            )
        except Exception:
            pass

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_login_rate_limit)])
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    invalid_credentials = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if user is None or not verify_password(payload.password, user.hashed_password):
        # Only recorded against a real user when the email matched but the
        # password didn't — an unknown email records no actor_user_id
        # rather than guessing, so the log never implies an account
        # exists for an email that doesn't.
        await record_audit_event(
            db,
            event_type="auth.login_failed",
            actor_user_id=user.id if user else None,
            metadata={"email": payload.email},
        )
        await db.commit()
        raise invalid_credentials
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    if user.mfa_enabled:
        # Password already verified above — this proves it without
        # issuing a real access/refresh token yet. The challenge token
        # can't be used as a bearer credential anywhere else
        # (get_current_user only accepts type == "access") and expires
        # in 5 minutes. Audit-logging "login_succeeded" here would be
        # premature — the login isn't complete until /auth/mfa/verify
        # actually succeeds, so that event is recorded there instead.
        challenge_token = create_mfa_challenge_token(user.id)
        # A Response returned directly bypasses response_model entirely
        # (FastAPI's documented behavior, already relied on in
        # organizations.py's invite_member) — needed here since this
        # branch returns a different shape than TokenResponse.
        return JSONResponse(
            content=MfaRequiredOut(challenge_token=challenge_token).model_dump()
        )

    await record_audit_event(db, event_type="auth.login_succeeded", actor_user_id=user.id)
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    set_auth_cookies(
        response, refresh_token=refresh_token, csrf_token=generate_csrf_token(), settings=get_settings()
    )

    # refresh_token is still returned in the body too — a non-browser
    # API client (script, mobile app, this project's own test suite)
    # has no cookie jar to rely on and needs it explicitly. The web
    # frontend receives it the same way but deliberately never persists
    # it anywhere; the httpOnly cookie set above is what it actually
    # relies on for refreshing.
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/mfa/verify", response_model=TokenResponse, dependencies=[Depends(_mfa_verify_rate_limit)])
async def mfa_verify(
    payload: MfaVerifyRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Completes a login that /auth/login paused on mfa_required=True.
    Takes the short-lived challenge_token from that response plus the
    6-digit code from the user's authenticator app, and — on success —
    issues real tokens exactly like a normal login would, including the
    refresh/CSRF cookies."""
    invalid_challenge = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge token")

    decoded = decode_token(payload.challenge_token)
    if decoded is None or decoded.get("type") != "mfa_challenge":
        raise invalid_challenge

    user = await db.get(User, decoded.get("sub"))
    if user is None or not user.is_active or not user.mfa_enabled or not user.mfa_secret:
        raise invalid_challenge

    # valid_window=1 tolerates the code from one 30s step before/after
    # now, for clock drift between the server and the user's device —
    # standard TOTP leniency, not a meaningfully wider guessing window.
    if not pyotp.TOTP(user.mfa_secret).verify(payload.code, valid_window=1):
        await record_audit_event(db, event_type="auth.mfa_verify_failed", actor_user_id=user.id)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect code")

    await record_audit_event(db, event_type="auth.mfa_verify_succeeded", actor_user_id=user.id)
    await record_audit_event(db, event_type="auth.login_succeeded", actor_user_id=user.id)
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    set_auth_cookies(
        response, refresh_token=refresh_token, csrf_token=generate_csrf_token(), settings=get_settings()
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MfaSetupOut:
    """Generates a new TOTP secret and stores it as *pending* —
    mfa_enabled stays False until /auth/mfa/enable confirms the user
    actually has it in an authenticator app by producing a correct code
    from it. Calling this again before enabling simply overwrites the
    previous pending secret (e.g. the user re-scans after a mistake);
    it never touches mfa_enabled or an already-active mfa_secret, so
    accidentally hitting this endpoint can't disable an MFA'd account."""
    if current_user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA is already enabled on this account.")

    secret = pyotp.random_base32()
    current_user.mfa_secret = secret
    await db.commit()

    otpauth_url = pyotp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name=_MFA_ISSUER)
    return MfaSetupOut(secret=secret, otpauth_url=otpauth_url)


@router.post("/mfa/enable", response_model=UserOut)
async def mfa_enable(
    payload: MfaEnableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if current_user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA is already enabled on this account.")
    if not current_user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Call /auth/mfa/setup first.")

    if not pyotp.TOTP(current_user.mfa_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect code — check your authenticator app and try again.")

    current_user.mfa_enabled = True
    await record_audit_event(db, event_type="auth.mfa_enabled", actor_user_id=current_user.id)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/mfa/disable", response_model=UserOut)
async def mfa_disable(
    payload: MfaDisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Requires re-entering the account password — not just an already-
    open session — since disabling MFA is a sensitive, security-reducing
    action (the same reason most providers gate it the same way)."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    await record_audit_event(db, event_type="auth.mfa_disabled", actor_user_id=current_user.id)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: RefreshRequest | None = None,
) -> TokenResponse:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    body_token = payload.refresh_token if payload else None
    if body_token:
        # Explicit bearer-style submission (script, test suite, mobile
        # app) — not an ambient credential a forged cross-site request
        # could trigger, so no CSRF check applies to this path.
        raw_refresh_token = body_token
    else:
        cookie_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
        if not cookie_token:
            raise invalid
        # The browser flow: the refresh token is reachable only via
        # this httpOnly cookie, sent automatically by the browser on
        # every request to this origin — exactly the ambient-credential
        # pattern CSRF protection exists for. Required here, and only
        # here, since every other endpoint still requires an explicit
        # Authorization header an attacker's page can't forge.
        csrf_cookie = request.cookies.get(CSRF_TOKEN_COOKIE)
        csrf_header = request.headers.get(CSRF_HEADER)
        if not csrf_cookie or not csrf_header or csrf_header != csrf_cookie:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
        raw_refresh_token = cookie_token

    decoded = decode_token(raw_refresh_token)
    if decoded is None or decoded.get("type") != "refresh":
        raise invalid

    user_id = decoded.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise invalid

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    set_auth_cookies(
        response, refresh_token=refresh_token, csrf_token=generate_csrf_token(), settings=get_settings()
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clears the refresh/CSRF cookies the browser flow relies on.
    There's no server-side token revocation list in this app (access
    and refresh tokens are stateless JWTs, valid until they expire
    either way) — logout only needs to stop the browser from presenting
    its credential, which clearing these cookies achieves. The frontend
    pairs this with dropping its in-memory access token."""
    clear_auth_cookies(response)


@router.post("/verify-email", response_model=UserOut, dependencies=[Depends(_verify_email_rate_limit)])
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> User:
    try:
        entry = await consume_token(db, payload.token, purpose=EmailTokenPurpose.EMAIL_VERIFICATION)
    except EmailTokenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    user = await db.get(User, entry.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or invalid token.")

    user.is_verified = True
    await record_audit_event(db, event_type="auth.email_verified", actor_user_id=user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_resend_verification_rate_limit)],
)
async def resend_verification(
    payload: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender_dep),
) -> dict[str, str]:
    generic_message = {
        "message": "If an account with that email exists and isn't verified yet, a new verification link has been sent."
    }

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or user.is_verified:
        # Same response either way — otherwise this endpoint could be
        # used to probe which emails have an (unverified) account.
        return generic_message

    raw_token = await create_email_verification_token(db, user.id)
    verify_url = f"{get_settings().frontend_base_url}/verify-email?token={raw_token}"
    email_sender.send(
        EmailMessage(
            to=user.email,
            subject="Verify your DataLume Intelligence account",
            text_body=f"Verify your email address:\n{verify_url}\n\nThis link expires in 24 hours.",
        )
    )
    await db.commit()
    return generic_message


@router.post(
    "/forgot-password", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(_forgot_password_rate_limit)]
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender_dep),
) -> dict[str, str]:
    generic_message = {"message": "If an account with that email exists, a password reset link has been sent."}

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        return generic_message

    raw_token = await create_password_reset_token(db, user.id)
    reset_url = f"{get_settings().frontend_base_url}/reset-password?token={raw_token}"
    email_sender.send(
        EmailMessage(
            to=user.email,
            subject="Reset your DataLume Intelligence password",
            text_body=f"Reset your password:\n{reset_url}\n\nThis link expires in 1 hour. If you didn't request this, ignore it.",
        )
    )
    await db.commit()
    return generic_message


@router.post(
    "/reset-password", status_code=status.HTTP_200_OK, dependencies=[Depends(_reset_password_rate_limit)]
)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        entry = await consume_token(db, payload.token, purpose=EmailTokenPurpose.PASSWORD_RESET)
    except EmailTokenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    user = await db.get(User, entry.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or invalid token.")

    user.hashed_password = hash_password(payload.new_password)
    await record_audit_event(db, event_type="auth.password_reset_completed", actor_user_id=user.id)
    await db.commit()
    return {"message": "Password has been reset. You can now log in with your new password."}
