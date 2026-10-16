from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership, MembershipRole
from app.models.workspace import Workspace

# Roles permitted to manage organization membership and settings.
ORG_MANAGE_ROLES = {MembershipRole.OWNER, MembershipRole.ADMIN}

# Roles permitted to write data (upload datasets, run cleaning operations)
# within an organization workspace. Viewer and Auditor are read-only by
# design — see the brief's role definitions.
WORKSPACE_WRITE_ROLES = {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST}


async def get_membership(db: AsyncSession, user_id: str, organization_id: str) -> Membership | None:
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def require_membership(db: AsyncSession, user_id: str, organization_id: str) -> Membership:
    membership = await get_membership(db, user_id, organization_id)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")
    return membership


async def require_org_manager(db: AsyncSession, user_id: str, organization_id: str) -> Membership:
    membership = await require_membership(db, user_id, organization_id)
    if MembershipRole(membership.role) not in ORG_MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return membership


async def require_workspace_access(db: AsyncSession, user_id: str, workspace: Workspace) -> None:
    """Enforce tenant isolation: a user may access a workspace only if they
    own it personally, or are a member of the organization that owns it."""
    if workspace.owner_user_id is not None:
        if workspace.owner_user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this workspace")
        return

    if workspace.organization_id is not None:
        await require_membership(db, user_id, workspace.organization_id)
        return

    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Workspace has no owner")


async def require_workspace_write_access(db: AsyncSession, user_id: str, workspace: Workspace) -> None:
    """Like require_workspace_access, but additionally rejects Viewer and
    Auditor members of an organization workspace — they can read data but
    not upload, clean, or otherwise mutate it."""
    if workspace.owner_user_id is not None:
        if workspace.owner_user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this workspace")
        return

    if workspace.organization_id is not None:
        membership = await require_membership(db, user_id, workspace.organization_id)
        if MembershipRole(membership.role) not in WORKSPACE_WRITE_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit write access")
        return

    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Workspace has no owner")
