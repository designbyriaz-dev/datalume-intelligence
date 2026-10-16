from pydantic import BaseModel, ConfigDict, Field

from app.models.workspace import IndustryType


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    industry: IndustryType = IndustryType.GENERAL
    organization_id: str | None = None


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    industry: str
    owner_user_id: str | None
    organization_id: str | None
    kpi_window_months: int | None


class WorkspaceSettingsUpdate(BaseModel):
    # None resets to the default (12 months, see
    # app.services.industry_kpis.DEFAULT_KPI_WINDOW_MONTHS). Always
    # required in the payload, not just-omittable, so a PATCH call always
    # states its intent explicitly rather than relying on "field absent"
    # to mean "leave unchanged" for a single-field resource.
    kpi_window_months: int | None = Field(default=None, ge=1, le=60)
