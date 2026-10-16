from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.api.resolvers import get_table_chain_or_404, get_workspace_or_404
from app.api.v1.routers.industry import run_scenario_computation
from app.db.session import get_db
from app.models.saved_scenario import SavedScenario
from app.models.user import User
from app.schemas.saved_scenario import SavedScenarioCreateRequest, SavedScenarioOut
from app.schemas.scenario import ScenarioAdjustmentIn, ScenarioResponse
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.storage import ObjectStorage

router = APIRouter(tags=["saved-scenarios"])


@router.post(
    "/workspaces/{workspace_id}/saved-scenarios",
    response_model=SavedScenarioOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_saved_scenario(
    workspace_id: str,
    payload: SavedScenarioCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedScenario:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    _table, _version, _dataset, table_workspace = await get_table_chain_or_404(db, payload.dataset_table_id)
    if table_workspace.id != workspace_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "dataset_table_id does not belong to this workspace."
        )

    saved = SavedScenario(
        workspace_id=workspace_id,
        dataset_table_id=payload.dataset_table_id,
        name=payload.name,
        adjustments=[a.model_dump() for a in payload.adjustments],
        created_by_user_id=current_user.id,
    )
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return saved


@router.get("/workspaces/{workspace_id}/saved-scenarios", response_model=list[SavedScenarioOut])
async def list_saved_scenarios(
    workspace_id: str,
    dataset_table_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedScenario]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    query = select(SavedScenario).where(SavedScenario.workspace_id == workspace_id)
    if dataset_table_id is not None:
        query = query.where(SavedScenario.dataset_table_id == dataset_table_id)
    result = await db.execute(query.order_by(SavedScenario.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/saved-scenarios/{saved_scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_scenario(
    saved_scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    saved = await db.get(SavedScenario, saved_scenario_id)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved scenario not found")

    workspace = await get_workspace_or_404(db, saved.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(saved)
    await db.commit()


@router.post("/saved-scenarios/{saved_scenario_id}/run", response_model=ScenarioResponse)
async def run_saved_scenario(
    saved_scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> ScenarioResponse:
    saved = await db.get(SavedScenario, saved_scenario_id)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved scenario not found")

    table, _version, _dataset, workspace = await get_table_chain_or_404(db, saved.dataset_table_id)
    await require_workspace_access(db, current_user.id, workspace)

    adjustments_in = [ScenarioAdjustmentIn(**a) for a in saved.adjustments]
    return await run_scenario_computation(
        db,
        storage,
        table=table,
        workspace=workspace,
        current_user=current_user,
        adjustments_in=adjustments_in,
    )
