from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    # Set when registering from an organization-invite link
    # (app/api/v1/routers/organizations.py's GET /invites/{token}) — on
    # success, also creates the matching Membership. The invite's own
    # email must match this request's email; see auth.py's register().
    invite_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # Optional: a browser client omits this and relies on the httpOnly
    # refresh_token cookie instead (see /auth/refresh in
    # app/api/v1/routers/auth.py); a non-browser API client (scripts,
    # the test suite, a mobile app) can still pass it explicitly here,
    # exactly as before this field became optional.
    refresh_token: str | None = None


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class MfaRequiredOut(BaseModel):
    """What /auth/login returns instead of TokenResponse when the account
    has MFA enabled — documented here for OpenAPI, but the endpoint
    actually returns this as a plain JSONResponse (bypassing
    response_model=TokenResponse), the same established pattern
    app/api/v1/routers/organizations.py's invite_member uses for its own
    second response shape."""

    mfa_required: bool = True
    challenge_token: str


class MfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=6)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_url: str


class MfaEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaDisableRequest(BaseModel):
    password: str


class AccountDeletionRequest(BaseModel):
    password: str
