from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

settings = get_settings()


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str, expires_delta: timedelta, token_type: Literal["access", "refresh", "mfa_challenge"]
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, timedelta(minutes=settings.access_token_expire_minutes), "access")


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, timedelta(minutes=settings.refresh_token_expire_minutes), "refresh")


def create_mfa_challenge_token(user_id: str) -> str:
    """Issued by /auth/login in place of access+refresh tokens when the
    account has MFA enabled — proves the password check already passed,
    without itself being usable as a credential for any other endpoint
    (get_current_user only accepts type == "access"). Short-lived (5
    minutes) since it's the thing an attacker who already has the
    password would try to replay against /auth/mfa/verify."""
    return _create_token(user_id, timedelta(minutes=5), "mfa_challenge")


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
