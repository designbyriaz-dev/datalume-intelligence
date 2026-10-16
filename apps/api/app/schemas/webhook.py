from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    event_types: list[str] = Field(min_length=1)


class WebhookCreatedOut(BaseModel):
    id: str
    url: str
    event_types: list[str]
    secret: str = Field(description="Shown only once — store it now to verify incoming deliveries.")
    created_at: datetime


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    event_types: list[str]
    is_active: bool
    last_delivery_at: datetime | None
    last_delivery_status: int | None
    last_delivery_error: str | None
    created_at: datetime
