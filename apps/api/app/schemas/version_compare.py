from pydantic import BaseModel, Field


class CompareVersionsRequest(BaseModel):
    version_a: int = Field(description="Earlier version_number to compare from")
    version_b: int = Field(description="Later version_number to compare to")
    sheet_name: str | None = Field(default=None, description="Required if a version has more than one sheet")


class ColumnComparisonOut(BaseModel):
    column: str
    type: str
    sum_before: float | None = None
    sum_after: float | None = None
    sum_delta: float | None = None
    sum_pct_change: float | None = None
    mean_before: float | None = None
    mean_after: float | None = None
    distinct_before: int | None = None
    distinct_after: int | None = None
    most_common_before: str | None = None
    most_common_after: str | None = None


class CompareVersionsResponse(BaseModel):
    version_a: int
    version_b: int
    sheet_name: str
    row_count_before: int
    row_count_after: int
    row_count_delta: int
    row_count_pct_change: float | None
    columns_added: list[str]
    columns_removed: list[str]
    common_columns: list[str]
    column_comparisons: list[ColumnComparisonOut]
