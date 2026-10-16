from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceSettingsUpdate
from app.services.authz import require_membership, require_workspace_access, require_workspace_write_access

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
