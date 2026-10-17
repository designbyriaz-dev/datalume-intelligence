"""Scheduled report generation. run_due_scheduled_reports is the one
function that actually does the work — it's called from two places:

1. A real APScheduler background job (app/main.py), on a fixed interval,
   using a fresh DB session each tick. This is genuine recurring
   execution, not a stub. Running more than one API replica no longer
   causes every due report to fire once per replica: each tick first
   acquires a lease lock (app/services/distributed_lock.py) scoped to
   SCHEDULER_LOCK_ID, so only one replica's tick actually processes due
   reports at a time — the others see the lock held and skip that tick
   entirely, trying again next interval.
2. Tests, directly — set a ScheduledReport's next_run_at into the past
   and call the function; no waiting on wall-clock time required.
"""

from __future__ import annotations

import calendar
import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.industry_packs import get_industry_pack
from app.models.dataset import Dataset, DatasetTable, DatasetVersion
from app.models.report import Report
from app.models.scheduled_report import ScheduledReport
from app.models.user import User
from app.models.workspace import Workspace
from app.services.datasets import get_dataset_table_dataframe
from app.services.distributed_lock import release_lock, try_acquire_lock
from app.services.email import EmailAttachment, EmailMessage, EmailSender
from app.services.industry_kpis import DEFAULT_KPI_WINDOW_MONTHS, compute_kpis
from app.services.industry_matching import get_effective_field_mapping
from app.services.reports import (
    generate_business_finance_report_pdf,
    generate_commercial_property_report_pdf,
    generate_data_quality_report_pdf,
    generate_public_sector_budget_variance_report_pdf,
    generate_residential_property_report_pdf,
    generate_residential_repairs_maintenance_report_pdf,
    generate_social_housing_compliance_exceptions_report_pdf,
    generate_social_housing_report_pdf,
)
from app.services.storage import ObjectStorage

# Maps a report_type that requires a specific industry pack to that pack's
# industry_id. Shared between _generate_report_bytes (enforced at run time,
# in case a workspace's industry changed after the schedule was created)
# and the router's create-time validation, so the two can't drift apart.
REPORT_TYPE_REQUIRED_INDUSTRY = {
    "commercial_property_portfolio": "commercial_property",
    "residential_property_portfolio": "residential_property",
    "residential_repairs_maintenance": "residential_property",
    "social_housing_asset": "social_housing",
    "social_housing_compliance_exceptions": "social_housing",
    "business_performance": "business_finance",
    "public_sector_budget_variance": "public_sector",
}

VALID_REPORT_TYPES = {"data_quality", *REPORT_TYPE_REQUIRED_INDUSTRY.keys()}
VALID_FREQUENCIES = {"daily", "weekly", "monthly"}

# The lease lock id guarding run_due_scheduled_reports against concurrent
# processing by more than one API replica's scheduler tick at once.
SCHEDULER_LOCK_ID = "scheduled_reports"


class ScheduledReportError(Exception):
    pass


def compute_next_run(frequency: str, from_dt: dt.datetime) -> dt.datetime:
    if frequency == "daily":
        return from_dt + dt.timedelta(days=1)
    if frequency == "weekly":
        return from_dt + dt.timedelta(days=7)
    if frequency == "monthly":
        year = from_dt.year + (from_dt.month // 12)
        month = from_dt.month % 12 + 1
        day = min(from_dt.day, calendar.monthrange(year, month)[1])
        return from_dt.replace(year=year, month=month, day=day)
    raise ScheduledReportError(f"Unknown frequency: {frequency}. Valid: {', '.join(sorted(VALID_FREQUENCIES))}")


async def _generate_report_bytes(
    storage: ObjectStorage, scheduled: ScheduledReport, table: DatasetTable, dataset: Dataset, workspace: Workspace
) -> bytes:
    if scheduled.report_type == "data_quality":
        return generate_data_quality_report_pdf(
            dataset_name=dataset.name, table=table, generated_by_name="Scheduled report"
        )

    required_industry = REPORT_TYPE_REQUIRED_INDUSTRY.get(scheduled.report_type)
    if required_industry is not None:
        pack = get_industry_pack(workspace.industry)
        if pack is None or pack.industry_id != required_industry:
            raise ScheduledReportError(
                f"Workspace industry is '{workspace.industry}', not {required_industry} — "
                "this scheduled report can no longer run."
            )
        df = await get_dataset_table_dataframe(storage, table)
        mapping = get_effective_field_mapping(table, pack, df.columns)
        window_months = workspace.kpi_window_months or DEFAULT_KPI_WINDOW_MONTHS
        kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today(), window_months=window_months)

        if scheduled.report_type == "commercial_property_portfolio":
            return generate_commercial_property_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
                window_months=window_months,
            )
        if scheduled.report_type == "residential_property_portfolio":
            return generate_residential_property_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
                window_months=window_months,
            )
        if scheduled.report_type == "social_housing_asset":
            return generate_social_housing_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
                compliance_caveat=pack.compliance_caveat,
                window_months=window_months,
            )
        if scheduled.report_type == "residential_repairs_maintenance":
            return generate_residential_repairs_maintenance_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
            )
        if scheduled.report_type == "social_housing_compliance_exceptions":
            return generate_social_housing_compliance_exceptions_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                compliance_caveat=pack.compliance_caveat,
                window_months=window_months,
            )
        if scheduled.report_type == "business_performance":
            return generate_business_finance_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
            )
        if scheduled.report_type == "public_sector_budget_variance":
            return generate_public_sector_budget_variance_report_pdf(
                dataset_name=dataset.name,
                table_sheet_name=table.sheet_name,
                generated_by_name="Scheduled report",
                df=df,
                mapping=mapping,
                kpi_results=kpi_results,
                compliance_caveat=pack.compliance_caveat,
            )

    raise ScheduledReportError(f"Unknown report_type: {scheduled.report_type}")


async def run_due_scheduled_reports(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    now: dt.datetime | None = None,
    email_sender: EmailSender | None = None,
) -> list[Report]:
    now = now or dt.datetime.now(dt.timezone.utc)

    holder = await try_acquire_lock(db, SCHEDULER_LOCK_ID, now=now)
    if holder is None:
        # Another replica's tick already holds this lock — someone is
        # (or very recently was) processing due reports right now.
        # Skip this tick entirely rather than risk two replicas
        # generating and emailing the same report twice.
        return []

    try:
        return await _run_due_scheduled_reports_locked(db, storage, now=now, email_sender=email_sender)
    finally:
        await release_lock(db, SCHEDULER_LOCK_ID, holder)


async def _run_due_scheduled_reports_locked(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    now: dt.datetime,
    email_sender: EmailSender | None,
) -> list[Report]:
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.is_active.is_(True), ScheduledReport.next_run_at <= now)
    )
    due = list(result.scalars().all())

    generated: list[Report] = []
    for scheduled in due:
        table = await db.get(DatasetTable, scheduled.dataset_table_id)
        if table is None:
            scheduled.is_active = False
            scheduled.last_error = "Dataset table no longer exists."
            continue

        version = await db.get(DatasetVersion, table.dataset_version_id)
        dataset = await db.get(Dataset, version.dataset_id) if version else None
        workspace = await db.get(Workspace, scheduled.workspace_id)

        if dataset is None or workspace is None:
            scheduled.is_active = False
            scheduled.last_error = "Dataset or workspace no longer exists."
            continue

        try:
            pdf_bytes = await _generate_report_bytes(storage, scheduled, table, dataset, workspace)
        except ScheduledReportError as exc:
            scheduled.last_error = str(exc)
            scheduled.next_run_at = compute_next_run(scheduled.frequency, now)
            continue

        report_id = str(uuid.uuid4())
        storage_key = f"workspaces/{workspace.id}/reports/{report_id}.pdf"
        storage.write(storage_key, pdf_bytes)
        report = Report(
            id=report_id,
            dataset_table_id=table.id,
            report_type=scheduled.report_type,
            storage_key=storage_key,
            file_size_bytes=len(pdf_bytes),
            generated_by_user_id=scheduled.created_by_user_id,
        )
        db.add(report)
        generated.append(report)

        scheduled.last_run_at = now
        scheduled.last_error = None
        scheduled.next_run_at = compute_next_run(scheduled.frequency, now)

        if email_sender is not None:
            # Delivery is best-effort and independent of generation: a
            # failed send must not undo the report that was already
            # produced and stored, and must not touch last_error (that
            # field means "generation failed" — mixing delivery failures
            # into it would make the schedule look broken when it isn't).
            # Mirrors WebhookSubscription.last_delivery_error's
            # record-don't-crash approach.
            recipient = await db.get(User, scheduled.created_by_user_id)
            if recipient is not None:
                report_label = scheduled.report_type.replace("_", " ").title()
                try:
                    email_sender.send(
                        EmailMessage(
                            to=recipient.email,
                            subject=f"DataLume: your scheduled {report_label} report is ready",
                            text_body=(
                                f"Hi {recipient.full_name},\n\n"
                                f"Your scheduled {report_label} report for {dataset.name} "
                                f"({table.sheet_name}) is attached.\n\n"
                                "— DataLume Intelligence"
                            ),
                            attachments=[
                                EmailAttachment(
                                    filename=f"{scheduled.report_type}.pdf",
                                    content=pdf_bytes,
                                    content_type="application/pdf",
                                )
                            ],
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - record, don't crash the scheduler tick
                    scheduled.last_email_error = str(exc)
                else:
                    scheduled.last_email_sent_at = now
                    scheduled.last_email_error = None

    await db.commit()
    return generated
