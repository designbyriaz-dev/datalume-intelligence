from pydantic import BaseModel, ConfigDict, Field


class ColumnAliasOut(BaseModel):
    canonical_field: str
    description: str
    required_for_pack: bool


class KPIDefinitionOut(BaseModel):
    kpi_id: str
    name: str
    description: str
    format: str


class IndustryPackOut(BaseModel):
    industry_id: str
    name: str
    column_aliases: list[ColumnAliasOut]
    kpis: list[KPIDefinitionOut]
    suggested_questions: list[str]
    terminology: dict[str, str]
    report_templates: list[str]
    compliance_caveat: str | None


class KPIResultOut(BaseModel):
    kpi_id: str
    name: str
    format: str
    value: float | int | None
    formatted: str
    error: str | None


class IndustryKPIResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_run_id: str
    industry_id: str
    pack_name: str
    field_mapping: dict[str, str | None]
    missing_required_fields: list[str]
    kpis: list[KPIResultOut]
    compliance_caveat: str | None


class FieldMappingEntryOut(BaseModel):
    canonical_field: str
    description: str
    required_for_pack: bool
    matched_column: str | None


class FieldMappingOut(BaseModel):
    """What a user reviews before trusting the KPIs/reports computed
    from it — the automatic alias/token matching's result for every
    canonical field the pack defines, which actual columns are
    available to map to instead, and whether a human has confirmed this
    mapping (is_confirmed) or it's still just the automatic guess."""

    industry_id: str
    pack_name: str
    fields: list[FieldMappingEntryOut]
    available_columns: list[str]
    missing_required_fields: list[str]
    is_confirmed: bool


class ConfirmFieldMappingRequest(BaseModel):
    mapping: dict[str, str | None] = Field(
        description="canonical_field -> actual column name (or null to leave unmapped)"
    )
