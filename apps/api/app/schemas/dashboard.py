from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WidgetCreateRequest(BaseModel):
    widget_type: str = Field(pattern="^(kpi|chart)$")
    title: str = Field(min_length=1, max_length=255)
    config: dict[str, Any]


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    widget_type: str
    title: str
    config: dict[str, Any]
    position: int
    value: dict[str, Any] | None = None


class WidgetReorderRequest(BaseModel):
    # The new order, expressed as the full list of this dashboard's widget
    # ids in their new positions (index 0 = position 0, etc.) — not a
    # single {widget_id, new_position} pair, so the server can validate
    # the whole set in one request rather than trusting N separate calls
    # to leave a dashboard in a consistent state.
    widget_ids: list[str] = Field(min_length=1)


class DashboardCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dataset_table_id: str


class AutoGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dataset_table_id: str


class DashboardSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_table_id: str
    name: str
    widget_count: int


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_table_id: str
    name: str
    widgets: list[WidgetOut]


class CommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dashboard_id: str
    author_user_id: str | None
    content: str
    created_at: datetime
