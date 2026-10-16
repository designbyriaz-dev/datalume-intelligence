import datetime as dt
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_http_client, get_object_storage
from app.api.resolvers import get_table_chain_or_404
from app.core.industry_packs import get_industry_pack
from app.db.session import get_db
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportOut
from app.services.authz import require_workspace_access
from app.services.datasets import get_dataset_table_dataframe
from app.services.industry_kpis import compute_kpis
from app.services.industry_matching import get_effective_field_mapping
from app.services.reports import (
    generate_business_finance_report_pdf,
    generate_commercial_property_report_pdf,
    generate_data_quality_report_pdf,
    generate_residential_property_report_pdf,
    generate_residential_repairs_maintenance_report_pdf,
    generate_social_housing_compliance_exceptions_report_pdf,
    generate_social_housing_report_pdf,
)
from app.services.storage import ObjectStorage, StorageError
from app.services.webhooks import dispatch_event

router = APIRouter(tags=["reports"])


@router.post(
    "/dataset-tables/{table_id}/reports/data-quality",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_data_quality_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pdf_bytes = generate_data_quality_report_pdf(
        dataset_name=dataset.name, table=table, generated_by_name=current_user.full_name
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="data_quality",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/commercial-property-portfolio",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_commercial_property_portfolio_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "commercial_property":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for commercial_property workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    pdf_bytes = generate_commercial_property_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        kpi_results=kpi_results,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="commercial_property_portfolio",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/residential-property-portfolio",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_residential_property_portfolio_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "residential_property":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for residential_property workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    pdf_bytes = generate_residential_property_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        kpi_results=kpi_results,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="residential_property_portfolio",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/social-housing-asset",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_social_housing_asset_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "social_housing":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for social_housing workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    pdf_bytes = generate_social_housing_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        kpi_results=kpi_results,
        compliance_caveat=pack.compliance_caveat,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="social_housing_asset",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/business-performance",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_business_performance_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "business_finance":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for business_finance workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    pdf_bytes = generate_business_finance_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        kpi_results=kpi_results,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="business_performance",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/social-housing-compliance-exceptions",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_social_housing_compliance_exceptions_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "social_housing":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for social_housing workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)

    pdf_bytes = generate_social_housing_compliance_exceptions_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        compliance_caveat=pack.compliance_caveat,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="social_housing_compliance_exceptions",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.post(
    "/dataset-tables/{table_id}/reports/residential-repairs-maintenance",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_residential_repairs_maintenance_report(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Report:
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None or pack.industry_id != "residential_property":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This report template is only available for residential_property workspaces.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    pdf_bytes = generate_residential_repairs_maintenance_report_pdf(
        dataset_name=dataset.name,
        table_sheet_name=table.sheet_name,
        generated_by_name=current_user.full_name,
        df=df,
        mapping=mapping,
        kpi_results=kpi_results,
    )

    report_id = str(uuid.uuid4())
    storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
    storage.write(storage_key, pdf_bytes)

    report = Report(
        id=report_id,
        dataset_table_id=table.id,
        report_type="residential_repairs_maintenance",
        storage_key=storage_key,
        file_size_bytes=len(pdf_bytes),
        generated_by_user_id=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await dispatch_event(
        db,
        http_client,
        event_type="report.generated",
        workspace_id=workspace.id,
        payload={"report_id": report.id, "report_type": report.report_type, "dataset_table_id": table.id},
    )

    return report


@router.get("/dataset-tables/{table_id}/reports", response_model=list[ReportOut])
async def list_reports(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Report]:
    _table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(Report).where(Report.dataset_table_id == table_id).order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    _table, _version, _dataset, workspace = await get_table_chain_or_404(db, report.dataset_table_id)
    await require_workspace_access(db, current_user.id, workspace)

    try:
        content = storage.read(report.storage_key)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report file not found in storage") from exc

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report.report_type}-{report.id}.pdf"'},
    )
