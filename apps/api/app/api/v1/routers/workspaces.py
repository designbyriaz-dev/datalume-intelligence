from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.db.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceSettingsUpdate
from app.services.account_deletion import delete_workspace
from app.services.audit import record_audit_event
from app.services.authz import (
    require_membership,
    require_workspace_access,
    require_workspace_delete_access,
    require_workspace_write_access,
)
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    if payload.organization_id is not None:
        await require_membership(db, current_user.id, payload.organization_id)
        workspace = Workspace(
            name=payload.name,
            industry=payload.industry,
            organization_id=payload.organization_id,
        )
    else:
        workspace = Workspace(
            name=payload.name,
            industry=payload.industry,
            owner_user_id=current_user.id,
        )

    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("", response_model=list[WorkspaceOut])
async def list_my_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Workspace]:
    org_ids_subquery = select(Membership.organization_id).where(Membership.user_id == current_user.id)
    result = await db.execute(
        select(Workspace).where(
            or_(
                Workspace.owner_user_id == current_user.id,
                Workspace.organization_id.in_(org_ids_subquery),
            )
        )
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    workspace = (
        await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    await require_workspace_access(db, current_user.id, workspace)
    return workspace


@router.patch("/{workspace_id}/settings", response_model=WorkspaceOut)
async def update_workspace_settings(
    workspace_id: str,
    payload: WorkspaceSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    workspace = (
        await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    await require_workspace_write_access(db, current_user.id, workspace)

    workspace.kpi_window_months = payload.kpi_window_months
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_endpoint(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> None:
    """Irreversible: deletes the workspace and every dataset, report,
    dashboard, scheduled report, webhook, and saved scenario inside it —
    see app/services/account_deletion.py for exactly what cascades and
    what gets cleaned up in object storage."""
    workspace = (
        await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    await require_workspace_delete_access(db, current_user.id, workspace)

    # Recorded org-scoped (or unscoped for a personal workspace), not
    # workspace-scoped — a workspace-scoped AuditLog row would itself be
    # cascade-deleted by the deletion this is recording. Must happen
    # before delete_workspace, not after.
    await record_audit_event(
        db,
        event_type="workspace.deleted",
        actor_user_id=current_user.id,
        organization_id=workspace.organization_id,
        metadata={"workspace_id": workspace.id, "workspace_name": workspace.name},
    )
    await delete_workspace(db, storage, workspace)
