"""Self-serve deletion of a workspace or a whole account.

Every workspace-scoped row (datasets, versions, tables, dashboards,
reports, scheduled reports, webhooks, saved scenarios) cascade-deletes
at the DB level once its owning Workspace row is deleted — see each
model's own `workspace_id`/`dataset_id`/... ForeignKey(ondelete=...).
Object storage doesn't know about that cascade, so every storage key a
workspace actually used is collected and best-effort deleted first,
same "record, don't crash" principle as dunning.py's Stripe
cancellation — a storage provider outage must not block a user from
deleting their own data.

A full account deletion additionally best-effort cancels any live
Stripe subscription (so Stripe and this app can't end up disagreeing
about whether the account is still billed) before deleting the User
row itself. Content the user created inside a workspace they don't
personally own — an organization's shared workspace — is NOT deleted:
every `created_by_user_id`/`author_user_id`/`generated_by_user_id`
column that isn't itself an ownership link is `ondelete="SET NULL"`
(see alembic/versions/1e8b0cec90e4_nullable_creator_fields_for_account_.py),
so that content simply becomes attributed to no one, the same way a
deleted Reddit or GitHub account leaves its comments/commits behind.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Subscription
from app.models.dataset import Dataset, DatasetTable, DatasetVersion
from app.models.document import Document
from app.models.property import Property
from app.models.report import Report
from app.models.user import User
from app.models.workspace import Workspace
from app.services.audit import record_audit_event
from app.services.storage import ObjectStorage, delete_keys_best_effort

logger = logging.getLogger("datalume.account_deletion")


async def _collect_workspace_storage_keys(db: AsyncSession, workspace_id: str) -> list[str]:
    version_keys = (
        await db.execute(
            select(DatasetVersion.storage_key)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.workspace_id == workspace_id)
        )
    ).scalars().all()

    table_keys = (
        await db.execute(
            select(DatasetTable.data_storage_key)
            .join(DatasetVersion, DatasetVersion.id == DatasetTable.dataset_version_id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.workspace_id == workspace_id)
        )
    ).scalars().all()

    report_keys = (
        await db.execute(
            select(Report.storage_key)
            .join(DatasetTable, DatasetTable.id == Report.dataset_table_id)
            .join(DatasetVersion, DatasetVersion.id == DatasetTable.dataset_version_id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.workspace_id == workspace_id)
        )
    ).scalars().all()

    document_keys = (
        await db.execute(
            select(Document.storage_key)
            .join(Property, Property.id == Document.property_id)
            .where(Property.workspace_id == workspace_id)
        )
    ).scalars().all()

    return [k for k in (*version_keys, *table_keys, *report_keys, *document_keys) if k]


async def delete_workspace(db: AsyncSession, storage: ObjectStorage, workspace: Workspace) -> None:
    """Caller must already have checked delete access
    (authz.require_workspace_delete_access) and recorded its own audit
    event beforehand — a workspace-scoped AuditLog row is itself
    cascade-deleted the instant its workspace is (see AuditLog.workspace_id's
    ondelete="CASCADE"), so an event describing this deletion has to be
    organization-scoped or unscoped, not workspace-scoped, and has to
    exist before this runs, not after."""
    keys = await _collect_workspace_storage_keys(db, workspace.id)
    delete_keys_best_effort(storage, keys)

    await db.delete(workspace)
    await db.commit()


async def delete_own_account(db: AsyncSession, storage: ObjectStorage, user: User) -> None:
    """Deletes every personally-owned workspace (and its storage, same
    as delete_workspace above) and the User row itself. Organizations
    the user merely belongs to, and any content they created inside an
    organization's shared workspace, are left in place — see this
    module's docstring."""
    result = await db.execute(select(Subscription).where(Subscription.owner_user_id == user.id))
    subscription = result.scalar_one_or_none()
    if subscription is not None and subscription.stripe_subscription_id:
        try:
            from app.services.stripe_billing import get_stripe_client

            stripe_client = get_stripe_client()
            stripe_client.cancel_subscription(stripe_subscription_id=subscription.stripe_subscription_id)
        except Exception as exc:  # noqa: BLE001 - Stripe being unreachable/unconfigured must not block deletion
            logger.warning(
                "Failed to cancel Stripe subscription for user %s during account deletion: %s", user.id, exc
            )

    owned_workspace_ids = (
        await db.execute(select(Workspace.id).where(Workspace.owner_user_id == user.id))
    ).scalars().all()
    for workspace_id in owned_workspace_ids:
        keys = await _collect_workspace_storage_keys(db, workspace_id)
        delete_keys_best_effort(storage, keys)

    await record_audit_event(
        db,
        event_type="auth.account_deleted",
        actor_user_id=user.id,
        metadata={"email": user.email},
    )
    await db.delete(user)
    await db.commit()
