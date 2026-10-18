from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    # Note: which table to ground this in comes from the URL
    # (/dataset-tables/{table_id}/ask), not from this body.
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, description="Continue an existing conversation")


class ToolCallOut(BaseModel):
    name: str
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None


class AskResponse(BaseModel):
    conversation_id: str
    answer: str
    tool_calls: list[ToolCallOut]
    hit_iteration_limit: bool


class AIMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None
    created_at: datetime


class AIConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_id: str
    title: str | None
    created_by_user_id: str | None
    created_at: datetime
    messages: list[AIMessageOut]
