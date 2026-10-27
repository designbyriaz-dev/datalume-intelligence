from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.resolvers import get_workspace_or_404
from app.db.session import get_db
from app.models.property import Property, RentLedgerEntry, Tenancy
from app.models.user import User
from app.schemas.property import (
    PropertyCreate,
    PropertyKPIsOut,
    PropertyOut,
    PropertyUpdate,
    RentLedgerEntryCreate,
    RentLedgerEntryOut,
    TenancyBalanceOut,
    TenancyCreate,
    TenancyOut,
    TenancyUpdate,
)
from app.services.authz import require_workspace_access, require_workspace_delete_access, require_workspace_write_access
from app.services.property_kpis import compute_portfolio_kpis, compute_tenancy_balance

router = APIRouter(tags=["properties"])


async def _get_property_or_404(db: AsyncSession, property_id: str) -> Property:
    property_ = await db.get(Property, property_id)
    if property_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    return property_


async def _get_tenancy_or_404(db: AsyncSession, tenancy_id: str) -> tuple[Tenancy, Property]:
    tenancy = await db.get(Tenancy, tenancy_id)
    if tenancy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenancy not found")
    property_ = await _get_property_or_404(db, tenancy.property_id)
    return tenancy, property_


@router.post(
    "/workspaces/{workspace_id}/properties",
    response_model=PropertyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_property(
    workspace_id: str,
    payload: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Property:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    property_ = Property(
        workspace_id=workspace_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(property_)
    await db.commit()
    await db.refresh(property_)
    return property_


@router.get("/workspaces/{workspace_id}/properties", response_model=list[PropertyOut])
async def list_properties(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Property]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Property).where(Property.workspace_id == workspace_id).order_by(Property.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/workspaces/{workspace_id}/properties/kpis", response_model=PropertyKPIsOut)
async def get_property_kpis(
    workspace_id: str,
    period_start: date | None = None,
    period_end: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PropertyKPIsOut:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    properties_result = await db.execute(select(Property).where(Property.workspace_id == workspace_id))
    properties = list(properties_result.scalars().all())

    tenancies_result = await db.execute(
        select(Tenancy).where(Tenancy.property_id.in_([p.id for p in properties]))
    )
    tenancies = list(tenancies_result.scalars().all())

    entries_result = await db.execute(
        select(RentLedgerEntry).where(RentLedgerEntry.tenancy_id.in_([t.id for t in tenancies]))
    )
    entries_by_tenancy: dict[str, list[RentLedgerEntry]] = {}
    for entry in entries_result.scalars().all():
        entries_by_tenancy.setdefault(entry.tenancy_id, []).append(entry)

    kpis = compute_portfolio_kpis(
        property_count=len(properties),
        tenancies=tenancies,
        entries_by_tenancy=entries_by_tenancy,
        period_start=period_start or date.min,
        period_end=period_end or date.max,
    )
    return PropertyKPIsOut(**kpis.__dict__)


@router.get("/properties/{property_id}", response_model=PropertyOut)
async def get_property(
    property_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Property:
    property_ = await _get_property_or_404(db, property_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)
    return property_


@router.patch("/properties/{property_id}", response_model=PropertyOut)
async def update_property(
    property_id: str,
    payload: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Property:
    property_ = await _get_property_or_404(db, property_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    for field, value in payload.model_dump().items():
        setattr(property_, field, value)
    await db.commit()
    await db.refresh(property_)
    return property_


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    property_ = await _get_property_or_404(db, property_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_delete_access(db, current_user.id, workspace)

    await db.delete(property_)
    await db.commit()


@router.post(
    "/properties/{property_id}/tenancies",
    response_model=TenancyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenancy(
    property_id: str,
    payload: TenancyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenancy:
    property_ = await _get_property_or_404(db, property_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    tenancy = Tenancy(
        property_id=property_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(tenancy)
    await db.commit()
    await db.refresh(tenancy)
    return tenancy


@router.get("/properties/{property_id}/tenancies", response_model=list[TenancyOut])
async def list_tenancies(
    property_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Tenancy]:
    property_ = await _get_property_or_404(db, property_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Tenancy).where(Tenancy.property_id == property_id).order_by(Tenancy.start_date.desc())
    )
    return list(result.scalars().all())


@router.patch("/tenancies/{tenancy_id}", response_model=TenancyOut)
async def update_tenancy(
    tenancy_id: str,
    payload: TenancyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenancy:
    tenancy, property_ = await _get_tenancy_or_404(db, tenancy_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    for field, value in payload.model_dump().items():
        setattr(tenancy, field, value)
    await db.commit()
    await db.refresh(tenancy)
    return tenancy


@router.post(
    "/tenancies/{tenancy_id}/ledger-entries",
    response_model=RentLedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ledger_entry(
    tenancy_id: str,
    payload: RentLedgerEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RentLedgerEntry:
    tenancy, property_ = await _get_tenancy_or_404(db, tenancy_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    entry = RentLedgerEntry(
        tenancy_id=tenancy_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/tenancies/{tenancy_id}/ledger-entries", response_model=list[RentLedgerEntryOut])
async def list_ledger_entries(
    tenancy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RentLedgerEntry]:
    tenancy, property_ = await _get_tenancy_or_404(db, tenancy_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(RentLedgerEntry)
        .where(RentLedgerEntry.tenancy_id == tenancy_id)
        .order_by(RentLedgerEntry.entry_date)
    )
    return list(result.scalars().all())


@router.get("/tenancies/{tenancy_id}/balance", response_model=TenancyBalanceOut)
async def get_tenancy_balance(
    tenancy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenancyBalanceOut:
    tenancy, property_ = await _get_tenancy_or_404(db, tenancy_id)
    workspace = await get_workspace_or_404(db, property_.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(select(RentLedgerEntry).where(RentLedgerEntry.tenancy_id == tenancy_id))
    entries = list(result.scalars().all())
    return TenancyBalanceOut(tenancy_id=tenancy_id, balance_gbp=compute_tenancy_balance(entries))
