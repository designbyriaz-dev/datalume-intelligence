import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.resolvers import get_workspace_or_404
from app.db.session import get_db
from app.models.dataset import DatasetTable
from app.models.scheduled_report import ScheduledReport
from app.models.user import User
from app.schemas.scheduled_report import ScheduledReportCreateRequest, ScheduledReportOut
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.core.industry_packs import get_industry_pack
from app.services.scheduled_reports import (
    REPORT_TYPE_REQUIRED_INDUSTRY,
    VALID_FREQUENCIES,
    VALID_REPORT_TYPES,
    compute_next_run,
)

router = APIRouter(tags=["scheduled-reports"])


@router.post(
    "/workspaces/{workspace_id}/scheduled-reports",
    response_model=ScheduledReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_report(
    workspace_id: str,
    payload: ScheduledReportCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledReport:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    if payload.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown report_type '{payload.report_type}'. Valid: {', '.join(sorted(VALID_REPORT_TYPES))}",
        )
    if payload.frequency not in VALID_FREQUENCIES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown frequency '{payload.frequency}'. Valid: {', '.join(sorted(VALID_FREQUENCIES))}",
        )
    required_industry = REPORT_TYPE_REQUIRED_INDUSTRY.get(payload.report_type)
    if required_industry is not None:
        pack = get_industry_pack(workspace.industry)
        if pack is None or pack.industry_id != required_industry:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{payload.report_type} reports can only be scheduled in a {required_industry} workspace.",
            )

    table = await db.get(DatasetTable, payload.dataset_table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset table not found")

    now = dt.datetime.now(dt.timezone.utc)
    scheduled = ScheduledReport(
        workspace_id=workspace_id,
        dataset_table_id=payload.dataset_table_id,
        report_type=payload.report_type,
        frequency=payload.frequency,
        next_run_at=compute_next_run(payload.frequency, now),
        created_by_user_id=current_user.id,
    )
    db.add(scheduled)
    await db.commit()
    await db.refresh(scheduled)
    return scheduled


@router.get("/workspaces/{workspace_id}/scheduled-reports", response_model=list[ScheduledReportOut])
async def list_scheduled_reports(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledReport]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(select(ScheduledReport).where(ScheduledReport.workspace_id == workspace_id))
    return list(result.scalars().all())


@router.delete("/scheduled-reports/{scheduled_report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_report(
    scheduled_report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    scheduled = await db.get(ScheduledReport, scheduled_report_id)
    if scheduled is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheduled report not found")

    workspace = await get_workspace_or_404(db, scheduled.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(scheduled)
    await db.commit()
