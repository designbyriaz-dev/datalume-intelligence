from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scenario import ScenarioAdjustmentIn


class SavedScenarioCreateRequest(BaseModel):
    dataset_table_id: str
    name: str = Field(min_length=1, max_length=255)
    adjustments: list[ScenarioAdjustmentIn] = Field(min_length=1, max_length=10)


class SavedScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    dataset_table_id: str
    name: str
    adjustments: list[ScenarioAdjustmentIn]
    created_by_user_id: str
    created_at: datetime
