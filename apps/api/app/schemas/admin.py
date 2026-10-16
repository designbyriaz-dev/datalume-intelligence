from datetime import datetime

from pydantic import BaseModel


class PlatformStatsOut(BaseModel):
    generated_at: datetime
    total_users: int
    active_users: int
    signups_last_30_days: int
    total_organizations: int
    total_workspaces: int
    total_datasets: int
    total_dataset_versions: int
    total_analysis_runs: int
    total_reports_generated: int
    total_storage_bytes: int
    subscriptions_by_plan: dict[str, int]
    estimated_mrr_gbp: float
    failed_logins_last_24h: int


class AdminUserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    is_platform_admin: bool
    created_at: datetime
