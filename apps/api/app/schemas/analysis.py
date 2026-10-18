from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    operation: str = Field(description="One of the registered tool names — see GET /api/v1/tools")
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_table_id: str
    operation_type: str
    parameters: dict[str, Any]
    result: dict[str, Any]
    created_by_user_id: str | None


class ToolParameterOut(BaseModel):
    name: str
    type: str
    description: str
    required: bool
    enum: list[str] | None = None
    default: Any = None


class ToolSpecOut(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameterOut]
