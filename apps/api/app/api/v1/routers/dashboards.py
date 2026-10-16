from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_object_storage
from app.api.resolvers import get_dashboard_chain_or_404, get_workspace_or_404
from app.db.session import get_db
from app.models.dashboard import Dashboard, DashboardComment, DashboardWidget
from app.models.dataset import DatasetTable
from app.models.user import User
from app.schemas.dashboard import (
    AutoGenerateRequest,
    CommentCreateRequest,
    CommentOut,
    DashboardCreateRequest,
    DashboardOut,
    DashboardSummaryOut,
    WidgetCreateRequest,
    WidgetOut,
    WidgetReorderRequest,
)
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.dashboards import WidgetComputeError, build_default_widgets, compute_widget_value
from app.services.datasets import get_dataset_table_dataframe
from app.services.storage import ObjectStorage

router = APIRouter(tags=["dashboards"])


async def _widget_out_with_value(widget: DashboardWidget, df, table, workspace) -> WidgetOut:
    try:
        value = compute_widget_value(df, table, workspace, widget.widget_type, widget.config)
    except WidgetComputeError as exc:
        value = {"error": str(exc)}
    return WidgetOut(
        id=widget.id, widget_type=widget.widget_type, title=widget.title, config=widget.config,
        position=widget.position, value=value,
    )


@router.post("/workspaces/{workspace_id}/dashboards", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    workspace_id: str,
    payload: DashboardCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardOut:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    table = await db.get(DatasetTable, payload.dataset_table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset table not found")

    dashboard = Dashboard(
        workspace_id=workspace_id,
        dataset_table_id=payload.dataset_table_id,
        name=payload.name,
        created_by_user_id=current_user.id,
    )
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    return DashboardOut(
        id=dashboard.id, workspace_id=dashboard.workspace_id, dataset_table_id=dashboard.dataset_table_id,
        name=dashboard.name, widgets=[],
    )


@router.post(
    "/workspaces/{workspace_id}/dashboards/auto-generate",
    response_model=DashboardOut,
    status_code=status.HTTP_201_CREATED,
)
async def auto_generate_dashboard(
    workspace_id: str,
    payload: AutoGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DashboardOut:
    """"Generate Dashboard Automatically" — inspects the table's profile
    (or the workspace's industry pack, if it has one) and proposes a
    default set of widgets."""
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    table = await db.get(DatasetTable, payload.dataset_table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset table not found")

    dashboard = Dashboard(
        workspace_id=workspace_id,
        dataset_table_id=payload.dataset_table_id,
        name=payload.name,
        created_by_user_id=current_user.id,
    )
    db.add(dashboard)
    await db.flush()

    widget_configs = build_default_widgets(table, workspace)
    for i, wc in enumerate(widget_configs):
        db.add(
            DashboardWidget(
                dashboard_id=dashboard.id,
                widget_type=wc["widget_type"],
                title=wc["title"],
                config=wc["config"],
                position=i,
            )
        )
    await db.commit()

    return await get_dashboard(dashboard.id, current_user, db, storage)


@router.get("/workspaces/{workspace_id}/dashboards", response_model=list[DashboardSummaryOut])
async def list_dashboards(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Dashboard, func.count(DashboardWidget.id))
        .outerjoin(DashboardWidget, DashboardWidget.dashboard_id == Dashboard.id)
        .where(Dashboard.workspace_id == workspace_id)
        .group_by(Dashboard.id)
    )
    return [
        {
            "id": d.id,
            "workspace_id": d.workspace_id,
            "dataset_table_id": d.dataset_table_id,
            "name": d.name,
            "widget_count": count,
        }
        for d, count in result.all()
    ]


@router.get("/dashboards/{dashboard_id}", response_model=DashboardOut)
async def get_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DashboardOut:
    dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id)
        .options(selectinload(Dashboard.widgets))
    )
    dashboard = result.scalar_one()

    table = await db.get(DatasetTable, dashboard.dataset_table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard's dataset table no longer exists")
    df = await get_dataset_table_dataframe(storage, table)

    widgets_out = [await _widget_out_with_value(w, df, table, workspace) for w in dashboard.widgets]
    return DashboardOut(
        id=dashboard.id, workspace_id=dashboard.workspace_id, dataset_table_id=dashboard.dataset_table_id,
        name=dashboard.name, widgets=widgets_out,
    )


@router.post("/dashboards/{dashboard_id}/widgets", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def add_widget(
    dashboard_id: str,
    payload: WidgetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DashboardOut:
    dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    count_result = await db.execute(
        select(func.count(DashboardWidget.id)).where(DashboardWidget.dashboard_id == dashboard_id)
    )
    next_position = count_result.scalar_one()

    db.add(
        DashboardWidget(
            dashboard_id=dashboard_id,
            widget_type=payload.widget_type,
            title=payload.title,
            config=payload.config,
            position=next_position,
        )
    )
    await db.commit()

    return await get_dashboard(dashboard_id, current_user, db, storage)


@router.delete("/dashboards/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_widget(
    dashboard_id: str,
    widget_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    widget = await db.get(DashboardWidget, widget_id)
    if widget is None or widget.dashboard_id != dashboard_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found on this dashboard")

    await db.delete(widget)
    await db.commit()


@router.patch("/dashboards/{dashboard_id}/widgets/reorder", response_model=DashboardOut)
async def reorder_widgets(
    dashboard_id: str,
    payload: WidgetReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DashboardOut:
    """Persists a drag-and-drop reorder. Takes the dashboard's full new
    widget order (not a single moved-widget delta) and validates it's
    exactly the dashboard's current widget set — same ids, no more, no
    fewer, no duplicates — before writing anything, so a stale or
    tampered client request can't silently leave some widgets with
    out-of-sync positions or move a widget it doesn't actually own onto
    this dashboard."""
    dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    result = await db.execute(
        select(DashboardWidget.id).where(DashboardWidget.dashboard_id == dashboard_id)
    )
    existing_ids = {row[0] for row in result.all()}
    submitted_ids = payload.widget_ids

    if len(submitted_ids) != len(set(submitted_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "widget_ids contains duplicates")
    if set(submitted_ids) != existing_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "widget_ids must contain exactly this dashboard's current widgets, no more and no fewer",
        )

    for position, widget_id in enumerate(submitted_ids):
        widget = await db.get(DashboardWidget, widget_id)
        widget.position = position

    await db.commit()

    return await get_dashboard(dashboard_id, current_user, db, storage)


@router.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(dashboard)
    await db.commit()


@router.post(
    "/dashboards/{dashboard_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
async def add_comment(
    dashboard_id: str,
    payload: CommentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardComment:
    """Any workspace member — including read-only Viewer/Auditor roles —
    can comment. Discussing a shared dashboard is a read-level
    collaborative activity, not a mutation of the underlying data."""
    _dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_access(db, current_user.id, workspace)

    comment = DashboardComment(dashboard_id=dashboard_id, author_user_id=current_user.id, content=payload.content)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/dashboards/{dashboard_id}/comments", response_model=list[CommentOut])
async def list_comments(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DashboardComment]:
    _dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(DashboardComment)
        .where(DashboardComment.dashboard_id == dashboard_id)
        .order_by(DashboardComment.created_at)
    )
    return list(result.scalars().all())


@router.delete("/dashboards/{dashboard_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    dashboard_id: str,
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _dashboard, workspace = await get_dashboard_chain_or_404(db, dashboard_id)
    await require_workspace_access(db, current_user.id, workspace)

    comment = await db.get(DashboardComment, comment_id)
    if comment is None or comment.dashboard_id != dashboard_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found on this dashboard")
    if comment.author_user_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own comments")

    await db.delete(comment)
    await db.commit()
