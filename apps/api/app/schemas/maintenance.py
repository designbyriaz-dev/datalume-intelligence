from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.maintenance import MaintenancePriority, MaintenanceStatus


class MaintenanceRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    priority: MaintenancePriority = MaintenancePriority.MEDIUM
    reported_date: date
    tenancy_id: str | None = None


class MaintenanceRequestUpdate(BaseModel):
    # Mirrors TenancyUpdate's restricted-field pattern (see
    # app/schemas/property.py) — status/priority/resolved_date are the
    # fields that actually change over a request's life; title/
    # description/reported_date are fixed at creation.
    status: MaintenanceStatus
    priority: MaintenancePriority
    resolved_date: date | None = None


class MaintenanceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    tenancy_id: str | None
    title: str
    description: str | None
    priority: str
    status: str
    reported_date: date
    resolved_date: date | None
    created_by_user_id: str | None
