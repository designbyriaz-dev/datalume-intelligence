from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScheduledReportCreateRequest(BaseModel):
    dataset_table_id: str
    report_type: str
    frequency: str


class ScheduledReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_table_id: str
    report_type: str
    frequency: str
    next_run_at: datetime
    last_run_at: datetime | None
    last_error: str | None
    last_email_sent_at: datetime | None
    last_email_error: str | None
    is_active: bool
