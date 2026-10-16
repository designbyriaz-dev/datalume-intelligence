from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.api.resolvers import get_table_chain_or_404
from app.db.session import get_db
from app.models.analysis import AnalysisRun
from app.models.user import User
from app.schemas.analysis import AnalysisRunOut, AnalyzeRequest, ToolSpecOut
from app.services import billing
from app.services.analytics import AnalyticsError
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.datasets import get_dataset_table_dataframe
from app.services.storage import ObjectStorage
from app.services.tools import TOOLS

router = APIRouter(tags=["analysis"])


@router.get("/tools", response_model=list[ToolSpecOut])
async def list_tools(current_user: User = Depends(get_current_user)) -> list[dict]:
    """The full registry of deterministic analytical operations available
    — the same ones the AI query planner is restricted to calling once
    it's configured with a real LLM key."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "enum": p.enum,
                    "default": p.default,
                }
                for p in spec.parameters
            ],
        }
        for spec in TOOLS.values()
    ]


@router.post("/dataset-tables/{table_id}/analyze", response_model=AnalysisRunOut, status_code=status.HTTP_201_CREATED)
async def analyze_table(
    table_id: str,
    payload: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> AnalysisRun:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    # Read-only analysis is available to Viewers/Auditors too — running a
    # calculation doesn't mutate the dataset, unlike upload/deduplicate.
    await require_workspace_access(db, current_user.id, workspace)

    tool = TOOLS.get(payload.operation)
    if tool is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown operation '{payload.operation}'. See GET /api/v1/tools for the list.",
        )

    df = await get_dataset_table_dataframe(storage, table)

    try:
        result = tool.execute(df, payload.parameters)
    except AnalyticsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Quota is only consumed once the analysis actually succeeds — a
    # doomed-to-fail request (bad column, wrong type) never costs the
    # user a unit of their monthly allowance.
    subscription = await billing.get_subscription_for_workspace(db, workspace)
    try:
        await billing.check_and_increment_analysis_quota(db, subscription)
    except billing.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc

    run = AnalysisRun(
        dataset_table_id=table.id,
        operation_type=payload.operation,
        parameters=payload.parameters,
        result=result,
        created_by_user_id=current_user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/dataset-tables/{table_id}/analyses", response_model=list[AnalysisRunOut])
async def list_analyses(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisRun]:
    _table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.dataset_table_id == table_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(result.scalars().all())
