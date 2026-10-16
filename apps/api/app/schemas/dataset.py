from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ColumnProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    inferred_type: str
    suggested_type: str
    null_count: int
    null_ratio: float
    distinct_count: int
    sample_values: list[Any]
    stats: dict[str, Any]
    flags: list[str]
    # Defaults keep this backwards-compatible with profile JSON persisted
    # before this field existed.
    invalid_count: int = 0
    invalid_ratio: float = 0.0


class DataQualityIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: str
    issue_type: str
    column: str | None
    detail: str


class TableProfileOut(BaseModel):
    sheet_name: str
    row_count: int
    column_count: int
    duplicate_row_count: int
    columns: list[ColumnProfileOut]
    issues: list[DataQualityIssueOut]
    quality_score: float


class DatasetTableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_name: str
    row_count: int
    column_count: int
    profile: TableProfileOut
    confirmed_schema: dict[str, str] | None


class DatasetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_number: int
    status: str
    source_filename: str | None
    file_size_bytes: int | None
    derived_from_version_id: str | None
    tables: list[DatasetTableOut]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    created_by_user_id: str


class DatasetDetailOut(DatasetOut):
    versions: list[DatasetVersionOut]


class ConfirmSchemaRequest(BaseModel):
    column_types: dict[str, str] = Field(
        description="Column name -> confirmed type (integer | float | boolean | date | datetime | text)"
    )


class FillMissingValuesRequest(BaseModel):
    column: str
    strategy: str = Field(description="drop_rows | constant | mean | median | mode")
    constant_value: str | int | float | bool | None = Field(
        default=None, description="Required when strategy is 'constant'"
    )


class NormalizeTextRequest(BaseModel):
    column: str
    case: str | None = Field(default=None, description="lower | upper | title | omit for no case change")
    trim: bool = True
    collapse_whitespace: bool = True


class FilterRowsRequest(BaseModel):
    column: str
    operator: str = Field(description="eq | ne | gt | gte | lt | lte | contains | is_null | not_null")
    value: str | int | float | bool | None = None


class CalculatedFieldRequest(BaseModel):
    new_column_name: str = Field(min_length=1, max_length=255)
    left_column: str
    operator: str = Field(description="add | subtract | multiply | divide | concat")
    right_column: str | None = None
    right_value: str | int | float | None = None
    separator: str = ""


class MergeColumnsRequest(BaseModel):
    columns: list[str] = Field(min_length=2)
    new_column_name: str = Field(min_length=1, max_length=255)
    separator: str = " "
    drop_source_columns: bool = True


class SplitColumnRequest(BaseModel):
    column: str
    delimiter: str = Field(min_length=1)
    new_column_names: list[str] | None = Field(
        default=None, description="Must exactly match the number of parts the data actually splits into"
    )
    drop_source_column: bool = True


class StandardizeColumnRequest(BaseModel):
    column: str
    kind: str = Field(description="date | currency")
    date_format: str | None = Field(default=None, description="Required when kind='date', e.g. '%Y-%m-%d'")


class PivotRequest(BaseModel):
    index_columns: list[str] = Field(min_length=1)
    pivot_column: str
    value_column: str
    aggregate_function: str = Field(default="sum", description="min | max | first | last | sum | mean | median | len")


class UnpivotRequest(BaseModel):
    id_columns: list[str] = Field(min_length=1)
    value_columns: list[str] = Field(min_length=1)
    variable_name: str = "variable"
    value_name: str = "value"


class GroupByAggregation(BaseModel):
    column: str | None = Field(default=None, description="Omit for function='count'")
    function: str = Field(description="sum | mean | min | max | median | count")
    output_name: str = Field(min_length=1, max_length=255)


class GroupByRequest(BaseModel):
    group_by_columns: list[str] = Field(min_length=1)
    aggregations: list[GroupByAggregation] = Field(min_length=1)


class TransformationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    operation_type: str
    parameters: dict[str, Any]
    source_version_id: str
    result_version_id: str
    performed_by_user_id: str
