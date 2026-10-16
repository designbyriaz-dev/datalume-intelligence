from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyCreatedOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    raw_key: str = Field(description="Shown only once — store it now, it cannot be retrieved again.")
    created_at: datetime


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    key_prefix: str
    last_used_at: datetime | None
    is_active: bool
    created_at: datetime
