from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.resolvers import get_property_chain_or_404, get_tenancy_chain_or_404
from app.db.session import get_db
from app.models.maintenance import MaintenanceRequest
from app.models.user import User
from app.schemas.maintenance import MaintenanceRequestCreate, MaintenanceRequestOut, MaintenanceRequestUpdate
from app.services.authz import require_workspace_access, require_workspace_write_access

router = APIRouter(tags=["maintenance"])


async def _get_request_or_404(db: AsyncSession, request_id: str) -> MaintenanceRequest:
    request = await db.get(MaintenanceRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance request not found")
    return request


@router.post(
    "/properties/{property_id}/maintenance-requests",
    response_model=MaintenanceRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_request(
    property_id: str,
    payload: MaintenanceRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceRequest:
    _property, workspace = await get_property_chain_or_404(db, property_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    if payload.tenancy_id is not None:
        _tenancy, tenancy_property, _workspace = await get_tenancy_chain_or_404(db, payload.tenancy_id)
        if tenancy_property.id != property_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenancy_id does not belong to this property")

    request = MaintenanceRequest(
        property_id=property_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


@router.get("/properties/{property_id}/maintenance-requests", response_model=list[MaintenanceRequestOut])
async def list_maintenance_requests(
    property_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MaintenanceRequest]:
    _property, workspace = await get_property_chain_or_404(db, property_id)
    await require_workspace_access(db, current_user.id, workspace)

    query = select(MaintenanceRequest).where(MaintenanceRequest.property_id == property_id)
    if status_filter is not None:
        query = query.where(MaintenanceRequest.status == status_filter)
    result = await db.execute(query.order_by(MaintenanceRequest.reported_date.desc()))
    return list(result.scalars().all())


@router.get("/maintenance-requests/{request_id}", response_model=MaintenanceRequestOut)
async def get_maintenance_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceRequest:
    request = await _get_request_or_404(db, request_id)
    _property, workspace = await get_property_chain_or_404(db, request.property_id)
    await require_workspace_access(db, current_user.id, workspace)
    return request


@router.patch("/maintenance-requests/{request_id}", response_model=MaintenanceRequestOut)
async def update_maintenance_request(
    request_id: str,
    payload: MaintenanceRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceRequest:
    request = await _get_request_or_404(db, request_id)
    _property, workspace = await get_property_chain_or_404(db, request.property_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    for field, value in payload.model_dump().items():
        setattr(request, field, value)
    await db.commit()
    await db.refresh(request)
    return request


@router.delete("/maintenance-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    request = await _get_request_or_404(db, request_id)
    _property, workspace = await get_property_chain_or_404(db, request.property_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(request)
    await db.commit()
