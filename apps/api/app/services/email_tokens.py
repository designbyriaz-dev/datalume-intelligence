"""Generation and one-time consumption of EmailToken rows. Mirrors
app/services/api_keys.py's hashing approach (SHA-256 of a random
url-safe token; only the hash is stored) and app/services/sso.py's
consume_login_state (look up by hash, check expiry, delete-on-use so a
token can never be replayed)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_token import EmailToken, EmailTokenPurpose

VERIFICATION_TOKEN_EXPIRY = timedelta(hours=24)
PASSWORD_RESET_TOKEN_EXPIRY = timedelta(hours=1)
ORG_INVITE_TOKEN_EXPIRY = timedelta(days=7)


class EmailTokenError(Exception):
    """Unknown, expired, or already-used token."""


def _generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_email_verification_token(db: AsyncSession, user_id: str) -> str:
    raw_token = _generate_raw_token()
    db.add(
        EmailToken(
            token_hash=hash_token(raw_token),
            purpose=EmailTokenPurpose.EMAIL_VERIFICATION,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + VERIFICATION_TOKEN_EXPIRY,
        )
    )
    await db.flush()
    return raw_token


async def create_password_reset_token(db: AsyncSession, user_id: str) -> str:
    raw_token = _generate_raw_token()
    db.add(
        EmailToken(
            token_hash=hash_token(raw_token),
            purpose=EmailTokenPurpose.PASSWORD_RESET,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + PASSWORD_RESET_TOKEN_EXPIRY,
        )
    )
    await db.flush()
    return raw_token


async def create_org_invite_token(
    db: AsyncSession, *, target_email: str, organization_id: str, role: str
) -> str:
    raw_token = _generate_raw_token()
    db.add(
        EmailToken(
            token_hash=hash_token(raw_token),
            purpose=EmailTokenPurpose.ORG_INVITE,
            target_email=target_email,
            organization_id=organization_id,
            role=role,
            expires_at=datetime.now(timezone.utc) + ORG_INVITE_TOKEN_EXPIRY,
        )
    )
    await db.flush()
    return raw_token


async def peek_token(db: AsyncSession, raw_token: str, *, purpose: EmailTokenPurpose) -> EmailToken:
    """Looks up a token WITHOUT consuming it — for previewing an org
    invite before the invitee has registered. Still validates expiry
    and prior use, since a preview of a dead token should say so."""
    result = await db.execute(select(EmailToken).where(EmailToken.token_hash == hash_token(raw_token)))
    entry = result.scalar_one_or_none()
    if entry is None or entry.purpose != purpose:
        raise EmailTokenError("Unknown or invalid token.")
    if entry.used_at is not None:
        raise EmailTokenError("This link has already been used.")
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip (naive
    # datetimes returned); Postgres preserves it. Same quirk documented
    # in app/services/sso.py's consume_login_state.
    now = datetime.now(timezone.utc).replace(tzinfo=entry.expires_at.tzinfo)
    if entry.expires_at < now:
        raise EmailTokenError("This link has expired.")
    return entry


async def consume_token(db: AsyncSession, raw_token: str, *, purpose: EmailTokenPurpose) -> EmailToken:
    """Looks up, validates, and marks a token used in one step. Callers
    must still commit. Raises EmailTokenError for any invalid state so
    there's one place that decides "is this token usable right now" —
    callers don't each re-implement the expiry/reuse checks."""
    entry = await peek_token(db, raw_token, purpose=purpose)
    entry.used_at = datetime.now(timezone.utc)
    return entry
