from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.resolvers import get_tenancy_chain_or_404
from app.db.session import get_db
from app.models.inventory import Inventory, InventoryItem
from app.models.user import User
from app.schemas.inventory import (
    InventoryComparisonOut,
    InventoryCreate,
    InventoryItemDiff,
    InventoryOut,
)
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.inventory_compare import compare_inventories

router = APIRouter(tags=["inventories"])


async def _get_inventory_or_404(db: AsyncSession, inventory_id: str) -> Inventory:
    result = await db.execute(
        select(Inventory).options(selectinload(Inventory.items)).where(Inventory.id == inventory_id)
    )
    inventory = result.scalar_one_or_none()
    if inventory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory not found")
    return inventory


@router.post(
    "/tenancies/{tenancy_id}/inventories",
    response_model=InventoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_inventory(
    tenancy_id: str,
    payload: InventoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Inventory:
    _tenancy, _property, workspace = await get_tenancy_chain_or_404(db, tenancy_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    inventory = Inventory(
        tenancy_id=tenancy_id,
        inventory_type=payload.inventory_type,
        inspection_date=payload.inspection_date,
        notes=payload.notes,
        created_by_user_id=current_user.id,
        items=[
            InventoryItem(
                room=item.room,
                item_name=item.item_name,
                condition=item.condition,
                notes=item.notes,
            )
            for item in payload.items
        ],
    )
    db.add(inventory)
    await db.commit()
    # Deliberately no db.refresh() here: this session's expire_on_commit
    # is False (app/db/session.py), so the in-memory `inventory.items`
    # list set above already holds the real, flushed InventoryItem rows
    # (ids and server-generated timestamps included, via RETURNING) —
    # refresh() would re-expire that relationship, forcing a lazy load
    # that fails outside an awaited context during response
    # serialization (a real MissingGreenlet error this caught).
    return inventory


@router.get("/tenancies/{tenancy_id}/inventories", response_model=list[InventoryOut])
async def list_inventories(
    tenancy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Inventory]:
    _tenancy, _property, workspace = await get_tenancy_chain_or_404(db, tenancy_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Inventory)
        .options(selectinload(Inventory.items))
        .where(Inventory.tenancy_id == tenancy_id)
        .order_by(Inventory.inspection_date)
    )
    return list(result.scalars().all())


@router.get("/inventories/{inventory_id}", response_model=InventoryOut)
async def get_inventory(
    inventory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Inventory:
    inventory = await _get_inventory_or_404(db, inventory_id)
    _tenancy, _property, workspace = await get_tenancy_chain_or_404(db, inventory.tenancy_id)
    await require_workspace_access(db, current_user.id, workspace)
    return inventory


@router.delete("/inventories/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory(
    inventory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    inventory = await _get_inventory_or_404(db, inventory_id)
    _tenancy, _property, workspace = await get_tenancy_chain_or_404(db, inventory.tenancy_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(inventory)
    await db.commit()


@router.get("/inventories/{before_id}/compare/{after_id}", response_model=InventoryComparisonOut)
async def compare_inventory_pair(
    before_id: str,
    after_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InventoryComparisonOut:
    before = await _get_inventory_or_404(db, before_id)
    after = await _get_inventory_or_404(db, after_id)

    if before.tenancy_id != after.tenancy_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Both inventories must belong to the same tenancy")

    _tenancy, _property, workspace = await get_tenancy_chain_or_404(db, before.tenancy_id)
    await require_workspace_access(db, current_user.id, workspace)

    comparison = compare_inventories(before, after)
    return InventoryComparisonOut(
        before_inventory_id=before_id,
        after_inventory_id=after_id,
        items=[InventoryItemDiff(**item.__dict__) for item in comparison.items],
        added_count=comparison.added_count,
        removed_count=comparison.removed_count,
        changed_count=comparison.changed_count,
        unchanged_count=comparison.unchanged_count,
    )
