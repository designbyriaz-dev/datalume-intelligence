"""Audit event recording. This module instruments a deliberately chosen
subset of events, not every mutation in the app — see EVENT_TYPES below
for exactly which ones and where they're recorded. Treat this as a real,
working audit trail with documented coverage, not a claim of complete
governance logging.

Currently recorded, and where:
- auth.user_registered       — app/api/v1/routers/auth.py
- auth.login_succeeded       — app/api/v1/routers/auth.py
- auth.login_failed          — app/api/v1/routers/auth.py
- organization.created       — app/api/v1/routers/organizations.py
- organization.member_invited — app/api/v1/routers/organizations.py
- api_key.created            — app/api/v1/routers/api_keys.py
- api_key.revoked            — app/api/v1/routers/api_keys.py
- billing.plan_changed       — app/services/webhook_handlers.py
- billing.subscription_canceled — app/services/webhook_handlers.py
- admin.user_data_accessed   — app/api/v1/routers/admin.py (every time a
  platform admin lists user records — the brief's requirement that
  "customer data access by platform administrators must be ... audited")
- auth.email_verified          — app/api/v1/routers/auth.py
- auth.password_reset_completed — app/api/v1/routers/auth.py
- organization.invite_emailed  — app/api/v1/routers/organizations.py
  (an invite sent to an email with no existing account — distinct from
  organization.member_invited, which is an immediate membership grant
  to an existing account)
- organization.invite_accepted — app/api/v1/routers/auth.py (a new
  account created via an org-invite token, at registration)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

EVENT_TYPES = {
    "auth.user_registered",
    "auth.login_succeeded",
    "auth.login_failed",
    "organization.created",
    "organization.member_invited",
    "api_key.created",
    "api_key.revoked",
    "billing.plan_changed",
    "billing.subscription_canceled",
    "admin.user_data_accessed",
    "auth.email_verified",
    "auth.password_reset_completed",
    "organization.invite_emailed",
    "organization.invite_accepted",
}


async def record_audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    actor_user_id: str | None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Adds and flushes the entry; does NOT commit — call sites record
    the audit event as part of the same transaction as the action it
    describes, so the two can never disagree (an audit row for an action
    that didn't actually happen, or vice versa)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unregistered audit event_type: {event_type!r}. Add it to EVENT_TYPES first.")

    entry = AuditLog(
        event_type=event_type,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        event_metadata=metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry
