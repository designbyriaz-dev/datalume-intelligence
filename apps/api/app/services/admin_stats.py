"""Platform admin statistics — every number here is a real aggregate
query against the actual database, computed at request time. Nothing is
estimated or fabricated.

Deliberately NOT included, because there's no real data source for them
yet (see docs/CHECKLIST.md rather than inventing numbers):
- AI processing costs — no LLM calls have ever been made (LLM_API_KEY is
  unconfigured in this environment); cost tracking would need real usage
  first.
- System error rates — no error-tracking/log-aggregation service is
  integrated.
- Customer support ticket counts — no support system exists.
- Background job health — the APScheduler job's own run history isn't
  persisted anywhere queryable yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plans import get_plan
from app.models.analysis import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.billing import BillingPeriod, Subscription, SubscriptionStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.models.workspace import Workspace


async def _scalar(db: AsyncSession, stmt) -> int:
    result = await db.execute(stmt)
    value = result.scalar_one()
    return value or 0


async def compute_platform_stats(db: AsyncSession) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    total_users = await _scalar(db, select(func.count(User.id)))
    active_users = await _scalar(db, select(func.count(User.id)).where(User.is_active.is_(True)))
    signups_last_30_days = await _scalar(
        db, select(func.count(User.id)).where(User.created_at >= now - timedelta(days=30))
    )

    total_organizations = await _scalar(db, select(func.count(Organization.id)))
    total_workspaces = await _scalar(db, select(func.count(Workspace.id)))
    total_datasets = await _scalar(db, select(func.count(Dataset.id)))
    total_dataset_versions = await _scalar(db, select(func.count(DatasetVersion.id)))
    total_analysis_runs = await _scalar(db, select(func.count(AnalysisRun.id)))
    total_reports_generated = await _scalar(db, select(func.count(Report.id)))

    dataset_storage_bytes = await _scalar(
        db, select(func.coalesce(func.sum(DatasetVersion.file_size_bytes), 0))
    )
    report_storage_bytes = await _scalar(db, select(func.coalesce(func.sum(Report.file_size_bytes), 0)))

    plan_counts_result = await db.execute(
        select(Subscription.plan_id, func.count(Subscription.id)).group_by(Subscription.plan_id)
    )
    subscriptions_by_plan = {plan_id: count for plan_id, count in plan_counts_result.all()}

    # MRR estimate: sum of each active, monthly-billed subscription's
    # plan price. Annual subscriptions are excluded from this figure
    # (the brief's plan list gives no separate annual price point to
    # convert from) — flagged explicitly rather than silently
    # under-counting without explanation.
    active_monthly_result = await db.execute(
        select(Subscription.plan_id, func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.billing_period == BillingPeriod.MONTHLY,
            Subscription.plan_id != "free",
        ).group_by(Subscription.plan_id)
    )
    estimated_mrr_gbp = 0.0
    for plan_id, count in active_monthly_result.all():
        plan = get_plan(plan_id)
        if plan.monthly_price_gbp:
            estimated_mrr_gbp += plan.monthly_price_gbp * count

    failed_logins_last_24h = await _scalar(
        db,
        select(func.count(AuditLog.id)).where(
            AuditLog.event_type == "auth.login_failed", AuditLog.created_at >= now - timedelta(hours=24)
        ),
    )

    return {
        "generated_at": now,
        "total_users": total_users,
        "active_users": active_users,
        "signups_last_30_days": signups_last_30_days,
        "total_organizations": total_organizations,
        "total_workspaces": total_workspaces,
        "total_datasets": total_datasets,
        "total_dataset_versions": total_dataset_versions,
        "total_analysis_runs": total_analysis_runs,
        "total_reports_generated": total_reports_generated,
        "total_storage_bytes": dataset_storage_bytes + report_storage_bytes,
        "subscriptions_by_plan": subscriptions_by_plan,
        "estimated_mrr_gbp": round(estimated_mrr_gbp, 2),
        "failed_logins_last_24h": failed_logins_last_24h,
    }
