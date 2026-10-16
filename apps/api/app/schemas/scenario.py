from pydantic import BaseModel, Field

from app.schemas.industry import KPIResultOut


class ScenarioAdjustmentIn(BaseModel):
    column: str
    adjustment_type: str = Field(pattern="^(percentage|fixed_amount|set_value)$")
    value: float


class ScenarioRequest(BaseModel):
    adjustments: list[ScenarioAdjustmentIn] = Field(min_length=1, max_length=10)


class KPIDeltaOut(BaseModel):
    kpi_id: str
    name: str
    format: str
    baseline_value: float | int | None
    scenario_value: float | int | None
    delta: float | None
    pct_change: float | None


class ScenarioResponse(BaseModel):
    industry_id: str
    adjustments_applied: list[ScenarioAdjustmentIn]
    baseline_kpis: list[KPIResultOut]
    scenario_kpis: list[KPIResultOut]
    kpi_deltas: list[KPIDeltaOut]
