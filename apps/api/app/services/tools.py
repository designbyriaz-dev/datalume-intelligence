"""The tool registry: the single source of truth for which deterministic
analytical operations exist, their parameters, and how to validate and
invoke them. Used by two callers today — the direct /analyze REST
endpoint, and (once an LLM key is configured) the AI query planner's
tool-calling loop — so a tool defined once here is available to both.

This is also the enforcement point for "AI must not be permitted to
execute arbitrary code": the planner can only ever call something in
this registry, never raw code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import polars as pl

from app.services import analytics


@dataclass
class ToolParameter:
    name: str
    type: str  # JSON-schema primitive: "string" | "number" | "integer"
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: list[ToolParameter]
    func: Callable[..., dict[str, Any]]

    def input_schema(self) -> dict[str, Any]:
        """JSON schema in the shape Anthropic's tool-use API expects for
        a tool's `input_schema`."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {"type": "object", "properties": properties, "required": required}

    def execute(self, df: pl.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for p in self.parameters:
            if p.name in params and params[p.name] is not None:
                kwargs[p.name] = params[p.name]
            elif p.required:
                raise analytics.AnalyticsError(f"Missing required parameter: {p.name}")
            elif p.default is not None:
                kwargs[p.name] = p.default
        unknown = set(params) - {p.name for p in self.parameters}
        if unknown:
            raise analytics.AnalyticsError(f"Unknown parameter(s): {', '.join(sorted(unknown))}")
        return self.func(df, **kwargs)


TOOLS: dict[str, ToolSpec] = {
    "descriptive_stats": ToolSpec(
        name="descriptive_stats",
        description=(
            "Compute count, sum, mean, median, min, max, standard deviation and "
            "variance for a single numeric column."
        ),
        parameters=[ToolParameter("column", "string", "The numeric column to summarise.")],
        func=analytics.descriptive_stats,
    ),
    "frequency_table": ToolSpec(
        name="frequency_table",
        description="Count how often each distinct value appears in a column, most common first.",
        parameters=[
            ToolParameter("column", "string", "The column to count values in."),
            ToolParameter(
                "top_n", "integer", "Maximum number of distinct values to return.", required=False, default=20
            ),
        ],
        func=analytics.frequency_table,
    ),
    "correlation": ToolSpec(
        name="correlation",
        description="Compute the Pearson correlation coefficient between two numeric columns.",
        parameters=[
            ToolParameter("column_a", "string", "First numeric column."),
            ToolParameter("column_b", "string", "Second numeric column."),
        ],
        func=analytics.correlation,
    ),
    "detect_outliers": ToolSpec(
        name="detect_outliers",
        description="Find statistical outliers in a numeric column using the 1.5*IQR method.",
        parameters=[ToolParameter("column", "string", "The numeric column to check for outliers.")],
        func=analytics.detect_outliers,
    ),
    "group_aggregate": ToolSpec(
        name="group_aggregate",
        description=(
            "Aggregate a numeric column grouped by a category column (e.g. total rent by "
            "property type). Use agg='count' to count rows per group without a value_column."
        ),
        parameters=[
            ToolParameter("group_by", "string", "The categorical column to group by."),
            ToolParameter(
                "agg",
                "string",
                "Aggregation function.",
                required=False,
                default="sum",
                enum=["sum", "mean", "count", "min", "max", "median"],
            ),
            ToolParameter(
                "value_column",
                "string",
                "The numeric column to aggregate. Required unless agg='count'.",
                required=False,
            ),
        ],
        func=analytics.group_aggregate,
    ),
    "time_trend": ToolSpec(
        name="time_trend",
        description="Aggregate a numeric column by month or year from a date column, to show a trend over time.",
        parameters=[
            ToolParameter("date_column", "string", "The date column (may be stored as text)."),
            ToolParameter("value_column", "string", "The numeric column to aggregate per period."),
            ToolParameter("period", "string", "Bucket size.", required=False, default="month", enum=["month", "year"]),
            ToolParameter(
                "agg",
                "string",
                "Aggregation function.",
                required=False,
                default="sum",
                enum=["sum", "mean", "count", "min", "max"],
            ),
        ],
        func=analytics.time_trend,
    ),
    "simple_forecast": ToolSpec(
        name="simple_forecast",
        description=(
            "Project a numeric column forward using a simple linear-trend baseline over "
            "historical month/year periods. Not seasonality-aware — directional only."
        ),
        parameters=[
            ToolParameter("date_column", "string", "The date column (may be stored as text)."),
            ToolParameter("value_column", "string", "The numeric column to forecast."),
            ToolParameter(
                "periods_ahead", "integer", "How many future periods to forecast (1-24).", required=False, default=3
            ),
            ToolParameter("period", "string", "Bucket size.", required=False, default="month", enum=["month", "year"]),
        ],
        func=analytics.simple_forecast,
    ),
}


def anthropic_tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions in the shape the Anthropic Messages API expects
    for its `tools` parameter. Used by app/services/ai/ once a real LLM
    client is wired in."""
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema()}
        for spec in TOOLS.values()
    ]
