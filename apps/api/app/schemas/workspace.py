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
