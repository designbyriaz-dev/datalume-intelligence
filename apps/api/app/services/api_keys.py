"""API key generation and verification. Keys look like
`dlk_<43 url-safe base64 chars>` (dlk = DataLume Key) — the prefix lets
app/api/deps.py distinguish an API key from a JWT at a glance without
trying to decode it first. Only a SHA-256 hash is ever persisted; the raw
key is returned to the caller exactly once, at creation, and is
unrecoverable after that (same as GitHub/Stripe/every other PAT system)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.user import User

KEY_PREFIX = "dlk_"
DISPLAY_PREFIX_LENGTH = 12  # "dlk_" + 8 chars, enough to recognize a key without exposing it


@dataclass
class GeneratedApiKey:
    raw_key: str
    key_prefix: str
    key_hash: str


def generate_api_key() -> GeneratedApiKey:
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    return GeneratedApiKey(
        raw_key=raw_key,
        key_prefix=raw_key[:DISPLAY_PREFIX_LENGTH],
        key_hash=hash_api_key(raw_key),
    )


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def looks_like_api_key(token: str) -> bool:
    return token.startswith(KEY_PREFIX)


async def resolve_user_for_api_key(db: AsyncSession, raw_key: str) -> User | None:
    """Looks up the key by hash, checks it's active, updates
    last_used_at, and returns the user it authenticates as — or None if
    the key is invalid/revoked. Caller is expected to commit (mirrors
    the billing quota pattern: this function mutates but doesn't decide
    the transaction boundary)."""
    key_hash = hash_api_key(raw_key)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None

    api_key.last_used_at = datetime.now(timezone.utc)

    user = await db.get(User, api_key.user_id)
    if user is None or not user.is_active:
        return None
    return user
