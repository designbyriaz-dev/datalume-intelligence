"""Shared "load this row or 404" helpers used by multiple routers
(datasets, analysis) so the lookup chain — table -> version -> dataset ->
workspace — isn't duplicated."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard
from app.models.dataset import Dataset, DatasetTable, DatasetVersion
from app.models.property import Property, Tenancy
from app.models.workspace import Workspace


async def get_workspace_or_404(db: AsyncSession, workspace_id: str) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


async def get_dataset_or_404(db: AsyncSession, dataset_id: str) -> Dataset:
    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    return dataset


async def get_table_chain_or_404(
    db: AsyncSession, table_id: str
) -> tuple[DatasetTable, DatasetVersion, Dataset, Workspace]:
    table = await db.get(DatasetTable, table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset table not found")
    version = await db.get(DatasetVersion, table.dataset_version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset version not found")
    dataset = await db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    workspace = await db.get(Workspace, dataset.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return table, version, dataset, workspace


async def get_dashboard_chain_or_404(db: AsyncSession, dashboard_id: str) -> tuple[Dashboard, Workspace]:
    dashboard = await db.get(Dashboard, dashboard_id)
    if dashboard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found")
    workspace = await db.get(Workspace, dashboard.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return dashboard, workspace


async def get_property_chain_or_404(db: AsyncSession, property_id: str) -> tuple[Property, Workspace]:
    property_ = await db.get(Property, property_id)
    if property_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    workspace = await db.get(Workspace, property_.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return property_, workspace


async def get_tenancy_chain_or_404(db: AsyncSession, tenancy_id: str) -> tuple[Tenancy, Property, Workspace]:
    tenancy = await db.get(Tenancy, tenancy_id)
    if tenancy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenancy not found")
    property_, workspace = await get_property_chain_or_404(db, tenancy.property_id)
    return tenancy, property_, workspace
